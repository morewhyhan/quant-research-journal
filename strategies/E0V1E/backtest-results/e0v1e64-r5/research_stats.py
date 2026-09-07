"""Daily equity-return statistics; percentages and squared percentage points are explicit."""
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd


def read_result(folder):
    folder = Path(folder)
    filename = json.loads((folder / '.last_result.json').read_text())['latest_backtest']
    path = folder / filename
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith('.json') and not name.endswith('_config.json'):
                payload = json.loads(archive.read(name))
                if isinstance(payload, dict) and 'strategy' in payload:
                    assert len(payload['strategy']) == 1
                    key = next(iter(payload['strategy']))
                    return payload['strategy'][key], path, key
    raise ValueError('No result in ' + str(path))


def daily_series(folder):
    payload = json.loads((Path(folder) / 'equity_daily.json').read_text())
    frame = pd.DataFrame(payload)
    frame['date'] = pd.to_datetime(frame['date'], utc=True)
    series = frame.set_index('date')['equity'].astype(float)
    assert series.index.is_unique and series.index.is_monotonic_increasing
    assert series.index.to_series().diff().dropna().eq(pd.Timedelta(days=1)).all()
    assert (series > 0).all()
    return series.pct_change(fill_method=None).dropna()


def statistics(returns):
    r = np.asarray(returns, dtype=float)
    assert len(r) > 1 and np.isfinite(r).all() and (r > -1).all()
    var = float(np.var(r, ddof=1))
    dates = returns.index - pd.Timedelta(nanoseconds=1)
    groups = {}
    for freq in ('M', 'Q'):
        labels = dates.tz_localize(None).to_period(freq).astype(str)
        groups[freq] = {label: float((np.prod(1 + r[labels == label]) - 1) * 100)
                        for label in sorted(set(labels))}
    tail_count = max(1, math.ceil(len(r) * .05))
    monthly = np.array(list(groups['M'].values()))
    return {
        'days': len(r), 'mean_daily_return_pct': float(r.mean() * 100),
        'mean_daily_log_return_pct': float(np.log1p(r).mean() * 100),
        'daily_variance_decimal': var, 'daily_variance_pp2': var * 10000,
        'daily_std_pct': math.sqrt(var) * 100,
        'downside_deviation_zero_pct': float(np.sqrt(np.mean(np.minimum(r, 0) ** 2)) * 100),
        'worst_5pct_days_mean_return_pct': float(np.sort(r)[:tail_count].mean() * 100),
        'worst_day_pct': float(r.min() * 100), 'negative_days': int((r < 0).sum()),
        'lag1_autocorrelation': float(pd.Series(r).autocorr()),
        'monthly_returns_pct': groups['M'], 'quarterly_returns_pct': groups['Q'],
        'monthly_variance_pp2': float(monthly.var(ddof=1)) if len(monthly) > 1 else None,
        'positive_months': int((monthly > 0).sum()),
    }


def paired_block_interval(candidate, baseline, seed=20260907, draws=2000, block=7):
    assert candidate.index.equals(baseline.index)
    diff = np.log1p(candidate.to_numpy()) - np.log1p(baseline.to_numpy())
    n = len(diff)
    rng = np.random.default_rng(seed)
    # Contiguous, non-circular moving blocks preserve within-week dependence.
    starts = rng.integers(0, n - block + 1, size=(draws, math.ceil(n / block)))
    indexes = (starts[:, :, None] + np.arange(block)).reshape(draws, -1)[:, :n]
    means = diff[indexes].mean(axis=1) * 100
    return {'block_days': block, 'draws': draws, 'seed': seed,
            'daily_log_excess_pct': float(diff.mean() * 100),
            'bootstrap_95pct_interval_pp': np.quantile(means, [.025, .975]).tolist(),
            'interpretation': 'descriptive paired block bootstrap on seen data, not a future guarantee or multiple-testing correction'}


def trade_group(rows):
    if not rows:
        return {'trades': 0}
    ratio = np.array([t['profit_ratio'] for t in rows])
    pnl = np.array([t['profit_abs'] for t in rows])
    losses = -pnl[pnl < 0].sum()
    ratio_losses = -ratio[ratio < 0].sum()
    return {'trades': len(rows), 'ev_pct': float(ratio.mean() * 100),
            'trade_variance_pp2': float(ratio.var(ddof=1) * 10000) if len(rows) > 1 else None,
            'pf': float(pnl[pnl > 0].sum() / losses) if losses else None,
            'equal_stake_pf': float(ratio[ratio > 0].sum() / ratio_losses) if ratio_losses else None,
            'total_pnl': float(pnl.sum()), 'gross_loss': float(losses),
            'win_rate_pct': float((ratio > 0).mean() * 100)}


def entry_match(candidate, baseline):
    key = lambda t: (t['pair'], t['is_short'], t['open_timestamp'])
    b, c = {key(t): t for t in baseline}, {key(t): t for t in candidate}
    assert len(b) == len(baseline) and len(c) == len(candidate)
    common = sorted(b.keys() & c.keys())
    changed = [k for k in common if (b[k]['close_timestamp'], b[k]['exit_reason']) !=
               (c[k]['close_timestamp'], c[k]['exit_reason'])]
    fields = ('pair', 'is_short', 'open_date', 'close_date', 'exit_reason', 'profit_ratio', 'profit_abs', 'stake_amount')
    cases = [{'baseline': {f: b[k][f] for f in fields}, 'candidate': {f: c[k][f] for f in fields},
              'profit_delta_pp': float((c[k]['profit_ratio'] - b[k]['profit_ratio']) * 100)} for k in changed]
    return {'matched': len(common), 'changed_exits': len(changed),
            'winners_to_losses': sum(b[k]['profit_ratio'] > 0 and c[k]['profit_ratio'] < 0 for k in changed),
            'improved_exits': sum(c[k]['profit_ratio'] > b[k]['profit_ratio'] for k in changed),
            'changed_baseline': trade_group([b[k] for k in changed]),
            'changed_candidate': trade_group([c[k] for k in changed]),
            'changed_mean_delta_pp': float(np.mean([case['profit_delta_pp'] for case in cases])) if cases else 0,
            'new': trade_group([c[k] for k in c.keys() - b.keys()]),
            'missing': trade_group([b[k] for k in b.keys() - c.keys()]),
            'cases': sorted(cases, key=lambda case: case['profit_delta_pp'])}
