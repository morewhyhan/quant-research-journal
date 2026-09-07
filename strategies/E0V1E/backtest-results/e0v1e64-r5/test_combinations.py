"""Tests target multiple-inheritance integration and statistics, not old rule duplication."""
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'my-strategies/E0V1E64_R5'
sys.path.insert(0, str(SOURCE))
from E0V1E64_V5 import E0V1E64_V5
from E0V1E64_V14 import E0V1E64_V14
from E0V1E64_V16 import E0V1E64_V16
from E0V1E64_V17 import E0V1E64_V17
from research_stats import statistics, paired_block_interval
from run_suite import FACTORS, sha

NEW = {v: getattr(importlib.import_module('E0V1E64_' + v), 'E0V1E64_' + v) for v in ('V18','V19','V20','V21')}


class CombinationTests(unittest.TestCase):
    def test_inherited_callbacks_are_exact_modules_and_single_v5(self):
        for version, cls in NEW.items():
            rank, exit_rule, budget = FACTORS[version]
            self.assertEqual(cls.__mro__.count(E0V1E64_V5), 1)
            self.assertIs(cls.custom_exit, E0V1E64_V16.custom_exit if exit_rule else E0V1E64_V5.custom_exit)
            self.assertIs(cls.custom_stake_amount, E0V1E64_V17.custom_stake_amount if budget else E0V1E64_V5.custom_stake_amount)
            self.assertIs(cls.confirm_trade_entry, E0V1E64_V14.confirm_trade_entry if rank else E0V1E64_V5.confirm_trade_entry)
            self.assertEqual(cls.max_extension_minutes, 60)

    def test_real_loader_parameters_and_research_guard(self):
        from freqtrade.resolvers import StrategyResolver
        original = json.loads((SOURCE / 'E0V1E64_V5.json').read_text())['params']
        for cls in NEW.values():
            self.assertEqual(json.loads((SOURCE/(cls.__name__+'.json')).read_text())['params'], original)
            cfg = {'strategy': cls.__name__, 'strategy_path': str(SOURCE), 'user_data_dir': ROOT/'user_data',
                   'stake_currency': 'USDT', 'stake_amount': 'unlimited', 'max_open_trades': 1,
                   'trading_mode': 'futures', 'runmode': 'backtest'}
            s = StrategyResolver.load_strategy(cfg)
            s.ft_load_hyper_params(False)
            s.bot_start()
            self.assertEqual(s.stoploss, -.25)
            for group in ('buy', 'sell'):
                for name, value in original[group].items():
                    self.assertAlmostEqual(getattr(s, name).value, value)
            for mode in ('live', 'dry_run'):
                with self.assertRaises(RuntimeError):
                    cls({'runmode': mode}).bot_start()

    def test_shared_parent_exit_executed_once_in_each_combination(self):
        for cls in NEW.values():
            s = cls({})
            with patch.object(E0V1E64_V5, 'custom_exit', return_value='parent_exit') as callback:
                self.assertEqual(s.custom_exit('A', SimpleNamespace(), None, 100, 0), 'parent_exit')
                callback.assert_called_once()

    def test_ranked_entry_and_budget_both_active(self):
        for name in ('V18', 'V21'):
            s = NEW[name]({})
            s.wallets = None
            s.is_pair_locked = lambda *a, **k: False
            with patch.object(s, 'ranked_signals', return_value=[{'pair': 'B', 'side': 'short'}]):
                now = pd.Timestamp('2026-04-01T12:00:00Z').to_pydatetime()
                self.assertFalse(s.confirm_trade_entry('A', 'market', 1, 100, 'GTC', now, 'test', 'short'))
                self.assertTrue(s.confirm_trade_entry('B', 'market', 1, 100, 'GTC', now, 'test', 'short'))
                self.assertAlmostEqual(s.custom_stake_amount('B', now, 100, 970, 1, 970, 1, 'test', 'short'), 600)

    def test_factorial_covers_all_eight_states(self):
        self.assertEqual(len(set(FACTORS.values())), 8)
        self.assertEqual(set(FACTORS.values()), {(r,e,b) for r in (0,1) for e in (0,1) for b in (0,1)})

    def test_frozen_parents_unchanged(self):
        for p in SOURCE.glob('*'):
            if p.suffix in ('.py', '.json') and not any(v in p.name for v in NEW):
                self.assertEqual(sha(p), sha(ROOT/'my-strategies/E0V1E64_R4'/p.name))

    def test_variance_units_and_month_boundary(self):
        r = pd.Series([-.01, 0, .01], index=pd.date_range('2025-01-30', periods=3, tz='UTC'))
        s = statistics(r)
        self.assertAlmostEqual(s['daily_variance_decimal'], .0001)
        self.assertAlmostEqual(s['daily_variance_pp2'], 1)
        self.assertAlmostEqual(s['daily_std_pct'], 1)
        self.assertEqual(list(s['monthly_returns_pct']), ['2025-01'])
        self.assertAlmostEqual(s['monthly_returns_pct']['2025-01'], -.01)

    def test_paired_identical_series_excess_interval_zero(self):
        r = pd.Series(np.linspace(-.02, .03, 30), index=pd.date_range('2025-01-01', periods=30, tz='UTC'))
        s = paired_block_interval(r, r)
        self.assertEqual(s['bootstrap_95pct_interval_pp'], [0, 0])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CombinationTests))
    Path(__file__).with_name('TEST_RESULTS.json').write_text(json.dumps({
        'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'source_sha256': {p.name: sha(p) for p in sorted(SOURCE.iterdir()) if p.suffix in ('.py', '.json')},
        'test_script_sha256': sha(Path(__file__)),
    }, indent=2))
    sys.exit(not result.wasSuccessful())
