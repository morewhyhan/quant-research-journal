"""Second-round behavior, inheritance, causal timing and real parameter loading."""
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
SOURCE = ROOT / 'my-strategies/E0V1E64_R2'
sys.path.insert(0, str(SOURCE))
from E0V1E_v3_equity60_reserve40 import E0V1E_v3_equity60_reserve40 as Parent
from E0V1E64_V5 import E0V1E64_V5
from E0V1E64_V6 import E0V1E64_V6
from E0V1E64_V7 import E0V1E64_V7
from E0V1E64_V8 import E0V1E64_V8
from E0V1E64_V9 import E0V1E64_V9

NOW = datetime(2025, 6, 1, 12, tzinfo=timezone.utc)


class FakeTrade:
    id = 1000001
    is_short = True
    open_rate = 100.0
    enter_tag = 'short_1'
    open_date_utc = NOW - timedelta(hours=5)
    max_rate = 10000.0
    min_rate = 1.0

    def __init__(self):
        self.data = {}

    def calc_profit_ratio(self, rate):
        return (100.0 - rate) / 100.0

    def get_custom_data(self, key, default=None):
        return self.data.get(key, default)

    def set_custom_data(self, key, value):
        self.data[key] = value


def frame():
    return pd.DataFrame({'date':pd.date_range(end=NOW-timedelta(minutes=5), periods=13, freq='5min'),
        'high':[106.0]*13, 'close':[104.0]*13, 'ma120':list(range(113,100,-1)),
        'ma240':[110.0]*13, 'fastk':[20.0]*13, 'cci':[0.0]*13})


def instance(cls, data=None):
    strategy = cls({})
    strategy.dp = SimpleNamespace(get_analyzed_dataframe=lambda *a, **kw:(data, None))
    strategy.wallets = SimpleNamespace(get_total_stake_amount=lambda:970.0)
    strategy._peak_tradable_balance = 1400.0
    return strategy


