"""Cost-gated repeated MiniMax runs; errors remain separate observations."""
import argparse
from collections import Counter,defaultdict
from dataclasses import dataclass,asdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import csv
import hashlib
import json
import math
import time
from trust_network.demo.run import run_one,ROOT,ORGS
from trust_network.demo.documents import keypair

DEFAULT_COMBINATIONS=('black_box:selfish','verified_certificate:resp')


@dataclass(frozen=True)
class BatchConfig:
    repetitions: int = 15
    combinations: tuple[str,...] = DEFAULT_COMBINATIONS
    temperatures: tuple[float,...] = (.2,.5,.8)
    workers: int = 2

    def __post_init__(self):
        if self.repetitions<1 or not self.temperatures or not 1<=self.workers<=3: raise ValueError('invalid batch size or workers')
        if len(set(self.combinations))!=len(self.combinations) or not self.combinations: raise ValueError('duplicate or empty combinations')
        for combo in self.combinations:
            if combo not in tuple(p+':'+o for p in ('black_box','certificate','verified_certificate') for o in ('selfish','resp')): raise ValueError('invalid combination')
        if any(not 0<=t<=2 for t in self.temperatures): raise ValueError('invalid temperature')


def estimate(config: BatchConfig):
    runs=config.repetitions*len(config.combinations)
    historical={s['protocol']+':'+s['objective']:s for s in json.loads((ROOT/'results/minimax_v2/summary.json').read_text())}
    return {'repetitions':config.repetitions,'combinations':config.combinations,'workflow_runs':runs,
            'basis':'历史六组合共39次组织调用、71645 token；平均每组合6.5调用、11940.8333 token。',
            'mean_based_calls':runs*39/6,'mean_based_tokens':round(runs*71645/6),
            'selected_history_based_calls':config.repetitions*sum(historical[c]['calls'] for c in config.combinations),
            'selected_history_based_tokens':config.repetitions*sum(historical[c]['total_tokens'] for c in config.combinations),
            'all_six_15_repeats_calls':585,'all_six_15_repeats_tokens':1074675,
            'decision_call_cap':runs*24,'http_attempt_cap_with_format_retry':runs*24*2,
            'temperatures':config.temperatures,'warning':'估算不是费用承诺；返工、API错误与最多一次格式重试影响用量。未收到用户确认不得运行完整批次。'}


