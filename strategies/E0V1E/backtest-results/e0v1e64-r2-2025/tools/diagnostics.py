"""Supplemental audit of actual exports; does not optimize any strategy parameter."""
from datetime import datetime, timezone
import json
import math
import statistics
import numpy as np
from run_suite import HERE, OUT, read_result
from summarize import VERSIONS, LABELS, stats


def key(t):
    return t['pair'], t['is_short'], t['open_timestamp']


def compact(t):
    return {k:t[k] for k in ('pair','is_short','enter_tag','open_date','close_date',
        'open_timestamp','close_timestamp','exit_reason','profit_ratio','profit_abs',
        'stake_amount','trade_duration','leverage')}


def block_uncertainty(trades, repeats=5000, block=20):
    """Circular block resampling of equal-stake ratios, not compounded future forecasts."""
    values=np.asarray([t['profit_ratio'] for t in sorted(trades,key=lambda t:t['close_timestamp'])])
    n=len(values)
    rng=np.random.default_rng(20260906)
    evs,pfs=[],[]
    for _ in range(repeats):
        starts=rng.integers(0,n,size=math.ceil(n/block))
        indices=((starts[:,None]+np.arange(block))%n).ravel()[:n]
        sample=values[indices]
        evs.append(float(sample.mean()*100))
        loss=-sample[sample<0].sum()
        if loss>0:
            pfs.append(float(sample[sample>0].sum()/loss))
    return {'method':'circular blocks of 20 consecutive closed trades; 5000 resamples',
        'seed':20260906,'ev_pct_percentile_95':np.quantile(evs,[.025,.975]).tolist(),
        'equal_stake_pf_percentile_95':np.quantile(pfs,[.025,.975]).tolist(),
        'warning':'Descriptive resampling under empirical dependence; NOT future EV bounds, NOT selection-adjusted, NOT an OOS test.'}


def main():
    results={v:read_result(OUT/v)[0] for v in VERSIONS}
    base={key(t):t for t in results['V5']['trades']}
    diagnostics={}
    for version,result in results.items():
        trades=result['trades']
        current={key(t):t for t in trades}
        losses=sorted((t for t in trades if t['profit_abs']<0),key=lambda t:t['profit_abs'])
        by_loss_ratio=sorted(trades,key=lambda t:t['profit_ratio'])[:10]
        changed=[]
        for k in sorted(base.keys() & current.keys()):
            a,b=base[k],current[k]
            if (a['close_timestamp'],a['exit_reason'])!=(b['close_timestamp'],b['exit_reason']):
                changed.append({'baseline':compact(a),'candidate':compact(b),
                    'exit_delay_minutes':(b['close_timestamp']-a['close_timestamp'])/60000,
                    'profit_ratio_delta_pp':100*(b['profit_ratio']-a['profit_ratio'])})
        gross_loss=-sum(t['profit_abs'] for t in losses)
        halves=[]
        boundary=int(datetime(2025,7,1,tzinfo=timezone.utc).timestamp()*1000)
        for label,rows in [('H1',[t for t in trades if t['close_timestamp']<boundary]),
                           ('H2',[t for t in trades if t['close_timestamp']>=boundary])]:
            s=stats(rows)
            s['period']=label
            halves.append(s)
        diagnostics[version]={'label':LABELS[version], 'actual_leverage':sorted({t['leverage'] for t in trades}),
            'worst_10_dollar_losses':[compact(t) for t in losses[:10]],
            'worst_10_ratio_trades':[compact(t) for t in by_loss_ratio],
            'worst_10_share_gross_loss_pct':100*-sum(t['profit_abs'] for t in losses[:10])/gross_loss if gross_loss else 0,
            'halves_realized':halves,'uncertainty':block_uncertainty(trades),
            'changed_common_entries':changed,
            'new_entries':[compact(current[k]) for k in sorted(current.keys()-base.keys())],
            'missing_baseline_entries':[compact(base[k]) for k in sorted(base.keys()-current.keys())]}
    (OUT/'diagnostics.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# V5第二轮：交易差异与不确定性审计','',
        '本页从五份实际结果ZIP计算，不重新拟合策略。所有EV均为历史单笔收益均值。', '',
        '| 版本 | 上半年单笔EV / 等额PF | 下半年单笔EV / 等额PF | 最大10笔占总亏损 | 实际杠杆 |',
        '| --- | ---: | ---: | ---: | --- |']
    for v,d in diagnostics.items():
        cells=[f'{s["ev_pct"]:+.3f}% / {s["equal_stake_pf"]:.3f}' for s in d['halves_realized']]
        lines.append(f'| {v} | '+ ' | '.join(cells)+f' | {d["worst_10_share_gross_loss_pct"]:.2f}% | {d["actual_leverage"]} |')
    lines+=['','## 重抽样敏感性（非未来预测）','',
        '按平仓时间排列，每20笔为连续区块，循环区块重抽样5000次，随机种子20260906。下面是经验分布的2.5%～97.5%分位；未校正反复选优、币池偏差和市场环境变化，不能解释成未来收益的95%保证。', '',
        '| 版本 | 单笔EV区间 | 等额PF区间 |', '| --- | ---: | ---: |']
    for v,d in diagnostics.items():
        e=d['uncertainty']['ev_pct_percentile_95']
        p=d['uncertainty']['equal_stake_pf_percentile_95']
        lines.append(f'| {v} | {e[0]:+.3f}% ～ {e[1]:+.3f}% | {p[0]:.3f} ～ {p[1]:.3f} |')
    for v,d in diagnostics.items():
        lines+=['',f'## {v}：相同入场与仓位占用变化','',
            f'相同入场但退出变化{len(d["changed_common_entries"])}笔；新入场{len(d["new_entries"])}笔；原基准入场未发生{len(d["missing_baseline_entries"])}笔。',
            '退出变化会替换后续交易；不同版本金额基数也不同，不将匹配子集盈亏解释为全策略因果贡献。', '',
            '| 币对 | 入场 | 方向/信号 | 出场理由 | 单笔收益 | 盈亏USDT |', '| --- | --- | --- | --- | ---: | ---: |']
        for t in d['worst_10_dollar_losses']:
            lines.append(f'| {t["pair"]} | {t["open_date"]} | {"空" if t["is_short"] else "多"}/{t["enter_tag"]} | {t["exit_reason"]} | {100*t["profit_ratio"]:+.3f}% | {t["profit_abs"]:+.2f} |')
    lines+=['','完整逐笔变化、新增入场、缺失入场、尾部亏损与抽样结果见[diagnostics.json](year-2025/diagnostics.json)。']
    (HERE/'DIAGNOSTICS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Supplemental audit complete: DIAGNOSTICS.md and year-2025/diagnostics.json')


if __name__=='__main__':
    main()
