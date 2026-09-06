"""Verify original archives, frozen inputs and public-safe configs before publication."""
import json
from pathlib import Path
import zipfile
from run_suite import ROOT,HERE,read_result,sha
from summarize import VERSIONS

allowed={'','REDACTED','***','research','local-backtest-only',
         'local-backtest-only-not-a-live-credential',None}
checks=[]
for period in ('year-2025','july-2026','june-2026'):
    for version in VERSIONS:
        folder=HERE/period/version
        done=json.loads((folder/'completed.json').read_text())
        result,path=read_result(folder)
        assert sha(path)==done['result_sha256'],(period,version,'result hash')
        for relative,expected in done['input_hashes'].items():
            assert sha(ROOT/relative)==expected,(period,version,relative)
        with zipfile.ZipFile(path) as archive:
            name=next(n for n in archive.namelist() if n.endswith('_config.json'))
            config=json.loads(archive.read(name))
            assert config.get('dry_run') is True
            assert config.get('api_server',{}).get('enabled') is False
            for section,keys in [('exchange',('key','secret','password','uid','apiKey')),
                                 ('api_server',('password','jwt_secret_key','ws_token'))]:
                for key in keys:
                    value=config.get(section,{}).get(key)
                    assert value in allowed,(period,version,'unsafe config field',section,key)
        trades=result['trades']
        assert abs(sum(t['profit_abs'] for t in trades)-(result['final_balance']-result['starting_balance']))<.001
        gain=sum(max(0,t['profit_abs']) for t in trades)
        loss=-sum(min(0,t['profit_abs']) for t in trades)
        assert abs(gain/loss-result['profit_factor'])<1e-8
        checks.append({'period':period,'version':version,'trades':len(trades),
            'result_sha256':sha(path),'pairlist_count':len(result['pairlist']),
            'funding_total':sum(t['funding_fees'] for t in trades),
            'validity':'invalid_missing_mark' if period=='july-2026' else
                       'relative_comparison_without_funding' if period=='year-2025' else
                       'short_period_with_funding',
            'public_config_checked':True,'input_hashes_verified':True})
year,_=read_result(HERE/'year-2025/V5')
audit=json.loads((HERE/'data_quality_audit.json').read_text())
available={r['pair'] for r in audit['year-2025']['records'] if r['kinds']['5m-futures']['rows_in_period']>0}
payload={'all_15_passed':True,'year_available_but_not_exported':sorted(available-set(year['pairlist'])),
         'records':checks}
(HERE/'FINAL_AUDIT.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(payload,ensure_ascii=False,indent=2))
