"""Trade metrics plus independent 5m-close liquidation-value equity reconstruction."""
from collections import defaultdict
import json
from pathlib import Path
import math
import numpy as np
import pandas as pd
from run_suite import HERE,ROOT,PERIODS,VERSIONS,read_result

LABELS={'V5':'冻结基准','V10':'相对ATR仓位','V11':'近期表现预算','V12':'多单15%灾难止损','V13':'三槽分散持仓'}
STEP=300000


def ms(value):
    return int(pd.Timestamp(value).timestamp()*1000)


def timestamps(series):
    return pd.DatetimeIndex(series).as_unit('ms').asi8


def profit_at(t,rate,funding=0.0):
    return (t['amount']*(rate-t['open_rate'])*(-1 if t['is_short'] else 1)
            -t['amount']*(t['open_rate']*t['fee_open']+rate*t['fee_close'])+funding)


class Prices:
    def __init__(self,directory):
        self.directory=directory
        self.cache={}

    def get(self,pair):
        if pair not in self.cache:
            stem=pair.replace('/','_').replace(':','_')
            frame=pd.read_feather(self.directory/'futures'/f'{stem}-5m-futures.feather',columns=['date','close'])
            qtime=timestamps(frame['date'])+STEP
            close=frame['close'].to_numpy(dtype=float)
            frames=[]
            for kind in ('1h-mark','1h-funding_rate'):
                path=self.directory/'futures'/f'{stem}-{kind}.feather'
                frames.append(pd.read_feather(path,columns=['date','open']) if path.exists() else pd.DataFrame(columns=['date','open']))
            if all(not f.empty for f in frames):
                funds=frames[0].merge(frames[1],on='date',suffixes=('_mark','_fund')).sort_values('date')
                ftime=timestamps(funds['date'])
                prefix=np.r_[0.0,np.cumsum((funds['open_mark']*funds['open_fund']).to_numpy(dtype=float))]
            else:
                ftime=np.array([],dtype=np.int64)
                prefix=np.array([0.0])
            self.cache[pair]=(qtime,close,ftime,prefix)
        return self.cache[pair]


def equity_curve(result,prices):
    start=ms(pd.to_datetime(result['backtest_start'],utc=True))
    end=ms(pd.to_datetime(result['backtest_end'],utc=True))
    grid=np.arange(start,end+1,STEP,dtype=np.int64)
    realized_change=np.zeros(len(grid))
    floating=np.zeros(len(grid))
    counts=np.zeros(len(grid),dtype=int)
    valuation_gaps=set()
    max_accounting_error=0.0
    max_funding_error=0.0
    for t in result['trades']:
        error=abs(profit_at(t,t['close_rate'],t['funding_fees'])-t['profit_abs'])
        max_accounting_error=max(max_accounting_error,error)
        if error>.001:
            raise RuntimeError('Unsupported trade accounting (e.g. partial fills): '+t['pair'])
        opened,closed=t['open_timestamp'],t['close_timestamp']
        exit_idx=int(np.searchsorted(grid,closed))
        if exit_idx>=len(grid):
            raise RuntimeError('Close outside reported range')
        realized_change[exit_idx]+=t['profit_abs']
        lo,hi=int(np.searchsorted(grid,opened)),int(np.searchsorted(grid,closed))
        if lo>=hi:
            continue
        held=grid[lo:hi]
        qt,qc,ft,fc=prices.get(t['pair'])
        qi=np.searchsorted(qt,held,side='right')-1
        if np.any(qi<0):
            raise RuntimeError('Missing valuation price at entry')
        rate=qc[qi].copy()
        rate[held==opened]=t['open_rate']
        if np.any((held-qt[qi]>STEP)&(held!=opened)):
            valuation_gaps.add(t['pair'])
        begin=np.searchsorted(ft,opened,side='left')
        funding=(fc[np.searchsorted(ft,held,side='right')]-fc[begin])*t['amount']*(1 if t['is_short'] else -1)
        funding_at_close=(fc[np.searchsorted(ft,closed,side='right')]-fc[begin])*t['amount']*(1 if t['is_short'] else -1)
        max_funding_error=max(max_funding_error,abs(funding_at_close-t['funding_fees']))
        if abs(funding_at_close-t['funding_fees'])>.01:
            raise RuntimeError('Funding reconstruction mismatch: '+t['pair'])
        floating[lo:hi]+=profit_at(t,rate,funding)
        counts[lo:hi]+=1
    realized=result['starting_balance']+np.cumsum(realized_change)
    nav=realized+floating
    if abs(nav[-1]-result['final_balance'])>.001:
        raise RuntimeError('Equity does not reconcile with final wallet')
    peak=np.maximum.accumulate(np.r_[result['starting_balance'],nav])[1:]
    dd=1-nav/peak
    trough_idx=int(np.argmax(dd))
    peak_idx=int(np.argmax(nav[:trough_idx+1]))
    daily_indices=np.r_[np.arange(0,len(grid),288),len(grid)-1]
    daily_indices=np.unique(daily_indices)
    daily_nav=nav[daily_indices].copy()
    # Initial capital, then each UTC midnight valuation; first-entry costs appear in day one.
    daily_nav[0]=result['starting_balance']
    returns=daily_nav[1:]/daily_nav[:-1]-1
    return pd.DataFrame({'date':pd.to_datetime(grid,unit='ms',utc=True),'realized_equity':realized,
                         'liquidation_value':nav,'open_trades':counts}),{
        'mtm_max_drawdown_pct':float(dd.max()*100),'min_nav':float(nav.min()),
        'mtm_peak_date':str(pd.to_datetime(grid[peak_idx],unit='ms',utc=True)),
        'mtm_trough_date':str(pd.to_datetime(grid[trough_idx],unit='ms',utc=True)),
        'mtm_peak_value':float(peak[trough_idx]),'mtm_trough_value':float(nav[trough_idx]),
        'daily_volatility_pct':float(returns.std(ddof=1)*100) if len(returns)>1 else 0.0,
        'worst_daily_return_pct':float(returns.min()*100),
        'max_concurrent_positions':int(counts.max()),'valuation_gap_pairs':sorted(valuation_gaps),
        'max_trade_pnl_reconciliation_error':max_accounting_error,
        'max_funding_reconciliation_error':max_funding_error,
        'daily':[{'date':str(pd.to_datetime(grid[i],unit='ms',utc=True)),
                  'equity':float(v)} for i,v in zip(daily_indices,daily_nav)]}


