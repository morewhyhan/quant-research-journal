"""Matched-entry cases and funded-period valuation audit, without changing strategy inputs."""
import json
from run_suite import HERE,ROOT,VERSIONS,read_result
from summarize import Prices,equity_curve,basic

period='apr-jun-2026'
prices=Prices(ROOT/'user_data/data/okx_12m_archive')
results={v:read_result(HERE/period/v)[0] for v in VERSIONS}
key=lambda t:(t['pair'],t['is_short'],t['open_timestamp'])
base={key(t):t for t in results['V5']['trades']}
output={}
for version,r in results.items():
    current={key(t):t for t in r['trades']}
    common=base.keys()&current.keys()
    changed=[k for k in common if (base[k]['close_timestamp'],base[k]['exit_reason'])!=
             (current[k]['close_timestamp'],current[k]['exit_reason'])]
    fields=('pair','is_short','open_date','close_date','exit_reason','profit_ratio','profit_abs','stake_amount')
    cases=[{'baseline':{f:base[k][f] for f in fields},'candidate':{f:current[k][f] for f in fields},
            'profit_delta_pp':100*(current[k]['profit_ratio']-base[k]['profit_ratio'])} for k in changed]
    curve,risk=equity_curve(r,prices)
    summary=basic(r)
    summary.update({k:v for k,v in risk.items() if k!='daily'})
    summary.update({'same_entry_count':len(common),'changed_exit_count':len(changed),
        'baseline_winners_to_losses':sum(base[k]['profit_ratio']>0 and current[k]['profit_ratio']<0 for k in changed),
        'new_entries':len(current.keys()-base.keys()),'missing_baseline_entries':len(base.keys()-current.keys()),
        'changed_cases':sorted(cases,key=lambda c:c['profit_delta_pp'])})
    output[version]=summary
    print(version,json.dumps({k:v for k,v in summary.items() if k!='changed_cases'},ensure_ascii=False),flush=True)
(HERE/'FUNDED_CASE_AUDIT.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
