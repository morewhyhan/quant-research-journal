"""Read-only Feather date-column audit for an optional different-period check."""
from collections import Counter
import json
from pathlib import Path
import pyarrow.feather as feather

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
config=json.loads((HERE/'config.backtest.json').read_text())
summary={}
for directory in ('okx_12m_archive','okx_200_may2026_archive','okx'):
    records=[]
    for pair in config['exchange']['pair_whitelist']:
        name=pair.replace('/','_').replace(':','_')+'-5m-futures.feather'
        path=ROOT/'user_data/data'/directory/'futures'/name
        if not path.exists():
            records.append({'pair':pair,'missing':True})
            continue
        dates=feather.read_table(path,columns=['date'])['date']
        records.append({'pair':pair,'rows':len(dates),
                        'start':str(dates[0].as_py()),'end':str(dates[-1].as_py())})
    valid=[r for r in records if 'end' in r]
    summary[directory]={'records':records,'available_pairs':len(valid),
        'start_dates':dict(Counter(r['start'][:10] for r in valid)),
        'end_dates':dict(Counter(r['end'][:10] for r in valid))}
(HERE/'available_periods.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:{f:v[f] for f in ('available_pairs','start_dates','end_dates')} for k,v in summary.items()},indent=2))
