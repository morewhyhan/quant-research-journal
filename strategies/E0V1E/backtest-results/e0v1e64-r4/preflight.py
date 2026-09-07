"""Analyze frozen V5 tails and audit a longer funded period before any new run."""
from collections import Counter
import json
from pathlib import Path
import sys
import pandas as pd
import pyarrow.feather as feather

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'validation/e0v1e64-r2'))
from run_suite import read_result

baseline,_=read_result(ROOT/'validation/e0v1e64-r2/year-2025/V5')
trades=baseline['trades']
tail={}
for side in (False,True):
    rows=[t for t in trades if t['is_short']==side]
    losses=[t for t in rows if t['profit_abs']<0]
    tail['short' if side else 'long']={'trades':len(rows),'losses':len(losses),
        'loss_sum':sum(t['profit_abs'] for t in losses),
        'losses_below_10pct':sum(t['profit_ratio']<-.1 for t in rows),
        'losses_below_15pct':sum(t['profit_ratio']<-.15 for t in rows),
        'worst_ratio':min(t['profit_ratio'] for t in rows)}
long_wins=[t for t in trades if not t['is_short'] and t['profit_ratio']>0]
tail['long_winners_recorded_bar_mae']={str(level):sum(t['min_rate']/t['open_rate']-1<=-level for t in long_wins)
                                     for level in (.05,.1,.15,.2)}
tail['warning']='Recorded bar extrema are descriptive, not tick-accurate realized excursions; not strategy inputs.'
config=json.loads((ROOT/'validation/e0v1e64-r2/config.backtest.json').read_text())
start,end=pd.Timestamp('2026-04-01',tz='UTC'),pd.Timestamp('2026-06-30',tz='UTC')
records=[]
for pair in config['exchange']['pair_whitelist']:
    stem=pair.replace('/','_').replace(':','_')
    item={'pair':pair,'kinds':{}}
    for kind in ('5m-futures','1h-mark','1h-funding_rate'):
        path=ROOT/'user_data/data/okx_12m_archive/futures'/f'{stem}-{kind}.feather'
        if not path.exists():
            item['kinds'][kind]={'missing':True,'n':0}
            continue
        dates=feather.read_table(path,columns=['date'])['date'].to_pandas()
        period=dates[(dates>=start)&(dates<end)]
        item['kinds'][kind]={'n':len(period),'start':str(period.iloc[0]) if len(period) else None,
                             'end':str(period.iloc[-1]) if len(period) else None,
                             'max_gap_hours':float(period.diff().dt.total_seconds().max()/3600) if len(period)>1 else None}
    records.append(item)
active=[r for r in records if r['kinds']['5m-futures']['n']>0]
missing=[r['pair'] for r in active if any(r['kinds'][k]['n']==0 for k in ('1h-mark','1h-funding_rate'))]
late_funding=[r['pair'] for r in active if r['kinds']['1h-funding_rate']['start']
              and pd.Timestamp(r['kinds']['1h-funding_rate']['start'])>
              pd.Timestamp(r['kinds']['5m-futures']['start'])+pd.Timedelta(hours=8)]
report={'baseline_tail':tail,'funded_period':{'start':str(start),'end_exclusive':str(end),
        'active_5m_pairs':len(active),'missing_supporting_pairs':missing,
        'funding_starts_over_8h_after_ohlcv':late_funding,'records':records}}
(HERE/'PREFLIGHT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'baseline_tail':tail,'active_5m_pairs':len(active),'missing_supporting_pairs':missing,
                 'late_funding':late_funding},ensure_ascii=False,indent=2))
if missing or late_funding:
    raise RuntimeError('Supporting data incomplete; review before choosing this interval')
