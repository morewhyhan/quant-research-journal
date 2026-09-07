"""Report true strategy combinations, daily variance and factorial interactions."""
from itertools import combinations, product
import json
from pathlib import Path
import numpy as np
import pandas as pd

from run_suite import HERE, ROOT, SOURCE, VERSIONS, NEW, PERIODS, FACTORS, read_result
from research_stats import daily_series, statistics, paired_block_interval, trade_group, entry_match
from valuation import Prices, equity_curve, basic

LABELS = {'V5': 'V5基准', 'V14': '排序R', 'V16': '退出E', 'V17': '仓位B',
          'V18': '排序+仓位', 'V19': '排序+退出', 'V20': '退出+仓位', 'V21': '三项合并'}


def effects(results):
    metrics = ('mean_daily_log_return_pct', 'daily_variance_pp2', 'pf', 'mtm_max_drawdown_pct')
    names = ('R排序', 'E退出', 'B仓位')
    state = {FACTORS[v]: result for v, result in results.items()}
    out = {'main_effects': {}, 'pair_interactions': {}, 'third_order': {}}
    for i, name in enumerate(names):
        out['main_effects'][name] = {metric: float(np.mean([s[metric] for key, s in state.items() if key[i]])
                                                  - np.mean([s[metric] for key, s in state.items() if not key[i]]))
                                     for metric in metrics}
    for i, j in combinations(range(3), 2):
        out['pair_interactions'][names[i] + '×' + names[j]] = {
            metric: float(sum((1 if key[i] == key[j] else -1) * s[metric] for key, s in state.items()) / 2)
            for metric in metrics}
    for metric in metrics:
        out['third_order'][metric] = float(sum((-1) ** (3 - sum(key)) * s[metric] for key, s in state.items()))
    return out


