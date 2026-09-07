"""Serial R4 suite: V14-V17 tests plus verified V5 baselines."""
import fcntl
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "my-strategies/E0V1E64_R4"
VERSIONS = ("V5", "V14", "V15", "V16", "V17")
PERIODS = {
    "apr-jun-2026": ("okx_12m_archive", "20260401-20260630"),
    "year-2025": ("okx_2025_full_server_archive", "20250101-20260101"),
}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_result(folder):
    pointer = json.loads((folder / ".last_result.json").read_text())
    path = folder / pointer["latest_backtest"]
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist()
                    if name.endswith(".json") and not name.endswith("_config.json")
                    and "_E0V1E" not in name)
        results = json.loads(archive.read(name))["strategy"]
    assert len(results) == 1
    return next(iter(results.values())), path, next(iter(results))


def inputs():
    paths = sorted(SOURCE.glob("*.py")) + sorted(SOURCE.glob("*.json"))
    paths += [HERE / "README.md", HERE / "ENVIRONMENT.md", HERE / "config.backtest.json",
              HERE / "run_suite.py", HERE / "test_variants.py", HERE / "summarize.py",
              HERE / "test_reports.py", ROOT / "run_backtest.py", ROOT / "fix_dns.py"]
    return {str(path.relative_to(ROOT)): sha(path) for path in paths}


def manifest(period):
    data_name, timerange = PERIODS[period]
    folder = HERE / period
    folder.mkdir(parents=True, exist_ok=True)
    data = ROOT / "user_data/data" / data_name
    files = sorted(data.rglob("*.feather"))
    current = {"inputs": inputs(), "data_directory": str(data.relative_to(ROOT)),
               "timerange": timerange,
               "data_hashes": {str(path.relative_to(data)): sha(path) for path in files}}
    path = folder / "manifest.json"
    if path.exists():
        prior = json.loads(path.read_text())
        if prior != current:
            raise RuntimeError("Frozen inputs or data changed: " + period)
    else:
        path.write_text(json.dumps(current, indent=2))
    return current


def copy_verified_baseline(period, source_folder, manifest_data, provenance):
    folder = HERE / period / "V5"
    result, result_path, name = read_result(source_folder)
    source_done = json.loads((source_folder / "completed.json").read_text())
    assert sha(result_path) == source_done["result_sha256"]
    assert name == "E0V1E64_V5"
    assert len(result["trades"]) == (255 if period == "apr-jun-2026" else 855)
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / "completed.json").exists():
        for path in (source_folder / ".last_result.json", result_path):
            shutil.copy2(path, folder / path.name)
        for path in source_folder.glob("*.meta.json"):
            shutil.copy2(path, folder / path.name)
        (folder / "completed.json").write_text(json.dumps({
            "version": "V5", "reused": True, "provenance": provenance,
            "result_sha256": sha(result_path), "inputs": manifest_data["inputs"]
        }, indent=2))
    print(f"VERIFIED REUSE: {period} V5 from {provenance}; not a new run.", flush=True)


def run_one(period, version, manifest_data):
    folder = HERE / period / version
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "completed.json").exists():
        done = json.loads((folder / "completed.json").read_text())
        result, path, name = read_result(folder)
        assert done["inputs"] == inputs() and done["result_sha256"] == sha(path)
        assert name == "E0V1E64_" + version
        print("RESUME " + period + " " + version, flush=True)
        return
    if (folder / ".last_result.json").exists():
        raise RuntimeError("Unverified existing output; inspect rather than overwrite: " + str(folder))
    data_name, timerange = PERIODS[period]
    command = [sys.executable, str(ROOT / "run_backtest.py"), "backtesting",
               "--config", str(HERE / "config.backtest.json"), "--strategy-path", str(SOURCE),
               "--strategy", "E0V1E64_" + version, "--datadir", str(ROOT / "user_data/data" / data_name),
               "--timerange", timerange, "--max-open-trades", "1", "--fee", "0.0005",
               "--enable-protections", "--cache", "none", "--export", "trades",
               "--backtest-directory", str(folder)]
    started = time.time()
    print(f"START {period} {version} {datetime.now(timezone.utc).isoformat()}", flush=True)
    with (folder / "run.log").open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        (folder / "running.json").write_text(json.dumps({
            "pid": process.pid, "started": started, "command": command
        }, indent=2))
        code = process.wait()
    if code:
        raise RuntimeError(f"{period} {version} failed ({code}); inspect run.log")
    if manifest_data["inputs"] != inputs():
        raise RuntimeError("Frozen inputs changed while running")
    result, result_path, name = read_result(folder)
    assert name == "E0V1E64_" + version
    assert result["max_open_trades"] == 1
    if period == "apr-jun-2026":
        assert any(trade["funding_fees"] != 0 for trade in result["trades"]), "Missing funding calculation"
    (folder / "completed.json").write_text(json.dumps({
        "version": version, "reused": False, "result": result_path.name,
        "result_sha256": sha(result_path), "inputs": manifest_data["inputs"],
        "seconds": time.time() - started
    }, indent=2))
    print(f"DONE {period} {version}: return={result['profit_total'] * 100:.4f}% "
          f"PF={result['profit_factor']:.6f} DD={result['max_drawdown_account'] * 100:.3f}% "
          f"n={len(result['trades'])}", flush=True)


def main():
    with (HERE / ".suite.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for period in PERIODS:
            data_manifest = manifest(period)
            if period == "apr-jun-2026":
                copy_verified_baseline(
                    period, ROOT / "validation/e0v1e64-r3/apr-jun-2026/V5",
                    data_manifest, "validation/e0v1e64-r3/apr-jun-2026/V5")
            else:
                copy_verified_baseline(
                    period, ROOT / "validation/e0v1e64-r2/year-2025/V5",
                    data_manifest, "validation/e0v1e64-r2/year-2025/V5")
            for version in VERSIONS[1:]:
                run_one(period, version, data_manifest)
            manifest(period)
        subprocess.run([sys.executable, str(HERE / "summarize.py")], cwd=ROOT, check=True)
        print("R4 COMPLETE: eight new runs plus two verified V5 baselines.", flush=True)


if __name__ == "__main__":
    main()
