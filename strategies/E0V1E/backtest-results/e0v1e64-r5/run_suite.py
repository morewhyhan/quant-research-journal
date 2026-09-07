"""Fixed full-factorial comparisons, serial offline backtests, verified old controls."""
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from research_stats import read_result

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'my-strategies/E0V1E64_R5'
OLD = ROOT / 'validation/e0v1e64-r4'
VERSIONS = ('V5', 'V14', 'V16', 'V17', 'V18', 'V19', 'V20', 'V21')
NEW = VERSIONS[4:]
PERIODS = {'apr-jun-2026': ('okx_12m_archive', '20260401-20260630'),
           'year-2025': ('okx_2025_full_server_archive', '20250101-20260101')}
FACTORS = {'V5': (0, 0, 0), 'V14': (1, 0, 0), 'V16': (0, 1, 0), 'V17': (0, 0, 1),
           'V18': (1, 0, 1), 'V19': (1, 1, 0), 'V20': (0, 1, 1), 'V21': (1, 1, 1)}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inputs():
    files = sorted(SOURCE.glob('*.py')) + sorted(SOURCE.glob('*.json'))
    files += [HERE / name for name in ('SPEC.md', 'config.backtest.json', 'run_suite.py', 'test_combinations.py')]
    files += [ROOT / name for name in ('run_backtest.py', 'fix_dns.py')]
    return {str(p.relative_to(ROOT)): sha(p) for p in files}


def manifest(period):
    directory, timerange = PERIODS[period]
    data = ROOT / 'user_data/data' / directory
    current = {'inputs': inputs(), 'timerange': timerange, 'data_directory': str(data.relative_to(ROOT)),
               'data_hashes': {str(p.relative_to(data)): sha(p) for p in sorted(data.rglob('*.feather'))},
               'freqtrade_version': importlib.metadata.version('freqtrade')}
    old_manifest = json.loads((OLD / period / 'manifest.json').read_text())
    assert current['data_hashes'] == old_manifest['data_hashes'], 'Old comparison data changed'
    assert current['freqtrade_version'] == '2026.5.1'
    for path in ('run_backtest.py', 'fix_dns.py'):
        assert sha(ROOT / path) == old_manifest['inputs'][path], path
    assert sha(HERE / 'config.backtest.json') == old_manifest['inputs']['validation/e0v1e64-r4/config.backtest.json']
    for filename in ('E0V1E_v3.py', 'E0V1E_v3_equity60_reserve40.py', 'research_common.py', 'r4_common.py',
                     'E0V1E64_V5.py', 'E0V1E64_V5.json', 'E0V1E64_V14.py', 'E0V1E64_V14.json',
                     'E0V1E64_V16.py', 'E0V1E64_V16.json', 'E0V1E64_V17.py', 'E0V1E64_V17.json'):
        assert sha(SOURCE / filename) == old_manifest['inputs']['my-strategies/E0V1E64_R4/' + filename], filename
    folder = HERE / period
    folder.mkdir(exist_ok=True)
    output = folder / 'manifest.json'
    if output.exists():
        assert json.loads(output.read_text()) == current, 'Frozen run inputs changed'
    else:
        output.write_text(json.dumps(current, indent=2))
    return current


def reuse(period, version, m):
    old_folder, folder = OLD / period / version, HERE / period / version
    result, zip_path, name = read_result(old_folder)
    old_done = json.loads((old_folder / 'completed.json').read_text())
    assert sha(zip_path) == old_done['result_sha256'] and name == 'E0V1E64_' + version
    folder.mkdir(exist_ok=True)
    for p in [old_folder / '.last_result.json', zip_path, *old_folder.glob('*.meta.json')]:
        target = folder / p.name
        if target.exists():
            assert sha(target) == sha(p)
        else:
            shutil.copy2(p, target)
    done = {'reused': True, 'version': version, 'provenance': str(old_folder.relative_to(ROOT)),
            'source_completed_sha256': sha(old_folder / 'completed.json'),
            'result_sha256': sha(zip_path), 'inputs': m['inputs']}
    output = folder / 'completed.json'
    if output.exists():
        assert json.loads(output.read_text()) == done
    else:
        output.write_text(json.dumps(done, indent=2))
    print('VERIFIED REUSE', period, version, len(result['trades']), flush=True)


def run_one(period, version, m):
    folder = HERE / period / version
    folder.mkdir(exist_ok=True)
    completed = folder / 'completed.json'
    if completed.exists():
        done = json.loads(completed.read_text())
        _, path, _ = read_result(folder)
        assert done['inputs'] == inputs() and sha(path) == done['result_sha256']
        print('RESUME', period, version, flush=True)
        return
    assert not (folder / '.last_result.json').exists(), 'Unverified previous output'
    data, timerange = PERIODS[period]
    command = [sys.executable, str(ROOT / 'run_backtest.py'), 'backtesting', '--config', str(HERE / 'config.backtest.json'),
               '--strategy-path', str(SOURCE), '--strategy', 'E0V1E64_' + version,
               '--datadir', str(ROOT / 'user_data/data' / data), '--timerange', timerange,
               '--max-open-trades', '1', '--fee', '0.0005', '--enable-protections', '--cache', 'none',
               '--export', 'trades', '--backtest-directory', str(folder)]
    print('START', period, version, datetime.now(timezone.utc).isoformat(), flush=True)
    start = time.time()
    with (folder / 'run.log').open('w') as log:
        proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        (folder / 'running.json').write_text(json.dumps({'pid': proc.pid, 'command': command, 'started': start}, indent=2))
        if proc.wait():
            raise RuntimeError(f'{period} {version} failed; inspect run.log')
    assert m['inputs'] == inputs()
    result, path, name = read_result(folder)
    assert name == 'E0V1E64_' + version and result['max_open_trades'] == 1
    assert {t['leverage'] for t in result['trades']} == {1.0}
    if period == 'apr-jun-2026':
        assert any(t['funding_fees'] != 0 for t in result['trades'])
    errors = [line for line in (folder / 'run.log').read_text().splitlines()
              if ' - ERROR - ' in line or 'ranking failed' in line]
    assert not errors, errors[:3]
    completed.write_text(json.dumps({'reused': False, 'version': version, 'result_sha256': sha(path),
                                    'inputs': m['inputs'], 'seconds': time.time() - start}, indent=2))
    print(f'DONE {period} {version}: return={result["profit_total"]*100:.4f}% PF={result["profit_factor"]:.6f} '
          f'DD={result["max_drawdown_account"]*100:.4f}% n={len(result["trades"])}', flush=True)


def main():
    with (HERE / '.suite.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for period in PERIODS:
            m = manifest(period)
            for version in VERSIONS[:4]:
                reuse(period, version, m)
            for version in NEW:
                run_one(period, version, m)
            manifest(period)
        subprocess.run([sys.executable, str(HERE / 'summarize.py')], cwd=ROOT, check=True)
        subprocess.run([sys.executable, str(HERE / 'final_audit.py')], cwd=ROOT, check=True)
        print('R5 COMPLETE: 8 new tests, 8 reused controls, full factorial and variance report.', flush=True)


if __name__ == '__main__':
    main()