def basic(result):
    rows=result['trades']
    pnl=np.array([t['profit_abs'] for t in rows])
    ratios=np.array([t['profit_ratio'] for t in rows])
    loss=-pnl[pnl<0].sum()
    return {'trades':len(rows),'return_pct':result['profit_total']*100,
        'pf':float(pnl[pnl>0].sum()/loss),'equal_stake_pf':float(ratios[ratios>0].sum()/-ratios[ratios<0].sum()),
        'ev_pct':float(ratios.mean()*100),'engine_drawdown_pct':result['max_drawdown_account']*100,
        'worst_trade_pct':float(ratios.min()*100),'worst_trade_usdt':float(pnl.min()),
        'win_rate_pct':float((pnl>0).mean()*100),'final_balance':result['final_balance'],
        'pairlist_count':len(result['pairlist']),'traded_pairs':len({t['pair'] for t in rows}),
        'funding_total':sum(t['funding_fees'] for t in rows),
        'funded_trades':sum(t['funding_fees']!=0 for t in rows),
        'actual_leverage':sorted({t['leverage'] for t in rows})}


def compare(summary,baseline):
    summary['terminal_equity_improvement_pct']=100*(summary['final_balance']/baseline['final_balance']-1)
    summary['pf_delta']=summary['pf']-baseline['pf']
    summary['engine_dd_delta_pp']=summary['engine_drawdown_pct']-baseline['engine_drawdown_pct']
    summary['mtm_dd_delta_pp']=summary['mtm_max_drawdown_pct']-baseline['mtm_max_drawdown_pct']
    summary['volatility_delta_pp']=summary['daily_volatility_pct']-baseline['daily_volatility_pct']
    summary['material_return']=summary['terminal_equity_improvement_pct']>=10-1e-7
    summary['no_risk_worsening']=(summary['engine_dd_delta_pp']<=1e-7 and summary['mtm_dd_delta_pp']<=1e-7)
    summary['meets_target']=(summary['material_return'] and summary['no_risk_worsening'] and summary['pf_delta']>=-1e-7)


