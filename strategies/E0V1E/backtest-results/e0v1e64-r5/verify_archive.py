"""Check published bytes against actual executed sources/results and git objects."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from run_suite import HERE, ROOT, SOURCE, sha

REPO = ROOT/'validation/quant-research-journal'
SRC = REPO/'strategies/E0V1E/versions/e0v1e64-r5'
DST = REPO/'strategies/E0V1E/backtest-results/e0v1e64-r5'
MANIFEST = DST/'ARCHIVE_MANIFEST.json'
EXTENSIONS = ('.py', '.json', '.md', '.feather', '.zip')


def files():
    checks = []
    for local, archive in ((SOURCE, SRC), (HERE, DST)):
        for source in sorted(local.rglob('*')):
            if (not source.is_file() or source.suffix not in EXTENSIONS
                    or source.name == 'running.json' or '__pycache__' in source.parts):
                continue
            target = archive/source.relative_to(local)
            assert target.is_file(), str(target)
            assert sha(source) == sha(target), str(target)
            checks.append(str(target.relative_to(REPO)))
    assert sha(DST/'workspace_helpers/run_backtest.py') == sha(ROOT/'run_backtest.py')
    assert sha(DST/'workspace_helpers/fix_dns.py') == sha(ROOT/'fix_dns.py')
    records = {}
    for folder in (SRC, DST):
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path == MANIFEST:
                continue
            assert '__pycache__' not in path.parts and path.name not in ('run.log', 'running.json', '.suite.lock')
            records[str(path.relative_to(REPO))] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    assert set(checks).issubset(records)
    MANIFEST.write_text(json.dumps({'passed': True, 'verified_executed_files': len(checks),
                                   'files': records}, indent=2))
    print('PASS archive source/result byte identity:', len(checks), 'executed files;', len(records), 'total files')


def git_objects(mode):
    manifest = json.loads(MANIFEST.read_text())
    records = dict(manifest['files'])
    records[str(MANIFEST.relative_to(REPO))] = {'sha256': sha(MANIFEST), 'bytes': MANIFEST.stat().st_size}
    prefix = ':' if mode == 'index' else 'HEAD:'
    proc = subprocess.Popen(['git', '-C', str(REPO), 'cat-file', '--batch'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for name, expected in records.items():
            proc.stdin.write((prefix + name + '\n').encode())
            proc.stdin.flush()
            header = proc.stdout.readline().decode().strip().split()
            assert len(header) == 3 and header[1] == 'blob', (name, header)
            size = int(header[2])
            payload = proc.stdout.read(size)
            assert len(payload) == size and proc.stdout.read(1) == b'\n'
            assert size == expected['bytes'] and hashlib.sha256(payload).hexdigest() == expected['sha256'], name
    finally:
        proc.stdin.close()
        proc.wait()
    assert proc.returncode == 0
    print('PASS git', mode, 'matches all', len(records), 'archived byte hashes')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'files'
    if mode == 'files':
        files()
    elif mode in ('index', 'head'):
        git_objects(mode)
    else:
        raise SystemExit('Use files, index or head')
