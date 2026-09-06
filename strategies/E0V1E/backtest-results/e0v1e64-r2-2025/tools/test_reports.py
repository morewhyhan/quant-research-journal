"""Pure synthetic tests for report accounting; no expensive backtest required."""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from run_suite import ROOT, HERE
from summarize import stats, summarize
from diagnostics import block_uncertainty


class TestReports(unittest.TestCase):
    def test_ev_and_two_pf_definitions(self):
        result=stats([{'profit_abs':20,'profit_ratio':.01},
                      {'profit_abs':-10,'profit_ratio':-.01}])
        self.assertEqual(result['pf'],2)
        self.assertEqual(result['equal_stake_pf'],1)
        self.assertEqual(result['ev_pct'],0)

    def test_december_includes_exact_end_boundary_once(self):
        trades=[]
        for date,pnl in ((datetime(2025,1,31,tzinfo=timezone.utc),100),
                         (datetime(2025,6,30,tzinfo=timezone.utc),200),
                         (datetime(2026,1,1,tzinfo=timezone.utc),-50)):
            trades.append({'profit_abs':pnl,'profit_ratio':pnl/1000,
                'close_timestamp':int(date.timestamp()*1000),'enter_tag':'short_1',
                'exit_reason':'force_exit','is_short':True})
        raw={'trades':trades,'profit_total':250/8000,'max_drawdown_account':.02,
             'sharpe':1,'starting_balance':8000,'final_balance':8250}
        with patch('summarize.read_result',return_value=(raw,HERE/'year-2025/V5/synthetic.zip')):
            summary,detail,_=summarize('V5')
        self.assertEqual(len(detail['monthly']),12)
        self.assertEqual(detail['monthly'][-1]['net_profit'],-50)
        self.assertEqual(detail['monthly'][-1]['end_balance'],8250)
        self.assertEqual(summary['boundary_trades_assigned_december'],1)
        self.assertAlmostEqual(summary['pf'],6)

    def test_block_resampling_is_repeatable_and_not_compounding(self):
        trades=[{'profit_ratio':(.02 if i%2==0 else -.01),'close_timestamp':i} for i in range(40)]
        a=block_uncertainty(trades,repeats=20,block=20)
        b=block_uncertainty(trades,repeats=20,block=20)
        self.assertEqual(a,b)
        for value in a['ev_pct_percentile_95']:
            self.assertAlmostEqual(value,.5)
        for value in a['equal_stake_pf_percentile_95']:
            self.assertAlmostEqual(value,2)


if __name__=='__main__':
    unittest.main(verbosity=2)
