"""Serial, independently funded June cross-check of every frozen candidate."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile
import pyarrow.feather as feather
from run_suite import ROOT, HERE, SOURCE, inputs_manifest, read_result, sha
from summarize import VERSIONS, LABELS, stats

OUT=HERE/'june-2026'
DATA=ROOT/'user_data/data/okx_12m_archive'


def fingerprint():
    files=inputs_manifest()
    files.update({str(p.relative_to(ROOT)):sha(p) for p in (HERE/'JUNE_PLAN.md',Path(__file__))})
    return files


def year_ready():
    """Do not overlap backtests. Wait only while a recognized first-stage process exists."""
    for version in VERSIONS:
        if not (HERE/'year-2025'/version/'completed.json').exists():
            return False
    return (HERE/'year-2025/comparison.json').exists()


def year_running():
    listing=subprocess.run(['ps','-eo','args='],capture_output=True,text=True,check=True).stdout
    return any('validation/e0v1e64-r2/run_suite.py' in line and 'python' in line
               for line in listing.splitlines())


def build_manifest():
    config=json.loads((HERE/'config.backtest.json').read_text())
    records=[]
    for pair in config['exchange']['pair_whitelist']:
        stem=pair.replace('/','_').replace(':','_')
        item={'pair':pair,'files':{}}
        for kind in ('5m-futures','1h-mark','1h-funding_rate'):
            path=DATA/'futures'/f'{stem}-{kind}.feather'
            if path.exists():
                dates=feather.read_table(path,columns=['date'])['date']
                item['files'][kind]={'path':str(path.relative_to(DATA)),'sha256':sha(path),
                    'rows':len(dates),'start':str(dates[0].as_py()),'end':str(dates[-1].as_py())}
            else:
                item['files'][kind]={'missing':True}
        records.append(item)
    audit=json.loads((HERE/'data_quality_audit.json').read_text())['june-2026-proposed']
    for record in audit['records']:
        if record['kinds']['5m-futures']['rows_in_period'] > 0:
            for kind in ('1h-mark','1h-funding_rate'):
                if record['kinds'][kind]['rows_in_period'] == 0:
                    raise RuntimeError('Missing supporting June data: '+record['pair']+' '+kind)
    return {'created_utc':datetime.now(timezone.utc).isoformat(),
        'timerange':'20260601-20260630','data_directory':str(DATA.relative_to(ROOT)),
        'input_hashes':fingerprint(),'coverage':records}


def run_one(version, manifest):
    folder=OUT/version
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'completed.json').exists():
        done=json.loads((folder/'completed.json').read_text())
        result,path=read_result(folder)
        if done['input_hashes']!=fingerprint() or done['result_sha256']!=sha(path):
            raise RuntimeError(f'{version}: completed archive changed')
        print('RESUME JUNE '+version,flush=True)
        return
    if (folder/'.last_result.json').exists():
        raise RuntimeError(f'{version}: unverified existing result; inspect before rerun')
    cmd=[sys.executable,str(ROOT/'run_backtest.py'),'backtesting',
        '--config',str(HERE/'config.backtest.json'),'--strategy-path',str(SOURCE),
        '--strategy','E0V1E64_'+version,'--datadir',str(DATA),
        '--timerange','20260601-20260630','--fee','0.0005','--enable-protections',
        '--cache','none','--export','trades','--backtest-directory',str(folder)]
    started=time.time()
    print('START JUNE '+version,flush=True)
    with (folder/'run.log').open('w') as log:
        process=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        (folder/'running.json').write_text(json.dumps({'pid':process.pid,'command':cmd,'started':started},indent=2))
        code=process.wait()
    if code:
        raise RuntimeError(f'{version}: June backtest failed ({code}), inspect run.log')
    if fingerprint()!=manifest['input_hashes']:
        raise RuntimeError('Frozen inputs changed during June backtest')
    result,path=read_result(folder)
    with zipfile.ZipFile(path) as archive:
        name=next(n for n in archive.namelist() if n.endswith('.json')
                  and not n.endswith('_config.json') and '_E0V1E' not in n)
        if list(json.loads(archive.read(name))['strategy'])!=['E0V1E64_'+version]:
            raise RuntimeError('Unexpected strategy in archive')
    (folder/'completed.json').write_text(json.dumps({'version':version,'result':path.name,
        'result_sha256':sha(path),'input_hashes':fingerprint(),'seconds':time.time()-started},indent=2))
    print(f'DONE JUNE {version}: return={result["profit_total"]*100:.4f}% '
          f'PF={result["profit_factor"]:.6f} trades={len(result["trades"])}',flush=True)


def report():
    summaries=[]
    for v in VERSIONS:
        r,p=read_result(OUT/v)
        s=stats(r['trades'])
        s.update({'version':v,'label':LABELS[v],'return_pct':r['profit_total']*100,
            'max_drawdown_pct':r['max_drawdown_account']*100,'result_file':str(p.relative_to(HERE)),
            'starting_balance':r['starting_balance'],'final_balance':r['final_balance'],
            'actual_backtest_start':r['backtest_start'],'actual_backtest_end':r['backtest_end'],
            'actual_leverage':sorted({t['leverage'] for t in r['trades']}),
            'exported_pairlist_count':len(r['pairlist']),
            'total_funding_fees':sum(t['funding_fees'] for t in r['trades']),
            'trades_with_nonzero_funding':sum(t['funding_fees'] != 0 for t in r['trades'])})
        summaries.append(s)
    for s in summaries:
        if s['trades_with_nonzero_funding'] == 0:
            raise RuntimeError('Unexpected all-zero funding; inspect supporting data before accepting result')
    base=summaries[0]
    for s in summaries:
        s['improves_both_vs_V5']=s['return_pct']>base['return_pct'] and s['pf']>base['pf']
    (OUT/'comparison.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 不同年份检查：2026年6月1～29日','',
        '五个相同冻结版本，普通回测20260701–20260801，每版初始8000 USDT，独立零仓位开始，5m、单持仓、单边手续费0.05%。',
        '本地okx_12m_archive数据与2025归档目录不同，但五个版本内部使用相同白名单和同一数据快照；覆盖明细见manifest.json。', '',
        '| 版本 | 收益率 | 金额PF | 等额PF | 单笔EV | 最大回撤 | 交易数 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for s in summaries:
        lines.append(f'| {s["version"]} | {s["return_pct"]:+.2f}% | {s["pf"]:.3f} | '
            f'{s["equal_stake_pf"]:.3f} | {s["ev_pct"]:+.3f}% | {s["max_drawdown_pct"]:.2f}% | {s["trades"]} |')
    improved=[s['version'] for s in summaries[1:] if s['improves_both_vs_V5']]
    lines+=['','本月同时改善收益和金额PF：'+('、'.join(improved) if improved else '无')+'。',
        '这是固定参数的不同年份补充检查，不是充分的长期验证；仅29天且历史上已观察过附近实盘行情，不将其标为严格封存样本外。未据结果调参、未部署服务器。', '',
        '完整数字：[comparison.json](june-2026/comparison.json)；[测试前规则](JUNE_PLAN.md)。']
    (HERE/'JUNE_RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summaries,ensure_ascii=False,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wait-for-year',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'.runner.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while not year_ready():
            if not args.wait_for_year or not year_running():
                raise RuntimeError('Full-year phase incomplete and no active recognized runner')
            time.sleep(15)
        subprocess.run([sys.executable,str(HERE/'diagnostics.py')],cwd=ROOT,check=True)
        path=OUT/'manifest.json'
        current=build_manifest()
        if path.exists():
            manifest=json.loads(path.read_text())
            if manifest['input_hashes']!=current['input_hashes'] or manifest['coverage']!=current['coverage']:
                raise RuntimeError('June inputs/data changed since prior run')
        else:
            manifest=current
            path.write_text(json.dumps(manifest,indent=2))
        for v in VERSIONS:
            run_one(v,manifest)
        if build_manifest()['coverage']!=manifest['coverage']:
            raise RuntimeError('June data changed during testing')
        report()
        print('YEAR DIAGNOSTICS AND ALL FIVE JUNE CHECKS COMPLETE',flush=True)


if __name__=='__main__':
    main()
