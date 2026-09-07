"""Synthetic MTM, funding, shared-position and fixed decision-gate tests."""
import unittest
import numpy as np
from summarize import equity_curve,profit_at,compare,STEP


class FakePrices:
    def get(self,pair):
        return (np.array([0,STEP,2*STEP]),np.array([100.,105.,110.]),
                np.array([STEP]),np.array([0.,.01]))


class ReportTests(unittest.TestCase):
    def test_single_long_valuation_and_funding_reconcile(self):
        t={'pair':'X','open_timestamp':0,'close_timestamp':2*STEP,'amount':1,
           'open_rate':100.,'close_rate':110.,'fee_open':.0005,'fee_close':.0005,
           'funding_fees':-.01,'is_short':False,'profit_abs':9.885}
        r={'trades':[t],'starting_balance':1000.,'final_balance':1009.885,
           'backtest_start':'1970-01-01 00:00:00','backtest_end':'1970-01-01 00:10:00'}
        curve,risk=equity_curve(r,FakePrices())
        self.assertAlmostEqual(curve.iloc[0]['liquidation_value'],999.9)
        self.assertAlmostEqual(curve.iloc[1]['liquidation_value'],1004.8875)
        self.assertAlmostEqual(curve.iloc[2]['liquidation_value'],1009.885)
        self.assertLess(risk['max_funding_reconciliation_error'],1e-9)

    def test_short_fee_direction(self):
        t={'amount':1,'open_rate':100.,'fee_open':.0005,'fee_close':.0005,'is_short':True}
        self.assertAlmostEqual(profit_at(t,90.,.01),9.915)

    def test_two_positions_are_combined_in_one_wallet(self):
        long={'pair':'X','open_timestamp':0,'close_timestamp':2*STEP,'amount':1,
              'open_rate':100.,'close_rate':110.,'fee_open':.0005,'fee_close':.0005,
              'funding_fees':-.01,'is_short':False,'profit_abs':9.885}
        short=dict(long,pair='Y',is_short=True,funding_fees=.01,profit_abs=-10.095)
        r={'trades':[long,short],'starting_balance':1000.,'final_balance':999.79,
           'backtest_start':'1970-01-01 00:00:00','backtest_end':'1970-01-01 00:10:00'}
        curve,risk=equity_curve(r,FakePrices())
        self.assertEqual(risk['max_concurrent_positions'],2)
        self.assertAlmostEqual(curve.iloc[1]['liquidation_value'],999.795)
        self.assertAlmostEqual(curve.iloc[-1]['liquidation_value'],999.79)

    def test_target_is_equity_gain_not_return_percentage_points(self):
        base={'final_balance':10000,'pf':1.5,'engine_drawdown_pct':20,'mtm_max_drawdown_pct':25,'daily_volatility_pct':2}
        s=dict(base,final_balance=10500,pf=1.6,engine_drawdown_pct=19,mtm_max_drawdown_pct=24)
        compare(s,base)
        self.assertFalse(s['meets_target'])
        s['final_balance']=11000
        compare(s,base)
        self.assertTrue(s['meets_target'])
        s['mtm_max_drawdown_pct']=26
        compare(s,base)
        self.assertFalse(s['meets_target'])


if __name__=='__main__':
    unittest.main(verbosity=2)
