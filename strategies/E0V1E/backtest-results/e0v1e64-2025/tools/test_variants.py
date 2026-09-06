"""Decision-boundary tests and real Freqtrade parameter-loading checks."""
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'my-strategies/E0V1E64'
sys.path.insert(0, str(SOURCE))
from E0V1E_v3_equity60_reserve40 import E0V1E_v3_equity60_reserve40 as Parent
from E0V1E64_V1 import E0V1E64_V1
from E0V1E64_V2 import E0V1E64_V2
from E0V1E64_V3 import E0V1E64_V3
from E0V1E64_V4 import E0V1E64_V4
from E0V1E64_V5 import E0V1E64_V5

NOW = datetime(2025, 6, 1, 12, tzinfo=timezone.utc)


class FakeTrade:
    is_short = True
    open_rate = 100.0
    enter_tag = 'short_1'
    open_date_utc = NOW - timedelta(hours=5)
    max_rate = 10000.0  # Deliberately poisoned with unavailable future information.
    min_rate = 1.0

    def __init__(self):
        self.data = {}

    def calc_profit_ratio(self, rate):
        return (100.0 - rate) / 100.0

    def get_custom_data(self, key, default=None):
        return self.data.get(key, default)

    def set_custom_data(self, key, value):
        self.data[key] = value


def make_frame():
    return pd.DataFrame({'date': pd.date_range(end=NOW-timedelta(minutes=5), periods=13, freq='5min'),
        'high': [106.0]*13, 'close': [104.0]*13, 'ma120': list(range(113, 100, -1)),
        'ma240': [110.0]*13, 'fastk': [20.0]*13, 'cci': [0.0]*13,
        'v3_atr_pct': [0.01]*13, 'v3_atr_reference': [0.01]*13})


def instance(cls, frame=None):
    strategy = cls({})
    strategy.dp = SimpleNamespace(get_analyzed_dataframe=lambda *a, **kw: (frame, None))
    strategy.wallets = SimpleNamespace(get_total_stake_amount=lambda: 970.0)
    strategy._peak_tradable_balance = 1400.0
    return strategy


