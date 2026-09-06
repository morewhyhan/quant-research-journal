"""Audit all relevant OHLCV/mark/funding coverage before interpreting a period."""
from collections import Counter
import json
from pathlib import Path
import pandas as pd
import pyarrow.feather as feather
from run_suite import HERE, ROOT, read_result

config=json.loads((HERE/'config.backtest.json').read_text())
periods=[('year-2025','okx_2025_full_server_archive','2025-01-01','2026-01-01'),
         ('july-2026','okx','2026-07-01','2026-08-01'),
         ('june-2026-proposed','okx_12m_archive','2026-06-01','2026-07-01')]
output={}
for label,directory,start,end in periods:
    rows=[]
    for pair in config['exchange']['pair_whitelist']:
        stem=pair.replace('/','_').replace(':','_')
        rec={'pair':pair,'kinds':{}}
        for kind in ('5m-futures','1h-mark','1h-funding_rate'):
            path=ROOT/'user_data/data'/directory/'futures'/f'{stem}-{kind}.feather'
            if not path.exists():
                rec['kinds'][kind]={'missing':True,'rows_in_period':0}
                continue
            dates=feather.read_table(path,columns=['date'])['date'].to_pandas()
            if dates.empty:
                rec['kinds'][kind]={'empty':True,'rows_in_period':0}
                continue
            period=dates.loc[(dates>=pd.Timestamp(start,tz='UTC'))&(dates<pd.Timestamp(end,tz='UTC'))]
            rec['kinds'][kind]={'start':str(dates.iloc[0]),'end':str(dates.iloc[-1]),
                'rows_in_period':len(period),
                'period_start':str(period.iloc[0]) if len(period) else None,
                'period_end':str(period.iloc[-1]) if len(period) else None,
                'max_gap_hours_in_period':float(period.diff().dt.total_seconds().max()/3600) if len(period)>1 else None}
        rows.append(rec)
    counts={kind:sum(r['kinds'][kind]['rows_in_period']>0 for r in rows)
            for kind in ('5m-futures','1h-mark','1h-funding_rate')}
    complete=sum(all(r['kinds'][k]['rows_in_period']>0 for k in r['kinds']) for r in rows)
    item={'data_directory':directory,'start':start,'end':end,'pairs_with_period_data':counts,
          'pairs_with_all_three_kinds':complete,'records':rows}
    if label in ('year-2025','july-2026'):
        r,p=read_result(HERE/label/'V5')
        item['actual_result']={k:r[k] for k in ('market_change','backtest_start','backtest_end') if k in r}
        item['exported_pairlist_count']=len(r.get('pairlist',[]))
        item['sum_trade_funding_fees']=sum(t['funding_fees'] for t in r['trades'])
    output[label]=item
    print(label,json.dumps({k:v for k,v in item.items() if k!='records'}),flush=True)
(HERE/'data_quality_audit.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
