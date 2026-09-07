"""Parameter, sizing, timing, absolute-stop and shared-slot regression tests."""
from datetime import datetime,timedelta,timezone
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'my-strategies/E0V1E64_R3'
sys.path.insert(0,str(SOURCE))
from E0V1E64_V5 import E0V1E64_V5
from E0V1E64_V10 import E0V1E64_V10
from E0V1E64_V11 import E0V1E64_V11
from E0V1E64_V12 import E0V1E64_V12
from E0V1E64_V13 import E0V1E64_V13
from freqtrade.persistence import Trade

NOW=datetime(2026,4,1,12,tzinfo=timezone.utc)
CLASSES=(E0V1E64_V5,E0V1E64_V10,E0V1E64_V11,E0V1E64_V12,E0V1E64_V13)


def instance(cls,data=None):
    strategy=cls({})
    strategy.dp=SimpleNamespace(get_analyzed_dataframe=lambda *a,**kw:(data,None))
    strategy.wallets=SimpleNamespace(get_total_stake_amount=lambda:970.0)
    strategy._peak_tradable_balance=970.0
    return strategy


def frame():
    return pd.DataFrame({'date':[NOW-timedelta(minutes=5),NOW],
                         'r3_atr_pct':[.02,1000.0],'r3_atr_reference':[.01,.00001]})


def past_trade(index,profit,when=NOW-timedelta(minutes=5)):
    return SimpleNamespace(id=index,close_date_utc=when,close_profit=profit)


class ThirdRoundTests(unittest.TestCase):
    def test_frozen_v5_dependencies(self):
        for name in ('E0V1E_v3.py','E0V1E_v3_equity60_reserve40.py','research_common.py','E0V1E64_V5.py'):
            self.assertEqual((SOURCE/name).read_text(),(ROOT/'my-strategies/E0V1E64_R2'/name).read_text())

    def test_parameter_loading_and_only_slot_override(self):
        from freqtrade.resolvers import StrategyResolver
        expected=json.loads((SOURCE/'E0V1E64_V5.json').read_text())['params']
        for cls in CLASSES:
            slots=3 if cls is E0V1E64_V13 else 1
            cfg={'strategy':cls.__name__,'strategy_path':str(SOURCE),'user_data_dir':ROOT/'user_data',
                 'stake_currency':'USDT','stake_amount':'unlimited','max_open_trades':slots,'trading_mode':'futures'}
            strategy=StrategyResolver.load_strategy(cfg)
            strategy.ft_load_hyper_params(False)
            for section in ('buy','sell'):
                for key,value in expected[section].items():
                    self.assertAlmostEqual(getattr(strategy,key).value,value,msg=cls.__name__+key)
            self.assertEqual(strategy.stoploss,-.25)
            self.assertEqual(strategy.max_open_trades,slots)
            self.assertEqual(strategy.max_extension_minutes,60)

    def test_v10_bounds(self):
        self.assertEqual(E0V1E64_V10.volatility_multiplier(.04,.01),.5)
        self.assertEqual(E0V1E64_V10.volatility_multiplier(.005,.01),1.25)
        self.assertEqual(E0V1E64_V10.volatility_multiplier(float('nan'),.01),1)

    def test_v10_uses_completed_frame_and_caps_available(self):
        s=instance(E0V1E64_V10,frame())
        args=('X',NOW,100,970,1,970,1,'short_1','short')
        self.assertAlmostEqual(s.custom_stake_amount(*args),300)
        data=frame()
        data.loc[0,'r3_atr_pct']=.005
        s=instance(E0V1E64_V10,data)
        self.assertAlmostEqual(s.custom_stake_amount(*args),750)
        s._peak_tradable_balance=1400
        self.assertAlmostEqual(s.custom_stake_amount(*args),970)

    def test_v11_fixed_regime_boundaries(self):
        f=E0V1E64_V11.budget_fraction
        self.assertEqual(f([.02]*29,0),.6)
        self.assertEqual(f([.02]*30,0),.9)
        self.assertEqual(f([-.01]*30,0),.4)
        self.assertEqual(f([.02]*30,.1),.6)
        self.assertEqual(f([.02]*30,.2),.4)
        self.assertEqual(f([0.0]*30,0),.4)

    @patch.object(Trade,'get_trades_proxy')
    def test_v11_excludes_future_closed_trades_and_sorts(self,mock):
        mock.return_value=[past_trade(i,.02) for i in range(29)]+[past_trade(30,-.9,NOW+timedelta(hours=1))]
        s=instance(E0V1E64_V11)
        args=('X',NOW,100,970,1,970,1,'short_1','short')
        self.assertAlmostEqual(s.custom_stake_amount(*args),600)
        mock.return_value=[past_trade(i,.02) for i in reversed(range(30))]+[past_trade(40,-.9,NOW+timedelta(hours=1))]
        self.assertAlmostEqual(s.custom_stake_amount(*args),900)

    def test_v12_absolute_long_stop_not_trailing_15pct(self):
        t=SimpleNamespace(is_short=False,open_rate=100.0,leverage=1.0,enter_tag='buy_1')
        s=instance(E0V1E64_V12)
        for rate,profit in ((100,0),(90,-.1),(102,.02)):
            distance=s.custom_stoploss('X',t,NOW,rate,profit)
            self.assertAlmostEqual(rate*(1-distance),85)

    def test_v12_preserves_profit_protection_and_short(self):
        t=SimpleNamespace(is_short=False,open_rate=100.0,leverage=1.0,enter_tag='buy_1')
        s=instance(E0V1E64_V12)
        self.assertAlmostEqual(s.custom_stoploss('X',t,NOW,106,.06),.002)
        t.is_short=True
        self.assertEqual(s.custom_stoploss('X',t,NOW,104,-.04),-.15)
        self.assertEqual(s.custom_stoploss('X',t,NOW,94,.06),-.02)

    @patch.object(Trade,'get_trades_proxy')
    def test_v13_direction_cap_and_no_future_inventory(self,mock):
        mock.return_value=[SimpleNamespace(is_short=True,open_date_utc=NOW-timedelta(minutes=5)) for _ in range(2)]
        s=instance(E0V1E64_V13)
        args=('X','market',1,100,'GTC',NOW,'short_1')
        self.assertFalse(s.confirm_trade_entry(*args,'short'))
        self.assertTrue(s.confirm_trade_entry(*args,'long'))
        mock.return_value=[SimpleNamespace(is_short=True,open_date_utc=NOW+timedelta(minutes=5)) for _ in range(2)]
        self.assertTrue(s.confirm_trade_entry(*args,'short'))

    def test_v13_three_slots_share_capital(self):
        s=instance(E0V1E64_V13)
        amount=s.custom_stake_amount('X',NOW,100,970/3,1,970,1,'short_1','short')
        self.assertAlmostEqual(amount*3,600)
        s._peak_tradable_balance=1400
        amount=s.custom_stake_amount('X',NOW,100,970/3,1,970,1,'short_1','short')
        self.assertAlmostEqual(amount*3,970)

    def test_all_research_versions_reject_live(self):
        for cls in CLASSES:
            with self.assertRaises(RuntimeError):
                cls({'runmode':'live'}).bot_start()


if __name__=='__main__':
    unittest.main(verbosity=2)