def case_hashes(case):
    return {str(p.relative_to(case)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(case.rglob('*')) if p.is_file()}


def run_record(index,combo,config,case,env_file,out,hashes,signing_keys=None):
    protocol,objective=combo.split(':'); folder=out/f'run_{index:03d}'/f'{protocol}_{objective}'
    folder.mkdir(parents=True,exist_ok=False)
    started=time.time(); temperature=config.temperatures[index%len(config.temperatures)]
    record={'repetition':index,'combination':combo,'temperature':temperature,'status':'error'}
    try:
        if case_hashes(case)!=hashes: raise ValueError('scenario inputs changed during batch')
        result=run_one(case,env_file,folder,protocol,objective,temperature=temperature,signing_keys=signing_keys)
        record.update(status='finished',**result)
    except Exception as exc:
        # Never copy remote/raw exception contents or secrets into the manifest.
        record['error_type']=type(exc).__name__
        record['error']='run failed; no synthetic completion substituted'
        partial=folder/f'{protocol}_{objective}.jsonl'
        if partial.exists(): partial.rename(partial.with_suffix('.jsonl.interrupted'))
    finally:
        if case_hashes(case)!=hashes:
            record['status']='error'; record['error']='input hashes changed'
        logs=list(folder.glob('*.jsonl'))+list(folder.glob('*.jsonl.interrupted'))
        events=[json.loads(line) for log in logs for line in log.read_text().splitlines()]
        record['logged_calls']=len(events)
        record['logged_api_requests']=sum(e['usage'].get('attempts',1) for e in events)
        record['logged_tokens']=sum(e['usage'].get('total_tokens',0) for e in events)
        record['logged_private_marker_hits']=sum(bool(e['private_marker_leaked']) for e in events)
        record['checks_selected']=[check for e in events for check in e['decision']['checks']]
        record['elapsed_seconds']=round(time.time()-started,2)
        (folder/'record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    return record


def wilson(successes,total):
    if not total: return None
    z=1.959963984540054; p=successes/total; d=1+z*z/total
    center=(p+z*z/(2*total))/d
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
    return [max(0,center-half),min(1,center+half)]


def aggregate(records):
    groups=defaultdict(list)
    for record in records: groups[record['combination']].append(record)
    output=[]
    for combo,group in sorted(groups.items()):
        finished=[r for r in group if r['status']=='finished']; failed=[r for r in group if r['status']!='finished']
        outcomes=Counter(r['outcome'] for r in finished)
        scopes=Counter(c.strip() for r in finished for c in r['checks_selected'])
        output.append({'combination':combo,'attempted_runs':len(group),'finished_runs':len(finished),'error_runs':len(failed),
                       'run_status_counts':dict(Counter(r['status'] for r in group)),
                       'outcomes':dict(outcomes),'resubmit_distribution':dict(Counter(r['resubmits'] for r in finished)),
                       'calls_distribution':dict(Counter(r['calls'] for r in finished)),
                       'api_requests_distribution':dict(Counter(r.get('api_requests',r['calls']) for r in finished)),
                       'checks_exact_text_frequency':dict(scopes),
                       'private_marker_hits_finished':sum(r['logged_private_marker_hits'] for r in finished),
                       'private_marker_hits_failed_partial':sum(r['logged_private_marker_hits'] for r in failed),
                       'logged_calls_all':sum(r['logged_calls'] for r in group),
                       'logged_tokens_all':sum(r['logged_tokens'] for r in group),
                       'unsafe_completions':sum(r['unsafe_completion'] for r in finished),
                       'safe_completion_count':sum(r['task_completed'] for r in finished),
                       'safe_completion_wilson95_finished_only':wilson(sum(r['task_completed'] for r in finished),len(finished)),
                       'temperature_strata':[{'temperature':t,'finished':sum(r['temperature']==t for r in finished),
                                              'outcomes':dict(Counter(r['outcome'] for r in finished if r['temperature']==t))} for t in sorted({r['temperature'] for r in group})]})
    return output


def save_report(out,records):
    summary=aggregate(records)
    (out/'aggregate.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    columns=('repetition','combination','temperature','status','outcome','task_completed','resubmits','calls','api_requests','logged_calls','logged_tokens','logged_private_marker_hits','error_type')
    with (out/'runs.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore'); writer.writeheader(); writer.writerows(records)
    with (out/'check_frequencies.csv').open('w',newline='') as stream:
        writer=csv.writer(stream); writer.writerow(('combination','check_text','frequency'))
        for item in summary:
            for scope,count in item['checks_exact_text_frequency'].items(): writer.writerow((item['combination'],scope,count))
    lines=['# MiniMax重复实验','', '这批结果仍然只是行为分布的经验观测，不是数学模型参数的拟合值，参数校准是后续工作。',
           '温度按重复编号在预注册温度列表中循环，不向不支持的API伪传seed。每组用相同温度序列；全部场景文件及ground truth固定，并逐run校验哈希。',
           '完成统计只含正常返回的run；错误/中断单列。检查范围按原始文本计频，语义近义项不合并。Wilson区间为完成返回样本的描述性二项区间，混合温度与服务依赖可能限制其解释。',
           '', '|组合|正常返回|报错|业务结局计数|重提交分布|私有标记命中|记录token|', '|---|---:|---:|---|---|---:|---:|']
    for item in summary:
        lines.append(f"|{item['combination']}|{item['finished_runs']}|{item['error_runs']}|{item['outcomes']}|{item['resubmit_distribution']}|{item['private_marker_hits_finished']}|{item['logged_tokens_all']}|")
    lines+=['','Token及调用统计为已记录响应，不含失败后无法取得usage的API请求，不等于总账单。私有标记未命中不证明没有其他形式的泄露。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


def execute(config,case,env_file,out):
    out.mkdir(parents=True,exist_ok=False)
    hashes=case_hashes(case)
    signing_keys={org:keypair() for org in ORGS}
    (out/'manifest.json').write_text(json.dumps({'config':asdict(config),'estimate':estimate(config),'case_hashes':hashes,
        'code_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
        'signing_public_keys':{org:pair[1] for org,pair in signing_keys.items()},
        'execution_authorization':'explicit --execute after user confirmation required'},ensure_ascii=False,indent=2))
    records=[]
    with ThreadPoolExecutor(max_workers=config.workers) as pool:
        futures=[pool.submit(run_record,i,combo,config,case,env_file,out,hashes,signing_keys) for i in range(config.repetitions) for combo in config.combinations]
        try:
            for future in as_completed(futures):
                record=future.result(); records.append(record)
                print(f"finished run={record['repetition']} {record['combination']} status={record['status']}",flush=True)
                save_report(out,sorted(records,key=lambda r:(r['repetition'],r['combination'])))
        except KeyboardInterrupt:
            for future in futures: future.cancel()
            raise
    return records


def collect_existing(out):
    """Recover a killed batch without starting any API requests or reruns."""
    manifest=json.loads((out/'manifest.json').read_text())
    config=manifest['config']; records=[]
    for index in range(config['repetitions']):
        for combo in config['combinations']:
            protocol,objective=combo.split(':')
            folder=out/f'run_{index:03d}'/f'{protocol}_{objective}'
            record_path=folder/'record.json'
            if record_path.exists():
                records.append(json.loads(record_path.read_text())); continue
            summary=folder/f'{protocol}_{objective}.json'
            logs=list(folder.glob('*.jsonl'))+list(folder.glob('*.jsonl.interrupted'))
            if summary.exists():
                record=json.loads(summary.read_text()); record['status']='finished'
            else:
                record={'status':'interrupted' if folder.exists() else 'not_started'}
                for log in logs:
                    if log.suffix=='.jsonl': log.rename(log.with_suffix('.jsonl.interrupted'))
                logs=list(folder.glob('*.jsonl.interrupted'))
            events=[]
            for log in logs:
                for line in log.read_text().splitlines():
                    try: events.append(json.loads(line))
                    except json.JSONDecodeError: record['truncated_log_line']=True
            record.update(repetition=index,combination=combo,temperature=config['temperatures'][index%len(config['temperatures'])],
                          logged_calls=len(events),logged_api_requests=sum(e['usage'].get('attempts',1) for e in events),
                          logged_tokens=sum(e['usage'].get('total_tokens',0) for e in events),
                          logged_private_marker_hits=sum(e['private_marker_leaked'] for e in events),
                          checks_selected=[c for e in events for c in e['decision']['checks']])
            records.append(record)
    save_report(out,records)
    return records


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--repetitions',type=int,default=15)
    parser.add_argument('--combinations',nargs='+',default=list(DEFAULT_COMBINATIONS)); parser.add_argument('--temperatures',type=float,nargs='+',default=[.2,.5,.8])
    parser.add_argument('--workers',type=int,default=2); parser.add_argument('--env-file',type=Path,default=Path('/home/cjy/cyberagent/.env'))
    parser.add_argument('--case',type=Path,default=ROOT/'examples/letter_of_credit'); parser.add_argument('--out',type=Path,default=Path('results/minimax_batch_v2'))
    parser.add_argument('--estimate-out',type=Path); parser.add_argument('--execute',action='store_true')
    parser.add_argument('--collect-only',action='store_true',help='recover reports after a stopped batch; never calls API')
    args=parser.parse_args(); config=BatchConfig(args.repetitions,tuple(args.combinations),tuple(args.temperatures),args.workers)
    if args.collect_only:
        if args.execute: parser.error('--collect-only cannot be combined with --execute')
        collect_existing(args.out); return
    report=estimate(config); print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    if args.estimate_out:
        args.estimate_out.parent.mkdir(parents=True,exist_ok=True)
        with args.estimate_out.open('x') as stream: json.dump(report,stream,ensure_ascii=False,indent=2)
    if not args.execute:
        print('ESTIMATE ONLY: waiting for user confirmation; no API requests made.'); return
    execute(config,args.case,args.env_file,args.out)


if __name__=='__main__': main()
