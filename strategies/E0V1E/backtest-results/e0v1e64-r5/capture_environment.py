"""Capture the actual local runtime; does not install or update dependencies."""
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
root = here.parents[1]
names = ('freqtrade', 'ccxt', 'pandas', 'numpy', 'pyarrow', 'TA-Lib', 'technical', 'scipy')
versions = {}
for name in names:
    try:
        versions[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        versions[name] = None
payload = {
    'python': sys.version, 'platform': platform.platform(), 'executable': sys.executable,
    'package_versions': versions,
    'raw_data_in_git': False,
    'commands_from_workspace_root': [
        '.venv/bin/python validation/e0v1e64-r5/test_combinations.py',
        '.venv/bin/python validation/e0v1e64-r5/test_report.py',
        '.venv/bin/python validation/e0v1e64-r5/run_suite.py',
    ],
    'note': 'The suite uses frozen R4 controls and data; restore both round folders and original workspace paths before running. The scripts do not download missing market data.',
}
(here/'ENVIRONMENT.json').write_text(json.dumps(payload, indent=2))
print(json.dumps(payload, indent=2))
