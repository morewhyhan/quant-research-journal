#!/usr/bin/env python3
"""Run isolated ordinary backtests; require V5 replication before comparing variants."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'my-strategies' / 'E0V1E64_R2'
DATA = ROOT / 'user_data/data/okx_2025_full_server_archive'
OUT = HERE / 'year-2025'
OLD = ROOT / 'validation/e0v1e64/year-2025/V5'


def read_result(folder):
    pointer = json.loads((folder / '.last_result.json').read_text())
    path = folder / pointer['latest_backtest']
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith('.json')
                    and not n.endswith('_config.json') and '_E0V1E' not in n)
        result = next(iter(json.loads(archive.read(name))['strategy'].values()))
    return result, path


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inputs_manifest():
    paths = sorted(SOURCE.glob('*.py')) + sorted(SOURCE.glob('*.json'))
    paths += [HERE / 'config.backtest.json', HERE / 'README.md', HERE / 'run_suite.py', HERE / 'test_variants.py', ROOT / 'run_backtest.py', ROOT / 'fix_dns.py']
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def child_running(pid, version):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'args='], capture_output=True, text=True)
    return (str(ROOT / 'run_backtest.py') in result.stdout
            and '--strategy E0V1E64_' + version in result.stdout)


def mark_complete(version, folder, started, hashes, recovered=False):
    result, path = read_result(folder)
    if inputs_manifest() != hashes:
        raise RuntimeError(f'{version}: source or configuration changed while running')
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith('.json')
                    and not n.endswith('_config.json') and '_E0V1E' not in n)
        if list(json.loads(archive.read(name))['strategy']) != ['E0V1E64_' + version]:
            raise RuntimeError(f'{version}: wrong strategy in result archive')
    (folder / 'completed.json').write_text(json.dumps({'version': version,
        'seconds': time.time() - started, 'result': path.name, 'result_sha256': sha(path),
        'input_hashes': hashes, 'recovered_after_scheduler_restart': recovered}, indent=2))
    print(f'DONE {version}: return={result["profit_total"]*100:.4f}% '
          f'PF={result["profit_factor"]:.6f} trades={len(result["trades"])}', flush=True)
    return version


def run_one(version, resume=False):
    folder = OUT / version
    folder.mkdir(parents=True, exist_ok=True)
    if resume and (folder / 'completed.json').exists():
        completed = json.loads((folder / 'completed.json').read_text())
        if completed['input_hashes'] == inputs_manifest():
            result, result_path = read_result(folder)
            if completed['result_sha256'] != sha(result_path):
                raise RuntimeError(f'{version}: archived result hash changed')
            print(f'RESUME {version}: {len(result["trades"])} trades', flush=True)
            return version
        raise RuntimeError(f'{version}: input hashes changed; use a fresh output directory')
    if resume and (folder / 'running.json').exists():
        running = json.loads((folder / 'running.json').read_text())
        if child_running(running['pid'], version):
            print(f'WAIT {version}: preserving existing process {running["pid"]}', flush=True)
            while child_running(running['pid'], version):
                time.sleep(15)
        if (folder / '.last_result.json').exists():
            hashes = json.loads((OUT / 'manifest.json').read_text())['input_hashes']
            return mark_complete(version, folder, running['started'], hashes, recovered=True)
    if (folder / '.last_result.json').exists():
        raise RuntimeError(f'{version}: existing result would be overwritten; use --resume')
    cmd = [sys.executable, str(ROOT / 'run_backtest.py'), 'backtesting',
           '--config', str(HERE / 'config.backtest.json'),
           '--strategy-path', str(SOURCE), '--strategy', 'E0V1E64_' + version,
           '--datadir', str(DATA), '--timerange', '20250101-20260101',
           '--fee', '0.0005', '--enable-protections', '--cache', 'none',
           '--export', 'trades', '--backtest-directory', str(folder)]
    started = time.time()
    before = inputs_manifest()
    print(f'START {version} {datetime.now(timezone.utc).isoformat()}', flush=True)
    if (folder / 'run.log').exists():
        (folder / 'run.log').rename(folder / f'run.previous-{int(started)}.log')
    with (folder / 'run.log').open('w') as log:
        process = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        (folder / 'running.json').write_text(json.dumps({'pid': process.pid, 'command': cmd,
            'started': started}, indent=2))
        code = process.wait()
    if code:
        raise RuntimeError(f'{version} failed ({code}); inspect {folder / "run.log"}')
    if inputs_manifest() != before:
        raise RuntimeError(f'{version}: source or configuration changed while running')
    return mark_complete(version, folder, started, before)


def check_baseline():
    current, _ = read_result(OUT / 'V5')
    old, _ = read_result(OLD)
    checks = {'trade_count': len(current['trades']) == len(old['trades'])}
    for key in ('profit_total', 'profit_factor', 'max_drawdown_account'):
        checks[key] = abs(current[key] - old[key]) < 1e-7
    def ordered(result):
        return sorted(result['trades'], key=lambda t: (t['open_timestamp'], t['pair']))
    pairs = list(zip(ordered(current), ordered(old)))
    checks['entry_exit_sequence'] = checks['trade_count'] and all(
        all(a[k] == b[k] for k in ('pair', 'open_timestamp', 'close_timestamp',
                                  'is_short', 'enter_tag', 'exit_reason'))
        and abs(a['profit_ratio'] - b['profit_ratio']) < 1e-8 for a, b in pairs)
    (OUT / 'baseline_validation.json').write_text(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise RuntimeError(f'V5 did not reproduce the approved baseline: {checks}')
    print('BASELINE VERIFIED: metrics and all 855 entry/exit records match.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, choices=(1,), default=1)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--versions', nargs='+', default=['V6','V7','V8','V9'],
                        choices=['V6','V7','V8','V9'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'manifest.json'
    if not manifest_path.exists():
        data_files = sorted(DATA.rglob('*.feather'))
        manifest_path.write_text(json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(),
            'input_hashes': inputs_manifest(), 'data_file_count': len(data_files),
            'data_hashes': {str(p.relative_to(DATA)): sha(p) for p in data_files},
            'timerange': '20250101-20260101', 'hypotheses': 'README.md'}, indent=2))
    else:
        manifest = json.loads(manifest_path.read_text())
        if manifest['input_hashes'] != inputs_manifest():
            if list(OUT.glob('*/completed.json')):
                raise RuntimeError('Frozen inputs changed after a completed backtest')
            manifest.setdefault('preflight_input_revisions', []).append(manifest['input_hashes'])
            manifest['input_hashes'] = inputs_manifest()
            manifest_path.write_text(json.dumps(manifest, indent=2))
    manifest = json.loads(manifest_path.read_text())
    previous_manifest = json.loads((ROOT / 'validation/e0v1e64/year-2025/manifest.json').read_text())
    if manifest['data_hashes'] != previous_manifest['data_hashes']:
        raise RuntimeError('Data differs from the previous V5 run; comparison not authorized as identical-data')
    run_one('V5', args.resume)
    check_baseline()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_one, v, args.resume): v for v in args.versions}
        for future in as_completed(futures):
            future.result()
    subprocess.run([sys.executable, str(HERE / 'summarize.py')], check=True, cwd=ROOT)
    print('ALL FIVE COMPLETE; report: validation/e0v1e64-r2/RESULTS.md', flush=True)


if __name__ == '__main__':
    main()
