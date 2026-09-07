"""Describe existing variants before fixing combination experiments."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_stats import read_result, daily_series, statistics, paired_block_interval, trade_group, entry_match

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'validation/e0v1e64-r4'
VERSIONS = ('V5', 'V14', 'V16', 'V17')


def main():
    old = json.loads((OLD / 'comparison.json').read_text())
    output = {}
    lines = ['# 第五轮前分析：方差与规则贡献', '',
             '日收益来自UTC每天零点的账户估值，含浮动盈亏。方差用样本方差(n-1)，单位为百分点²；标准差为其平方根。',
             '此前报告中的“日波动”已经是日收益标准差，本次显式补上方差、下行偏差、季度及协方差。',
             '2025仍缺实际资金费，2026年4月1日～6月29日计入资金费；两段均已看过，不当作新样本外。']
    for period in old:
        periods = {}
        series = {v: daily_series(OLD / period / v) for v in VERSIONS}
        trades = {v: read_result(OLD / period / v)[0]['trades'] for v in VERSIONS}
        lines += ['', '## ' + period, '',
                  '| 版本 | 日收益方差(百分点²) | 日标准差 | 下行偏差 | 最差5%日平均收益 | 单笔EV |',
                  '| --- | ---: | ---: | ---: | ---: | ---: |']
        for v in VERSIONS:
            stats = statistics(series[v])
            assert abs(stats['daily_std_pct'] - old[period][v]['daily_volatility_pct']) < 1e-8
            stats['versus_v5'] = paired_block_interval(series[v], series['V5'])
            stats['trades'] = trade_group(trades[v])
            stats['long'] = trade_group([t for t in trades[v] if not t['is_short']])
            stats['short'] = trade_group([t for t in trades[v] if t['is_short']])
            stats['matched'] = entry_match(trades[v], trades['V5'])
            periods[v] = stats
            lines.append(f'| {v} | {stats["daily_variance_pp2"]:.3f} | {stats["daily_std_pct"]:.3f}% | '
                         f'{stats["downside_deviation_zero_pct"]:.3f}% | {stats["worst_5pct_days_mean_return_pct"]:.3f}% | '
                         f'{stats["trades"]["ev_pct"]:.3f}% |')
        aligned = pd.DataFrame(series)
        periods['correlation'] = aligned.corr().to_dict()
        periods['covariance_pp2'] = (aligned.cov() * 10000).to_dict()
        output[period] = periods
        lines += ['', '| 版本 | 与V5日收益相关性 | 正收益月份 | 已匹配单改变退出 | 盈利单变亏损单 | 改变退出的平均收益率差 |',
                  '| --- | ---: | ---: | ---: | ---: | ---: |']
        for v in VERSIONS:
            s = periods[v]
            lines.append(f'| {v} | {periods["correlation"][v]["V5"]:.3f} | {s["positive_months"]}/{len(s["monthly_returns_pct"])} | '
                         f'{s["matched"]["changed_exits"]} | {s["matched"]["winners_to_losses"]} | {s["matched"]["changed_mean_delta_pp"]:+.3f}个百分点 |')
        print(period, json.dumps({v: {k: periods[v][k] for k in ('daily_variance_pp2', 'daily_std_pct', 'positive_months', 'quarterly_returns_pct')} for v in VERSIONS}), flush=True)
        print('V16 exit comparison', json.dumps({k: value for k, value in periods['V16']['matched'].items() if k != 'cases'}), flush=True)
    (HERE / 'EXISTING_ANALYSIS.json').write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    (HERE / 'EXISTING_ANALYSIS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