class TestSecondRound(unittest.TestCase):
    def test_frozen_dependencies_identical_modulo_newlines(self):
        for name in ('E0V1E_v3.py','E0V1E_v3_equity60_reserve40.py',
                     'research_common.py','E0V1E64_V1.py','E0V1E64_V4.py','E0V1E64_V5.py'):
            self.assertEqual((SOURCE/name).read_text(), (ROOT/'my-strategies/E0V1E64'/name).read_text())

    def test_real_parameter_loading(self):
        from freqtrade.resolvers import StrategyResolver
        expected = json.loads((SOURCE/'E0V1E64_V5.json').read_text())['params']
        for version in ('V5','V6','V7','V8','V9'):
            cfg = {'strategy':'E0V1E64_'+version,'strategy_path':str(SOURCE),
                   'user_data_dir':ROOT/'user_data','stake_currency':'USDT',
                   'stake_amount':'unlimited','max_open_trades':1,'trading_mode':'futures'}
            strategy = StrategyResolver.load_strategy(cfg)
            strategy.ft_load_hyper_params(False)
            for section in ('buy','sell'):
                for key,value in expected[section].items():
                    self.assertAlmostEqual(getattr(strategy,key).value,value,msg=version+key)
            self.assertEqual(strategy.stoploss,-.25)
            self.assertFalse(strategy.trailing_stop)

    @patch.object(Parent,'custom_exit',return_value='fastk_profit_cover')
    def test_v6_only_changes_timeout(self, _):
        base, longer = instance(E0V1E64_V5,frame()), instance(E0V1E64_V6,frame())
        t0,t1 = FakeTrade(),FakeTrade()
        self.assertIsNone(base.custom_exit('X',t0,NOW,99,.01))
        self.assertIsNone(longer.custom_exit('X',t1,NOW,99,.01))
        self.assertEqual(base.custom_exit('X',t0,NOW+timedelta(minutes=60),98,.02),'v5_extension_timeout')
        self.assertIsNone(longer.custom_exit('X',t1,NOW+timedelta(minutes=60),98,.02))
        self.assertEqual(longer.custom_exit('X',t1,NOW+timedelta(minutes=120),98,.02),'v5_extension_timeout')

    @patch.object(Parent,'custom_exit',return_value='fastk_profit_cover')
    def test_v7_tighter_floor_and_same_peak_observation(self, _):
        base,tight = instance(E0V1E64_V5,frame()),instance(E0V1E64_V7,frame())
        t0,t1 = FakeTrade(),FakeTrade()
        base.custom_exit('X',t0,NOW,98,.02)
        tight.custom_exit('X',t1,NOW,98,.02)
        self.assertIsNone(base.custom_exit('X',t0,NOW+timedelta(minutes=5),98.8,.012))
        self.assertEqual(tight.custom_exit('X',t1,NOW+timedelta(minutes=5),98.8,.012),'v5_profit_floor')
        self.assertEqual(t1.data['v5_extension']['peak'],.02)

    @patch.object(Parent,'custom_exit',return_value='fastk_profit_cover')
    def test_gap_can_cross_soft_floor(self, _):
        strategy,trade=instance(E0V1E64_V7,frame()),FakeTrade()
        strategy.custom_exit('X',trade,NOW,98,.02)
        self.assertEqual(strategy.custom_exit('X',trade,NOW+timedelta(minutes=5),101,-.01),'v5_profit_floor')

    def test_v8_short_recovery_ignores_engine_and_current_bar_extrema(self):
        data=frame()
        row=data.iloc[-1].copy()
        row['date'],row['high']=NOW,200.0
        data=pd.concat([data,pd.DataFrame([row])],ignore_index=True)
        strategy=instance(E0V1E64_V8,data)
        self.assertIsNone(strategy.custom_exit('X',FakeTrade(),NOW,104,-.04))
        data.loc[5,'high']=112.0
        self.assertEqual(strategy.custom_exit('X',FakeTrade(),NOW,104,-.04),'v1_cci_loss_cover')

    def test_v8_ignores_pre_entry_adverse_high(self):
        data=frame()
        data.loc[0,'high']=112.0
        trade=FakeTrade()
        trade.open_date_utc=NOW-timedelta(minutes=30)
        self.assertIsNone(instance(E0V1E64_V8,data).custom_exit('X',trade,NOW,104,-.04))

    def test_v8_still_delays_short_profit_exit(self):
        data=frame()
        data.loc[12,'fastk']=0.0
        trade=FakeTrade()
        strategy=instance(E0V1E64_V8,data)
        self.assertIsNone(strategy.custom_exit('X',trade,NOW,99,.01))
        self.assertIn('v5_extension',trade.data)
        self.assertEqual(strategy.custom_exit('X',trade,NOW+timedelta(minutes=5),99.6,.004),'v5_profit_floor')

    @patch.object(Parent,'custom_exit',return_value='long-parent-exit')
    def test_v8_delegates_long_original_exit(self, _):
        trade=FakeTrade()
        trade.is_short=False
        self.assertEqual(instance(E0V1E64_V8,frame()).custom_exit('X',trade,NOW,104,-.04),'long-parent-exit')

    def test_v9_stake_weights_and_available_cap(self):
        strategy=instance(E0V1E64_V9)
        args=('X',NOW,100,970,1,970,1)
        self.assertAlmostEqual(strategy.custom_stake_amount(*args,'short_1','short'),873)
        self.assertAlmostEqual(strategy.custom_stake_amount(*args,'short_new','short'),970)
        self.assertAlmostEqual(strategy.custom_stake_amount(*args,'buy_1','long'),970)
        strategy._peak_tradable_balance=970
        self.assertAlmostEqual(strategy.custom_stake_amount(*args,'short_new','short'),660)
        self.assertIs(E0V1E64_V9.custom_exit,E0V1E64_V5.custom_exit)

    def test_all_variants_block_live_mode(self):
        for cls in (E0V1E64_V5,E0V1E64_V6,E0V1E64_V7,E0V1E64_V8,E0V1E64_V9):
            with self.assertRaises(RuntimeError):
                cls({'runmode':'live'}).bot_start()


if __name__=='__main__':
    unittest.main(verbosity=2)