class TestVariants(unittest.TestCase):
    def test_parameters_match_frozen_parent(self):
        from freqtrade.resolvers import StrategyResolver
        params = json.loads((SOURCE/'E0V1E_v3_equity60_reserve40.json').read_text())['params']
        for version in ('B0','V1','V2','V3','V4','V5'):
            cfg = {'strategy': 'E0V1E64_'+version, 'strategy_path': str(SOURCE),
                'user_data_dir': ROOT/'user_data', 'stake_currency':'USDT',
                'stake_amount':'unlimited', 'max_open_trades':1, 'trading_mode':'futures'}
            strategy = StrategyResolver.load_strategy(cfg)
            strategy.ft_load_hyper_params(False)
            for section in ('buy','sell'):
                for key, value in params[section].items():
                    self.assertAlmostEqual(getattr(strategy, key).value, value, msg=version+key)

    def test_v1_ignores_current_unclosed_high_and_engine_max(self):
        frame = make_frame()
        row = frame.iloc[-1].copy()
        row['date'], row['high'] = NOW, 200.0
        frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True)
        strategy = instance(E0V1E64_V1, frame)
        self.assertIsNone(strategy.custom_exit('X', FakeTrade(), NOW, 104, -0.04))

    def test_v1_observed_adverse_recovery_exits(self):
        frame = make_frame()
        frame.loc[5, 'high'] = 112.0
        strategy = instance(E0V1E64_V1, frame)
        self.assertEqual(strategy.custom_exit('X', FakeTrade(), NOW, 104, -0.04), 'v1_cci_loss_cover')

    def test_v1_ignores_pre_entry_extrema(self):
        frame = make_frame()
        frame.loc[0, 'high'] = 112.0
        trade = FakeTrade()
        trade.open_date_utc = NOW-timedelta(minutes=30)
        self.assertIsNone(instance(E0V1E64_V1, frame).custom_exit('X', trade, NOW, 104, -0.04))

    @patch.object(Parent, 'custom_exit', return_value=None)
    def test_v2_requires_age_loss_and_failed_recovery(self, _):
        frame = make_frame()
        strategy = instance(E0V1E64_V2, frame)
        trade = FakeTrade()
        self.assertEqual(strategy.custom_exit('X', trade, NOW, 104, -.04), 'v2_stale_short_4h')
        self.assertIsNone(strategy.custom_exit('X', trade, NOW, 102, -.02))
        trade.open_date_utc = NOW-timedelta(hours=3)
        self.assertIsNone(strategy.custom_exit('X', trade, NOW, 104, -.04))
        trade.open_date_utc = NOW-timedelta(hours=5)
        frame.loc[12, 'close'] = 103.0
        self.assertIsNone(strategy.custom_exit('X', trade, NOW, 104, -.04))

    def test_v3_gate_caps_reserve_but_keeps_base(self):
        frame = make_frame()
        strategy = instance(E0V1E64_V3, frame)
        args = ('X',NOW,100,970,1,970,1,'short_1','short')
        self.assertAlmostEqual(strategy.custom_stake_amount(*args),970)
        frame.loc[12,'v3_atr_pct'] = .03
        self.assertAlmostEqual(strategy.custom_stake_amount(*args),600)

    def test_v4_caps_at_available_capital(self):
        strategy = instance(E0V1E64_V4)
        args = ('X',NOW,100,970,1,970,1)
        self.assertAlmostEqual(strategy.custom_stake_amount(*args,'short_new','short'),970)
        self.assertAlmostEqual(strategy.custom_stake_amount(*args,'short_1','short'),873)

    @patch.object(Parent, 'custom_exit', return_value='fastk_profit_cover')
    def test_v5_defers_then_protects_without_future_extrema(self, _):
        strategy, trade = instance(E0V1E64_V5, make_frame()), FakeTrade()
        self.assertIsNone(strategy.custom_exit('X',trade,NOW,99,.01))
        self.assertEqual(strategy.custom_exit('X',trade,NOW+timedelta(minutes=5),99.6,.004), 'v5_profit_floor')

    @patch.object(Parent, 'custom_exit', return_value='fastk_profit_cover')
    def test_v5_time_limit(self, _):
        strategy, trade = instance(E0V1E64_V5, make_frame()), FakeTrade()
        strategy.custom_exit('X',trade,NOW,99,.01)
        self.assertEqual(strategy.custom_exit('X',trade,NOW+timedelta(minutes=60),98,.02), 'v5_extension_timeout')

    def test_twelve_month_accounting_includes_boundary_force_exit(self):
        from summarize import summarize
        trades = []
        for when, pnl in ((datetime(2025,1,31,tzinfo=timezone.utc),100),
                          (datetime(2025,6,30,tzinfo=timezone.utc),200),
                          (datetime(2026,1,1,tzinfo=timezone.utc),-50)):
            trades.append({'profit_abs':pnl,'profit_ratio':pnl/1000,
                'close_timestamp':int(when.timestamp()*1000),'enter_tag':'short_1',
                'exit_reason':'force_exit','is_short':True})
        result = {'trades':trades,'profit_total':250/8000,'max_drawdown_account':.02,
            'sharpe':1,'starting_balance':8000,'final_balance':8250}
        path = ROOT/'validation/e0v1e64/year-2025/B0/synthetic.zip'
        with patch('summarize.read_result',return_value=(result,path)):
            summary, detail, _ = summarize('B0')
        self.assertEqual(len(detail['monthly']),12)
        self.assertEqual(detail['monthly'][-1]['net_profit'],-50)
        self.assertEqual(detail['monthly'][-1]['end_balance'],8250)
        self.assertEqual(summary['boundary_trades_assigned_december'],1)
        self.assertAlmostEqual(summary['pf'],6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
