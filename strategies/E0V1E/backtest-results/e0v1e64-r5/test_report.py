"""Independent hand-calculated checks for factorial/report mathematics."""
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from run_suite import FACTORS, sha
from research_stats import statistics, paired_block_interval
from summarize import effects


class ReportTests(unittest.TestCase):
    def test_full_factorial_response_and_interactions(self):
        # y = 5 + 2R + 3E + 4B + 7RE + 8RB + 9EB + 10REB.
        metrics = ('mean_daily_log_return_pct', 'daily_variance_pp2', 'pf', 'mtm_max_drawdown_pct')
        result = {}
        for version, (r, e, b) in FACTORS.items():
            y = 5 + 2*r + 3*e + 4*b + 7*r*e + 8*r*b + 9*e*b + 10*r*e*b
            result[version] = dict.fromkeys(metrics, y)
        actual = effects(result)
        expected_main = {'R排序': 12, 'E退出': 13.5, 'B仓位': 15}
        expected_pair = {'R排序×E退出': 12, 'R排序×B仓位': 13, 'E退出×B仓位': 14}
        for key, value in expected_main.items():
            for metric in metrics:
                self.assertAlmostEqual(actual['main_effects'][key][metric], value)
        for key, value in expected_pair.items():
            for metric in metrics:
                self.assertAlmostEqual(actual['pair_interactions'][key][metric], value)
        for metric in metrics:
            self.assertAlmostEqual(actual['third_order'][metric], 10)

    def test_compound_quarter_months_and_log_growth(self):
        r = pd.Series([.10, -.10, .20], index=pd.to_datetime(
            ['2025-02-01', '2025-03-01', '2025-04-01'], utc=True))
        s = statistics(r)
        self.assertEqual(list(s['monthly_returns_pct']), ['2025-01', '2025-02', '2025-03'])
        self.assertAlmostEqual(s['quarterly_returns_pct']['2025Q1'], 18.8)
        self.assertAlmostEqual(np.expm1(s['mean_daily_log_return_pct']/100*3)*100, 18.8)
        self.assertAlmostEqual(s['daily_variance_pp2'], 233.33333333333334)
        self.assertAlmostEqual(s['downside_deviation_zero_pct'], np.sqrt(.01/3)*100)

    def test_constant_paired_log_excess_stays_constant(self):
        idx = pd.date_range('2025-01-01', periods=365, tz='UTC')
        base = pd.Series(np.linspace(-.08, .10, 365), index=idx)
        candidate = np.expm1(np.log1p(base) + .001)
        interval = paired_block_interval(candidate, base)
        self.assertAlmostEqual(interval['daily_log_excess_pct'], .1)
        for bound in interval['bootstrap_95pct_interval_pp']:
            self.assertAlmostEqual(bound, .1)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReportTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    here = Path(__file__).resolve().parent
    (here/'REPORT_TEST_RESULTS.json').write_text(json.dumps({
        'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'checked_script_hashes': {name: sha(here/name) for name in (
            'test_report.py', 'summarize.py', 'research_stats.py')},
    }, indent=2))
    raise SystemExit(not result.wasSuccessful())
