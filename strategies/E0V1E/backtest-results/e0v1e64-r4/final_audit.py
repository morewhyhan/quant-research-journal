"""Check result provenance, config safety, source immutability and risk reconciliation."""
import json
import zipfile
from run_suite import HERE,ROOT,VERSIONS,PERIODS,read_result,sha,inputs

allowed={'','REDACTED','***','research','local-backtest-only','local-backtest-only-not-a-live-credential',None}
comparison=json.loads((HERE/'comparison.json').read_text())
checks=[]
for period in PERIODS:
    manifest=json.loads((HERE/period/'manifest.json').read_text())
    assert manifest['inputs']==inputs()
    directory=ROOT/manifest['data_directory']
    for relative,expected in manifest['data_hashes'].items():
        assert sha(directory/relative)==expected,(period,relative)
    for version in VERSIONS:
        folder=HERE/period/version
        done=json.loads((folder/'completed.json').read_text())
        result,path,name=read_result(folder)
        assert done['result_sha256']==sha(path)
        assert done['inputs']==inputs()
        assert name=='E0V1E64_'+version
        if done.get('reused'):
            assert version == 'V5'
            assert done.get('provenance') in {
                'validation/e0v1e64-r3/apr-jun-2026/V5',
                'validation/e0v1e64-r2/year-2025/V5',
            }
        with zipfile.ZipFile(path) as z:
            config=json.loads(z.read(next(n for n in z.namelist() if n.endswith('_config.json'))))
            assert config['dry_run'] is True and config['api_server']['enabled'] is False
            for section,keys in [('exchange',('key','secret','password','uid','apiKey')),
                                 ('api_server',('password','jwt_secret_key','ws_token'))]:
                for key in keys:
                    assert config.get(section,{}).get(key) in allowed,(period,version,section,key)
        s=comparison[period][version]
        assert s['max_trade_pnl_reconciliation_error']<.001
        assert s['max_funding_reconciliation_error']<.01
        assert not s['valuation_gap_pairs']
        assert s['actual_leverage']==[1.0]
        assert s['max_concurrent_positions']<=(3 if version=='V13' else 1)
        if period=='apr-jun-2026':
            assert s['funded_trades']>0
        checks.append({'period':period,'version':version,'result_sha256':sha(path),
            'reused':done.get('reused',False),'trades':s['trades'],
            'source_and_data_verified':True,'public_config_checked':True,
            'equity_reconciled':True,'valuation_gap_pairs':s['valuation_gap_pairs']})
(HERE/'FINAL_AUDIT.json').write_text(json.dumps({'passed':True,'new_backtests':8,'reused_baselines':2,
    'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: 8 new backtests + 2 verified baselines; source/data/config safety and equity reconciliation.')