def main():
    all_results={}
    for period,(directory,timerange) in PERIODS.items():
        prices=Prices(ROOT/'user_data/data'/directory)
        records={}
        for version in VERSIONS:
            result,path,name=read_result(HERE/period/version)
            summary=basic(result)
            curve,risk=equity_curve(result,prices)
            summary.update({k:v for k,v in risk.items() if k!='daily'})
            summary.update({'version':version,'label':LABELS[version],
                'backtest_start':result['backtest_start'],'backtest_end':result['backtest_end'],
                'baseline_reused':period=='year-2025' and version=='V5'})
            curve.to_feather(HERE/period/version/'equity_5m.feather')
            (HERE/period/version/'equity_daily.json').write_text(json.dumps(risk['daily'],indent=2))
            records[version]=result['trades']
            all_results.setdefault(period,{})[version]=summary
        base=all_results[period]['V5']
        base_entries={(t['pair'],t['is_short'],t['open_timestamp']):t for t in records['V5']}
        for version,s in all_results[period].items():
            compare(s,base)
            current={(t['pair'],t['is_short'],t['open_timestamp']):t for t in records[version]}
            common=base_entries.keys()&current.keys()
            s['matched_entries']=len(common)
            s['changed_exits']=sum((current[k]['close_timestamp'],current[k]['exit_reason'])!=
                                   (base_entries[k]['close_timestamp'],base_entries[k]['exit_reason']) for k in common)
            s['new_entries']=len(current.keys()-base_entries.keys())
            s['missing_baseline_entries']=len(base_entries.keys()-current.keys())
        print(period,json.dumps(all_results[period],ensure_ascii=False),flush=True)
    (HERE/'comparison.json').write_text(json.dumps(all_results,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 第三轮结果：V5基准与V10～V13','',
        '九次新回测，加一份严格校验后复用的V5全年结果。所有版本保持V5的60分钟延长逻辑；V6仅保留为历史参考。',
        '门槛事先固定：期末权益提高至少10%，金额PF不降，引擎回撤和5m收盘估值回撤均不增。不是收益承诺。']
    for period,results in all_results.items():
        title='2026年4月1日～6月29日：90天，计入资金费' if period=='apr-jun-2026' else '2025全年：旧口径，未计实际资金费'
        lines+=['','## '+title,'',
                '| 版本 | 收益 | PF | 单笔EV | 引擎回撤 | 5m收盘估值回撤 | 日波动 | 最差单笔 | 笔数 |',
                '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for v,s in results.items():
            lines.append(f'| {v} | {s["return_pct"]:+.2f}% | {s["pf"]:.3f} | {s["ev_pct"]:+.3f}% | '
                         f'{s["engine_drawdown_pct"]:.2f}% | {s["mtm_max_drawdown_pct"]:.2f}% | '
                         f'{s["daily_volatility_pct"]:.2f}% | {s["worst_trade_pct"]:.2f}% | {s["trades"]} |')
        lines+=['','| 候选 | 期末权益较V5 | PF变化 | 估值回撤变化 | 达到事前门槛 |',
                 '| --- | ---: | ---: | ---: | --- |']
        for v,s in results.items():
            if v!='V5':
                lines.append(f'| {v} | {s["terminal_equity_improvement_pct"]:+.2f}% | {s["pf_delta"]:+.3f} | '
                             f'{s["mtm_dd_delta_pp"]:+.2f}个百分点 | {"是" if s["meets_target"] else "否"} |')
    both=[v for v in VERSIONS[1:] if all(all_results[p][v]['meets_target'] for p in PERIODS)]
    lines+=['','## 结论与限制','',
        '两段都达到事前门槛的候选：'+('、'.join(both) if both else '没有')+'。',
        '保持V5为基准，不自动替换服务器。即使某版达标，也仍只是历史候选；2025缺资金费，90天与此前6月样本重合，不能宣称已证明长期收益。',
        '5m收盘估值曲线按导出成交量、开平仓费用、历史资金费和已完成5m收盘价重建未平仓浮盈亏，并与逐笔净利润和期末余额核对；不是逐tick盘中最低权益，也没有补入滑点。引擎回撤与该估值回撤口径不同，不混用。',
        '增加持仓会改变交易集合；仓位版改变金额PF不一定改善单笔信号。版本间替换交易数、等额PF、持仓并发度及核对误差见comparison.json。',
        '完整源码、参数、原始ZIP、数据及输入哈希均保留；未删除失利版本。', '',
        '[事前规则](README.md) · [完整数值](comparison.json) · [预审证据](PREFLIGHT.json)']
    (HERE/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
