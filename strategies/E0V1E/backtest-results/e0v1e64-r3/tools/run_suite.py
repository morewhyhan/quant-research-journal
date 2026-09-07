"""Serial R3 suite. Real 90-day tests plus four year tests; verified yearly V5 reuse."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCE=ROOT/'my-strategies/E0V1E64_R3'
VERSIONS=('V5','V10','V11','V12','V13')
PERIODS={'apr-jun-2026':('okx_12m_archive','20260401-20260630'),
         'year-2025':('okx_2025_full_server_archive','20250101-20260101')}


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def read_result(folder):
    pointer=json.loads((folder/'.last_result.json').read_text())
    path=folder/pointer['latest_backtest']
    with zipfile.ZipFile(path) as z:
        name=next(n for n in z.namelist() if n.endswith('.json')
                  and not n.endswith('_config.json') and '_E0V1E' not in n)
        results=json.loads(z.read(name))['strategy']
    assert len(results)==1
    return next(iter(results.values())),path,next(iter(results))


def inputs():
    paths=sorted(SOURCE.glob('*.py'))+sorted(SOURCE.glob('*.json'))
    paths+=[HERE/'README.md',HERE/'config.backtest.json',HERE/'run_suite.py',HERE/'test_variants.py',
            ROOT/'run_backtest.py',ROOT/'fix_dns.py']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}


def manifest(period):
    data_name,timerange=PERIODS[period]
    folder=HERE/period
    folder.mkdir(parents=True,exist_ok=True)
    data=ROOT/'user_data/data'/data_name
    files=sorted(data.rglob('*.feather'))
    current={'inputs':inputs(),'data_directory':str(data.relative_to(ROOT)),
             'timerange':timerange,'data_hashes':{str(p.relative_to(data)):sha(p) for p in files}}
    path=folder/'manifest.json'
    if path.exists():
        prior=json.loads(path.read_text())
        if prior!=current:
            raise RuntimeError('Frozen inputs or data changed: '+period)
    else:
        path.write_text(json.dumps(current,indent=2))
    return current


def reuse_year_baseline(m):
    folder=HERE/'year-2025/V5'
    old=ROOT/'validation/e0v1e64-r2/year-2025/V5'
    result,path,name=read_result(old)
    old_done=json.loads((old/'completed.json').read_text())
    assert sha(path)==old_done['result_sha256']
    prior=json.loads((ROOT/'validation/e0v1e64-r2/year-2025/manifest.json').read_text())
    assert m['data_hashes']==prior['data_hashes']
    for name in ('E0V1E_v3.py','E0V1E_v3_equity60_reserve40.py','research_common.py','E0V1E64_V5.py','E0V1E64_V5.json'):
        assert sha(SOURCE/name)==sha(ROOT/'my-strategies/E0V1E64_R2'/name),name
    assert sha(HERE/'config.backtest.json')==sha(ROOT/'validation/e0v1e64-r2/config.backtest.json')
    assert len(result['trades'])==855 and abs(result['profit_total']*100-1551.5283818241248)<1e-7
    folder.mkdir(parents=True,exist_ok=True)
    if not (folder/'completed.json').exists():
        for p in (old/'.last_result.json',path):
            shutil.copy2(p,folder/p.name)
        for p in old.glob('*.meta.json'):
            shutil.copy2(p,folder/p.name)
        (folder/'completed.json').write_text(json.dumps({'version':'V5','reused':True,
            'provenance':str(old.relative_to(ROOT)),'result_sha256':sha(path),'inputs':m['inputs']},indent=2))
    print('VERIFIED REUSE: previous V5 yearly 855 trades, not a new run.',flush=True)


def run_one(period,version,m):
    folder=HERE/period/version
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'completed.json').exists():
        done=json.loads((folder/'completed.json').read_text())
        r,p,name=read_result(folder)
        assert done['inputs']==inputs() and done['result_sha256']==sha(p)
        print('RESUME '+period+' '+version,flush=True)
        return
    if (folder/'.last_result.json').exists():
        raise RuntimeError('Unverified existing output; inspect rather than overwrite: '+str(folder))
    data_name,timerange=PERIODS[period]
    slots=3 if version=='V13' else 1
    cmd=[sys.executable,str(ROOT/'run_backtest.py'),'backtesting','--config',str(HERE/'config.backtest.json'),
         '--strategy-path',str(SOURCE),'--strategy','E0V1E64_'+version,'--datadir',str(ROOT/'user_data/data'/data_name),
         '--timerange',timerange,'--max-open-trades',str(slots),'--fee','0.0005','--enable-protections',
         '--cache','none','--export','trades','--backtest-directory',str(folder)]
    started=time.time()
    print(f'START {period} {version} {datetime.now(timezone.utc).isoformat()}',flush=True)
    with (folder/'run.log').open('w') as log:
        p=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        (folder/'running.json').write_text(json.dumps({'pid':p.pid,'started':started,'command':cmd},indent=2))
        code=p.wait()
    if code:
        raise RuntimeError(f'{period} {version} failed ({code}); inspect run.log')
    if m['inputs']!=inputs():
        raise RuntimeError('Frozen inputs changed while running')
    r,p,name=read_result(folder)
    assert name=='E0V1E64_'+version
    assert r['max_open_trades']==slots
    if period=='apr-jun-2026':
        assert any(t['funding_fees']!=0 for t in r['trades']),'Missing funding calculation'
    (folder/'completed.json').write_text(json.dumps({'version':version,'reused':False,
        'result':p.name,'result_sha256':sha(p),'inputs':m['inputs'],'seconds':time.time()-started},indent=2))
    print(f'DONE {period} {version}: return={r["profit_total"]*100:.4f}% PF={r["profit_factor"]:.6f} '
          f'DD={r["max_drawdown_account"]*100:.3f}% n={len(r["trades"])}',flush=True)


def main():
    with (HERE/'.suite.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for period in PERIODS:
            m=manifest(period)
            if period=='year-2025':
                reuse_year_baseline(m)
            for version in VERSIONS:
                run_one(period,version,m)
            manifest(period)
        subprocess.run([sys.executable,str(HERE/'summarize.py')],cwd=ROOT,check=True)
        print('R3 COMPLETE: nine new runs plus one verified V5 yearly reuse.',flush=True)


if __name__=='__main__':
    main()
