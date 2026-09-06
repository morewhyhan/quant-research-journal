#!/usr/bin/env python3
"""Summarize five second-round exports with a strict twelve-month window."""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from run_suite import OUT, HERE, read_result

VERSIONS = ('V5', 'V6', 'V7', 'V8', 'V9')
LABELS = {'V5':'冻结基准', 'V6':'延长至120分钟', 'V7':'保留70%峰值利润',
          'V8':'空单亏损回升退出校正', 'V9':'空单信号仓位调整'}


def stats(trades):
    wins = [t for t in trades if t['profit_abs'] > 0]
    losses = [t for t in trades if t['profit_abs'] < 0]
    gain = sum(t['profit_abs'] for t in wins)
    loss = -sum(t['profit_abs'] for t in losses)
    ratio_gain = sum(max(t['profit_ratio'], 0) for t in trades)
    ratio_loss = -sum(min(t['profit_ratio'], 0) for t in trades)
    return {'trades':len(trades), 'wins':len(wins), 'losses':len(losses),
            'traded_pairs':len({t['pair'] for t in trades if 'pair' in t}),
            'win_rate_pct':100*len(wins)/len(trades) if trades else 0,
            'gross_profit':gain, 'gross_loss':loss, 'net_profit':gain-loss,
            'pf':gain/loss if loss else None,
            'equal_stake_pf':ratio_gain/ratio_loss if ratio_loss else None,
            'ev_pct':100*statistics.fmean(t['profit_ratio'] for t in trades) if trades else 0,
            'avg_win_pct':100*statistics.fmean(t['profit_ratio'] for t in wins) if wins else 0,
            'avg_loss_pct':100*statistics.fmean(t['profit_ratio'] for t in losses) if losses else 0}


def summarize(version):
    result, path = read_result(OUT/version)
    trades = result['trades']
    summary = stats(trades)
    summary.update({'version':version,'label':LABELS[version], 'result_file':str(path.relative_to(HERE)),
        'return_pct':100*result['profit_total'], 'max_drawdown_pct':100*result['max_drawdown_account'],
        'sharpe':result['sharpe'], 'starting_balance':result['starting_balance'],
        'final_balance':result['final_balance'], 'geometric_monthly_pct':100*((1+result['profit_total'])**(1/12)-1)})
    grouped = {}
    for key in ('enter_tag','exit_reason','is_short'):
        buckets = defaultdict(list)
        for trade in trades:
            buckets[str(trade[key])].append(trade)
        grouped[key] = {k:stats(v) for k,v in sorted(buckets.items())}
    months = {m:[] for m in range(1,13)}
    boundary_trades = 0
    for trade in trades:
        dt = datetime.fromtimestamp(trade['close_timestamp']/1000, timezone.utc)
        if dt == datetime(2026,1,1,tzinfo=timezone.utc):
            month = 12
            boundary_trades += 1
        elif dt.year == 2025:
            month = dt.month
        else:
            raise ValueError(f'Unexpected close date: {dt}')
        months[month].append(trade)
    balance = result['starting_balance']
    monthly = []
    for month, rows in months.items():
        item = stats(rows)
        item.update({'month':f'2025-{month:02d}', 'start_balance':balance,
                     'return_pct':100*item['net_profit']/balance})
        balance += item['net_profit']
        item['end_balance'] = balance
        monthly.append(item)
    assert abs(balance-result['final_balance']) < .001
    quarterly = []
    for q in range(4):
        rows = sum((months[m] for m in range(q*3+1,q*3+4)), [])
        item = stats(rows)
        start = monthly[q*3]['start_balance']
        item.update({'quarter':f'2025Q{q+1}', 'return_pct':100*item['net_profit']/start})
        quarterly.append(item)
    summary['positive_months'] = sum(m['net_profit'] > 0 for m in monthly)
    summary['boundary_trades_assigned_december'] = boundary_trades
    return summary, {'groups':grouped,'monthly':monthly,'quarterly':quarterly}, trades


def fmt(value, digits=3):
    return '—' if value is None else f'{value:.{digits}f}'


