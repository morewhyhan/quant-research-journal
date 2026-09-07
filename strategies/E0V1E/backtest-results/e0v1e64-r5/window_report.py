"""Monthly returns and overlapping 90-day windows, not extra strategy tests."""
import json
import numpy as np
import pandas as pd
from run_suite import HERE, PERIODS, VERSIONS
from research_stats import daily_series, statistics


def main():
    all_windows = {}
    lines = ['# 月度表现与滚动90天', '',
             '全部以含浮盈亏、扣费用的UTC每日账户净值计算。2025没有真实资金费。',
             '90天检验段的最后一月仅覆盖6月1～29日；2025滚动窗高度重叠，不能当作独立重复试验。']
    for period in PERIODS:
        months, windows = {}, {}
        for version in VERSIONS:
            r = daily_series(HERE/period/version)
            s = statistics(r)
            months[version] = s['monthly_returns_pct']
            growth = np.expm1(np.log1p(r).rolling(90).sum()).dropna()*100
            variance = (r.rolling(90).var(ddof=1)*10000).dropna()
            windows[version] = {
                'monthly_variance_pp2': s['monthly_variance_pp2'],
                'monthly_std_pct': float(np.sqrt(s['monthly_variance_pp2'])),
                'positive_months': s['positive_months'],
                'monthly_observations': len(months[version]),
                'rolling_90_count': len(growth),
                'rolling_90_negative_count': int((growth < 0).sum()),
                'rolling_90_return_min_pct': float(growth.min()),
                'rolling_90_return_median_pct': float(growth.median()),
                'rolling_90_return_max_pct': float(growth.max()),
                'rolling_90_return_min_end_utc': str(growth.idxmin()),
                'rolling_90_daily_variance_min_pp2': float(variance.min()),
                'rolling_90_daily_variance_median_pp2': float(variance.median()),
                'rolling_90_daily_variance_max_pp2': float(variance.max()),
                'windows': [{'end_utc': str(date), 'return_pct': float(value),
                             'daily_variance_pp2': float(variance.loc[date])}
                            for date, value in growth.items()],
            }
        all_windows[period] = windows
        table = pd.DataFrame(months)
        lines += ['', '## ' + period, '',
                  '| 月份 | ' + ' | '.join(VERSIONS) + ' |',
                  '| --- | ' + ' | '.join(['---:']*len(VERSIONS)) + ' |']
        for date, row in table.iterrows():
            lines.append('| ' + date + ' | ' + ' | '.join(f'{row[v]:+.2f}%' for v in VERSIONS) + ' |')
        lines += ['', '| 版本 | 正收益月数 | 月方差(百分点²) | 滚动90天最差收益 | 滚动90天收益中位数 | 滚动90天日方差范围(百分点²) |',
                  '| --- | ---: | ---: | ---: | ---: | --- |']
        for version, s in windows.items():
            lines.append(f'| {version} | {s["positive_months"]}/{s["monthly_observations"]} | '
                         f'{s["monthly_variance_pp2"]:.2f} | {s["rolling_90_return_min_pct"]:+.2f}% | '
                         f'{s["rolling_90_return_median_pct"]:+.2f}% | '
                         f'{s["rolling_90_daily_variance_min_pp2"]:.2f}～{s["rolling_90_daily_variance_max_pp2"]:.2f} |')
    lines += ['', '方差单位是百分点²，绝不是账户亏损百分比；比较月方差时也要同时看平均收益，不能单凭较低月方差就说策略更优。',
              '只有3个月和12个月的样本，月方差估计很不稳定。滚动窗是对已观察曲线的描述，不是封存样本外验证。']
    (HERE/'WINDOWS.json').write_text(json.dumps(all_windows, indent=2, ensure_ascii=False), encoding='utf-8')
    (HERE/'MONTHLY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('Monthly and rolling-90-day diagnostics saved.')


if __name__ == '__main__':
    main()