def main():
    all_results, details, factorial = {}, {}, {}
    lines = ['# 第五轮：组合结果、方差与规则贡献', '',
             '四个新组合各跑90天和2025全年，共8次新回测；V5/V14/V16/V17两段共8份旧结果校验后复用。',
             '日方差使用每日账户估值收益率的样本方差，单位为百分点²；标准差是它的平方根。',
             '2025实际币池180、缺真实资金费；90天实际币池174、计入资金费。两段均为已观察数据。']
    for period, (directory, _) in PERIODS.items():
        prices = Prices(ROOT / 'user_data/data' / directory)
        records, returns, results = {}, {}, {}
        for version in VERSIONS:
            folder = HERE / period / version
            result, _, _ = read_result(folder)
            curve, risk = equity_curve(result, prices)
            curve.to_feather(folder / 'equity_5m.feather')
            (folder / 'equity_daily.json').write_text(json.dumps(risk['daily'], indent=2))
            returns[version] = daily_series(folder)
            s = basic(result)
            s.update({k: v for k, v in risk.items() if k != 'daily'})
            s.update(statistics(returns[version]))
            s.update({'version': version, 'label': LABELS[version], 'factors': FACTORS[version],
                      'baseline_reused': json.loads((folder / 'completed.json').read_text())['reused'],
                      'trade_variance_pp2': trade_group(result['trades'])['trade_variance_pp2']})
            assert abs(s['daily_std_pct'] - s['daily_volatility_pct']) < 1e-8
            assert abs((np.prod(1 + returns[version]) - 1) * 100 - s['return_pct']) < 1e-6
            results[version], records[version] = s, result['trades']
        base = results['V5']
        detail = {}
        for version, s in results.items():
            s['terminal_equity_improvement_pct'] = (s['final_balance'] / base['final_balance'] - 1) * 100
            s['variance_change_pct'] = (s['daily_variance_pp2'] / base['daily_variance_pp2'] - 1) * 100
            s['pf_delta'] = s['pf'] - base['pf']
            s['mtm_dd_delta_pp'] = s['mtm_max_drawdown_pct'] - base['mtm_max_drawdown_pct']
            s['engine_dd_delta_pp'] = s['engine_drawdown_pct'] - base['engine_drawdown_pct']
            s['paired_log_excess'] = paired_block_interval(returns[version], returns['V5'])
            s['dominates_v5'] = (s['terminal_equity_improvement_pct'] > 1e-6 and s['pf_delta'] >= -1e-6
                                 and s['variance_change_pct'] <= 1e-6 and s['mtm_dd_delta_pp'] <= 1e-6
                                 and s['engine_dd_delta_pp'] <= 1e-6)
            s['meets_material_goal'] = s['dominates_v5'] and s['terminal_equity_improvement_pct'] >= 10 - 1e-6
            s['year_3000_goal'] = period == 'year-2025' and s['return_pct'] >= 3000
            detail[version] = entry_match(records[version], records['V5'])
            s['matched_entries'] = detail[version]['matched']
            s['changed_exits'] = detail[version]['changed_exits']
            s['winner_to_loss_count'] = detail[version]['winners_to_losses']
            s['new_entries'] = detail[version]['new']['trades']
            s['missing_entries'] = detail[version]['missing']['trades']
        aligned = pd.DataFrame(returns)
        detail['correlation'] = aligned.corr().to_dict()
        detail['covariance_pp2'] = (aligned.cov() * 10000).to_dict()
        for version, reference in (('V18', 'V14'), ('V20', 'V16'), ('V21', 'V19')):
            detail[version]['sizing_only_reference'] = reference
            detail[version]['sizing_only_check'] = entry_match(records[version], records[reference])
        all_results[period], details[period], factorial[period] = results, detail, effects(results)
        title = '2026年4月1日～6月29日，计入资金费' if period == 'apr-jun-2026' else '2025全年，未计实际资金费'
        lines += ['', '## ' + title, '',
                  '| 版本 | 收益 | PF | 日方差(百分点²) | 日标准差 | 含浮亏回撤 | 平仓回撤 | 单笔EV | 笔数 |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for v, s in results.items():
            lines.append(f'| {v} {LABELS[v]} | {s["return_pct"]:+.2f}% | {s["pf"]:.3f} | {s["daily_variance_pp2"]:.3f} | '
                         f'{s["daily_std_pct"]:.3f}% | {s["mtm_max_drawdown_pct"]:.2f}% | {s["engine_drawdown_pct"]:.2f}% | '
                         f'{s["ev_pct"]:+.3f}% | {s["trades"]} |')
        lines += ['', '| 新组合 | 期末权益较V5 | 方差较V5 | PF差 | 含浮亏回撤差 | 全面改善 |',
                  '| --- | ---: | ---: | ---: | ---: | --- |']
        for v in NEW:
            s = results[v]
            lines.append(f'| {v} | {s["terminal_equity_improvement_pct"]:+.2f}% | {s["variance_change_pct"]:+.2f}% | '
                         f'{s["pf_delta"]:+.3f} | {s["mtm_dd_delta_pp"]:+.2f}个百分点 | {"是" if s["dominates_v5"] else "否"} |')
        lines += ['', '| 规则平均开关差 | 日对数收益差(百分点) | 日方差差(百分点²) | PF差 | 含浮亏回撤差(百分点) |',
                  '| --- | ---: | ---: | ---: | ---: |']
        for name, s in factorial[period]['main_effects'].items():
            lines.append(f'| {name} | {s["mean_daily_log_return_pct"]:+.5f} | {s["daily_variance_pp2"]:+.3f} | '
                         f'{s["pf"]:+.3f} | {s["mtm_max_drawdown_pct"]:+.3f} |')
        print(period, json.dumps({v: {k: s[k] for k in ('return_pct', 'pf', 'daily_variance_pp2', 'mtm_max_drawdown_pct', 'dominates_v5')}
                                 for v, s in results.items()}), flush=True)
    both = [v for v in NEW if all(all_results[p][v]['dominates_v5'] for p in PERIODS)]
    lines += ['', '## 选择与证据边界', '',
              '两段均全面改善V5的组合：' + ('、'.join(both) if both else '没有') + '。',
              '全面改善要求期末权益更高，PF不降，日方差、两类最大回撤均不增。折中方案不得标成全面改善。',
              '方差度量日常涨跌分散程度；最大回撤度量从净值高点跌到后续低点。降低方差不保证最大回撤降低。',
              '组合是一个账户内的规则合并，不能用旧策略收益率相加替代；同一因子在不同组合中的效果也可能不同。',
              '排序R包括三个既定指标，当前试验只能评价整个排序模块，不能据此证明其中每个指标独立有效。',
              '7日配对块bootstrap区间、相关/协方差、月季数据见JSON。全历史已经反复被观察，区间不能消除筛选偏差。',
              '2025未计真实资金费，5m估值未计滑点且未捕捉所有盘中极值；不推断实盘保证收益，也不外推90天成年化3000%。',
              '[冻结方案](SPEC.md) · [既有方差分析](EXISTING_ANALYSIS.md) · [完整数值](comparison.json) · '
              '[规则交互](FACTOR_EFFECTS.json) · [逐笔差异](MATCHED_CASES.json)']
    for name, payload in (('comparison.json', all_results), ('FACTOR_EFFECTS.json', factorial), ('MATCHED_CASES.json', details)):
        (HERE / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    (HERE / 'RESULTS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