def main():
    summaries, details, records = [], {}, {}
    for version in VERSIONS:
        summary, detail, trades = summarize(version)
        summaries.append(summary)
        details[version], records[version] = detail, trades
    baseline = summaries[0]
    for summary in summaries:
        summary['return_delta_pp'] = summary['return_pct']-baseline['return_pct']
        summary['pf_delta'] = summary['pf']-baseline['pf']
        summary['improves_both'] = (summary['return_delta_pp'] > 1e-6 and summary['pf_delta'] > 1e-6)
    def key(t):
        return (t['pair'], t['is_short'], t['open_timestamp'])
    old = {key(t):t for t in records['V5']}
    for version in VERSIONS:
        current = {key(t):t for t in records[version]}
        common = old.keys() & current.keys()
        same_exit = sum(old[k]['close_timestamp']==current[k]['close_timestamp']
                        and old[k]['exit_reason']==current[k]['exit_reason'] for k in common)
        details[version]['sequence_comparison'] = {'matched_entries':len(common),
            'matched_entries_same_exit':same_exit, 'matched_entries_changed_exit':len(common)-same_exit,
            'new_entries':len(current.keys()-old.keys()), 'missing_baseline_entries':len(old.keys()-current.keys())}
        changed = [k for k in common if old[k]['close_timestamp'] != current[k]['close_timestamp']
                   or old[k]['exit_reason'] != current[k]['exit_reason']]
        details[version]['matched_changed_exit_outcomes'] = {
            'count':len(changed),
            'baseline_winners_become_losses':sum(old[k]['profit_ratio']>0 and current[k]['profit_ratio']<0 for k in changed),
            'baseline_losers_improved':sum(old[k]['profit_ratio']<0 and current[k]['profit_ratio']>old[k]['profit_ratio'] for k in changed),
            'mean_baseline_ratio_pct':100*statistics.fmean(old[k]['profit_ratio'] for k in changed) if changed else None,
            'mean_candidate_ratio_pct':100*statistics.fmean(current[k]['profit_ratio'] for k in changed) if changed else None,
            'note':'Only common entries; excludes replacement trades and differing account size. Not whole-strategy causal attribution.'}
    validation = json.loads((OUT/'baseline_validation.json').read_text())
    payload = {'baseline_validation':validation, 'summaries':summaries, 'details':details}
    (OUT/'comparison.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines = ['# E0V1E64第二轮：以V5为基准，V6～V9独立优化','',
        '五个独立进程、同一198项配置白名单（196项有5m数据）、8000 USDT、单持仓、5m普通回测、单边手续费0.05%、相同离线市场模拟。',
        'V5复现检查：'+('全部通过，855笔进出记录与上一轮V5一致。' if all(validation.values()) else '未通过！'),'',
        '| 版本 | 改动 | 收益率 | PF(金额) | 等额单笔PF | 单笔EV | 最大回撤 | 胜率 | 交易数 |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for s in summaries:
        lines.append(f'| {s["version"]} | {s["label"]} | {s["return_pct"]:+.2f}% | {fmt(s["pf"])} | '
                     f'{fmt(s["equal_stake_pf"])} | {s["ev_pct"]:+.3f}% | {s["max_drawdown_pct"]:.2f}% | '
                     f'{s["win_rate_pct"]:.2f}% | {s["trades"]} |')
    improved = [s for s in summaries[1:] if s['improves_both']]
    lines += ['', '同时改善全年收益和金额PF：'+('、'.join(s['version'] for s in improved) if improved else '没有版本')+'。']
    if len(improved) == 1:
        winner = improved[0]['version']
        lines += ['', f'本轮只有{winner}同时超过V5的全年收益和金额PF，列为下一阶段研究候选。',
                  '这不是生产部署结论；基准继续保留，待其他时间段验证。']
    lines += ['', '## 是否同时提高收益和PF','',
              '| 版本 | 收益变化（百分点） | PF变化 | 两项同时提高 |',
              '| --- | ---: | ---: | --- |']
    for s in summaries[1:]:
        lines.append(f'| {s["version"]} | {s["return_delta_pp"]:+.2f} | {s["pf_delta"]:+.3f} | '
                     +('是' if s['improves_both'] else '否')+' |')
    lines += ['', '## 连续回测的季度已实现收益切片','',
              '| 版本 | Q1收益 / PF | Q2收益 / PF | Q3收益 / PF | Q4收益 / PF |',
              '| --- | ---: | ---: | ---: | ---: |']
    for version in VERSIONS:
        lines.append('| '+version+' | '+' | '.join(f'{q["return_pct"]:+.2f}% / {fmt(q["pf"])}'
                     for q in details[version]['quarterly'])+' |')
    lines += ['', '## 月度已实现收益','', '| 月份 | '+' | '.join(VERSIONS)+' |',
              '| --- | '+' | '.join(['---:']*len(VERSIONS))+' |']
    for m in range(12):
        lines.append(f'| 2025-{m+1:02d} | '+' | '.join(f'{details[v]["monthly"][m]["return_pct"]:+.2f}%'
                     for v in VERSIONS)+' |')
    lines += ['', '## 新增退出实际触发情况','']
    for version in VERSIONS:
        for reason, item in details[version]['groups']['exit_reason'].items():
            if reason.startswith(('v1_', 'v5_')):
                lines.append(f'- {version} / {reason}：{item["trades"]}笔，已实现净盈亏 '
                             f'{item["net_profit"]:+.2f} USDT，平均单笔 {item["ev_pct"]:+.3f}%。')
    lines += ['', '## 解读边界','',
        '- 金额PF受复利和动态仓位影响；等额单笔PF用于辅助判断信号/退出本身的变化。',
        '- 退出变化会改变后续占仓与入场序列，不能把新增退出的盈亏简单当成该改动的因果贡献。',
        '- 月份按UTC平仓归属，2026-01-01边界强平并入12月；月度/季度不是浮盈亏净值，也不是独立重跑。',
        '- 2025已用于提出本轮假设，不能把本轮筛选称为样本外验证，更不能证明长期实盘收益。',
        '- 原始基准保留既有止损/回调模拟方式；普通OHLC回测存在盘中路径、滑点与实盘时点差异。',
        '- 本轮未部署服务器；生产使用仍需账户高水位重启恢复、真实执行成本和时点验证。',
        '', '对应规则：[README.md](README.md)。完整指标：[comparison.json](year-2025/comparison.json)。']
    (HERE/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summaries,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
