"""Audit source/data provenance and independently reconstructed net equity."""
import json
import zipfile
from run_suite import HERE, ROOT, SOURCE, OLD, VERSIONS, NEW, PERIODS, inputs, manifest, read_result, sha


def main():
    comparison = json.loads((HERE / 'comparison.json').read_text())
    tests = json.loads((HERE / 'TEST_RESULTS.json').read_text())
    assert tests['passed'] and not tests['failures'] and not tests['errors']
    for name, digest in tests['source_sha256'].items():
        assert sha(SOURCE / name) == digest
    assert tests['test_script_sha256'] == sha(HERE / 'test_combinations.py')
    report_tests = json.loads((HERE / 'REPORT_TEST_RESULTS.json').read_text())
    assert report_tests['passed'] and not report_tests['failures'] and not report_tests['errors']
    for name, digest in report_tests['checked_script_hashes'].items():
        assert sha(HERE / name) == digest
    checks = []
    for period in PERIODS:
        manifest(period)
        for version in VERSIONS:
            folder = HERE / period / version
            done = json.loads((folder / 'completed.json').read_text())
            result, path, name = read_result(folder)
            assert name == 'E0V1E64_' + version and sha(path) == done['result_sha256']
            assert done['inputs'] == inputs()
            assert done['reused'] == (version not in NEW)
            if done['reused']:
                assert done['provenance'] == str((OLD / period / version).relative_to(ROOT))
                _, old_zip, _ = read_result(OLD / period / version)
                assert sha(path) == sha(old_zip)
            with zipfile.ZipFile(path) as archive:
                config = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('_config.json'))))
                assert config['dry_run'] and not config['api_server']['enabled']
                assert all(config['exchange'].get(k) in ('', None, 'REDACTED', '***') for k in ('key', 'secret', 'password', 'apiKey'))
            s = comparison[period][version]
            assert s['actual_leverage'] == [1.0] and s['max_concurrent_positions'] <= 1
            assert s['max_trade_pnl_reconciliation_error'] < .001 and s['max_funding_reconciliation_error'] < .01
            assert not s['valuation_gap_pairs']
            assert abs(s['daily_std_pct'] ** 2 - s['daily_variance_pp2']) < 1e-8
            assert s['days'] == (90 if period == 'apr-jun-2026' else 365)
            if period == 'apr-jun-2026':
                assert s['funded_trades'] > 0 and s['pairlist_count'] == 174
            else:
                assert s['funded_trades'] == 0 and s['pairlist_count'] == 180
            checks.append({'period': period, 'version': version, 'result_sha256': sha(path),
                           'reused': done['reused'], 'days': s['days'], 'trades': s['trades'],
                           'variance_units_and_equity_reconciled': True})
    (HERE / 'FINAL_AUDIT.json').write_text(json.dumps({
        'passed': True, 'new_backtests': 8, 'reused_controls': 8, 'checks': checks,
        'combination_tests': tests['tests_run'], 'report_math_tests': report_tests['tests_run'],
        'report_script_hashes': {p.name: sha(p) for p in HERE.glob('*.py')},
    }, indent=2))
    print('PASS: 8 new combinations + 8 reused controls; provenance, variance and equity verified.', flush=True)


if __name__ == '__main__':
    main()
