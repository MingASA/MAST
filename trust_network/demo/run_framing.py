"""Round 3: six paired repetitions, one bank-only framing intervention."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import asdict
from pathlib import Path
import csv
import json
from trust_network.demo.run import run_one,ROOT,ORGS
from trust_network.demo.run_batch import case_hashes,wilson
from trust_network.demo.framing import CONDITIONS
from trust_network.demo.documents import keypair
from trust_network.demo.discrepancy import replay_banks,evaluate_detection
from trust_network.demo.provider import ProviderConfig


def estimate():
    groups=json.loads((ROOT/'results/minimax_batch_v2/aggregate.json').read_text())
    fixed=next(g for g in groups if g['combination']=='verified_certificate:resp')
    # Same protocol and legacy goal as A; B adds a short bank-only sentence.
    workflow_calls=12*fixed['logged_calls_all']/fixed['attempted_runs']
    workflow_tokens=12*fixed['logged_tokens_all']/fixed['attempted_runs']
    return {'conditions':2,'repetitions_per_condition':6,'workflow_runs':12,'temperatures':[.2,.5,.8,.2,.5,.8],
            'basis':'第二轮protocol2/resp的15个run记录85次调用、180854 token；失败请求缺失usage，估算不是账单或上限。',
            'workflow_calls_estimate':workflow_calls,'workflow_tokens_estimate':round(workflow_tokens),
            'extra_framing_token_allowance':3000,'max_extraction_logical_calls':12,
            'extraction_tokens_allowance':36000,'total_logical_calls_estimate_upper':workflow_calls+12,
            'total_tokens_planning_estimate':round(workflow_tokens)+3000+36000,
            'evaluation_policy':'每个有银行实际暴露的正常run最多一次盲态抽取；无暴露不调用评估模型。格式重试可能额外调用。',
            'historical_exposure':'第二轮30个run、44次银行决策，暴露0/44；本批次改为暴露受控。',
            'experiment_design':'controlled_exposure',
            'budget_note':'保留历史全流程用量作为规划参照：省去前置决策，但银行补证/返工可能增加；抽取按12次预留，不假定仍为零暴露。',
            'requires_confirmation':True}


def run_condition(index,condition,case,env_file,out,hashes,keys):
    folder=out/f'pair_{index:02d}'/condition.name; folder.mkdir(parents=True,exist_ok=False)
    temperature=(.2,.5,.8)[index%3]
    record={'pair':index,'condition':condition.name,'temperature':temperature,'status':'workflow_error',
            'flagged_invoice_discrepancy':None}
    try:
        if case_hashes(case)!=hashes: raise ValueError('inputs changed')
        summary=run_one(case,env_file,folder,'verified_certificate',condition.objective,
                        temperature=temperature,signing_keys=keys,controlled_bank_input=case/'controlled_bank_input.json')
        record.update(summary)
        record['status']='evaluation_error'
        events=[json.loads(line) for line in (folder/f'verified_certificate_{condition.objective}.jsonl').read_text().splitlines()]
        evidence=replay_banks(case,events,case/'controlled_bank_input.json')
        (folder/'blinded_evidence.json').write_text(json.dumps([asdict(e) for e in evidence],ensure_ascii=False,indent=2))
        detection=evaluate_detection(evidence,ProviderConfig.load(env_file),folder/'extraction.json')
        record.update(asdict(detection)); record['status']='finished'
    except Exception as exc:
        record['error_type']=type(exc).__name__
        record['error']='workflow or evaluation failed; no completed label substituted'
        if record['status']=='workflow_error':
            for log in folder.glob('*.jsonl'): log.rename(log.with_suffix('.jsonl.interrupted'))
    finally:
        if case_hashes(case)!=hashes:
            record['status']='input_error'; record['flagged_invoice_discrepancy']=None
        logs=list(folder.glob('*.jsonl'))+list(folder.glob('*.jsonl.interrupted'))
        events=[json.loads(line) for log in logs for line in log.read_text().splitlines()]
        record['logged_calls']=len(events)
        record['logged_api_requests']=sum(e['usage'].get('attempts',1) for e in events)
        record['logged_tokens']=sum(e['usage'].get('total_tokens',0) for e in events)
        record['private_marker_hits']=sum(e['private_marker_leaked'] for e in events)
        record['check_frequencies']=dict(Counter(c for e in events for c in e['decision']['checks']))
        if (folder/'extraction.json').exists():
            record['evaluation_usage']=json.loads((folder/'extraction.json').read_text())['usage']
        (folder/'record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    return record


def report(out,records):
    summaries=[]
    for condition in ('A','B'):
        group=[r for r in records if r['condition']==condition]
        valid=[r for r in group if r['status']=='finished']
        positives=sum(r['flagged_invoice_discrepancy'] for r in valid)
        exposed=sum(r['bank_exposed'] for r in valid)
        checks=Counter()
        for r in valid: checks.update(r['check_frequencies'])
        check_items=sum(sum(r['check_frequencies'].values()) for r in valid)
        summaries.append({'experiment_design':'controlled_exposure','historical_exposure':'0/44','condition':condition,'planned_runs':6,'recorded_runs':len(group),'valid_runs':len(valid),
            'failed_runs':len(group)-len(valid),'status_counts':dict(Counter(r['status'] for r in group)),
            'flagged_invoice_discrepancy_count':positives,
            'flagged_invoice_discrepancy_rate':positives/len(valid) if valid else None,
            'descriptive_wilson95':wilson(positives,len(valid)),
            'temperature_strata':[{
                'temperature':t,'valid_runs':sum(r['temperature']==t for r in valid),
                'flagged_count':sum(r['flagged_invoice_discrepancy'] for r in valid if r['temperature']==t),
                'failed_runs':sum(r['temperature']==t and r['status']!='finished' for r in group),
                'wilson95':wilson(sum(r['flagged_invoice_discrepancy'] for r in valid if r['temperature']==t),sum(r['temperature']==t for r in valid))
                } for t in (.2,.5,.8)],
            'runs_with_bank_exposure':exposed,'detection_rate_given_exposure':positives/exposed if exposed else None,
            'outcomes_background':dict(Counter(r.get('outcome') for r in valid)),
            'resubmits_background':dict(Counter(r['resubmits'] for r in valid)),
            'check_frequencies_background':dict(checks),
            'check_items_total_valid':check_items,
            'check_items_mean_valid_run':check_items/len(valid) if valid else None,
            'private_marker_hits':sum(r['private_marker_hits'] for r in group),
            'logged_workflow_calls':sum(r['logged_calls'] for r in group),
            'logged_workflow_api_requests':sum(r['logged_api_requests'] for r in group),
            'logged_workflow_tokens':sum(r['logged_tokens'] for r in group),
            'evaluation_api_requests':sum(r.get('evaluation_usage',{}).get('attempts',0) for r in group),
            'evaluation_tokens':sum(r.get('evaluation_usage',{}).get('total_tokens',0) for r in group)})
    (out/'aggregate.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2))
    fields=('pair','condition','temperature','status','flagged_invoice_discrepancy','bank_exposed','bank_decisions','outcome','resubmits','logged_calls','logged_tokens','error_type')
    with (out/'runs.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore'); writer.writeheader(); writer.writerows(records)
    lines=['# 第三轮暴露受控实验：银行真实冲突检出率','',
        '历史背景：第二轮30个run、44次银行决策，未修正冲突暴露0/44。本批次在银行入口固定冲突输入，仅回答面对该冲突时framing是否改变检查/查证行为，不能估计自然流程中遇到冲突的概率。',
        '只比较银行resp与resp-omission，其他组织均为resp，协议固定verified_certificate。',
        '这是遗漏责任机制第一次在真实agent上做的小规模检验，不是决定性证据，更大样本或更多场景变体是后续工作。',
        'N=6/组不足以下因果或统计显著性结论，只报告方向和幅度。错误run不计入分母；表中同时列出预定6次和有效样本数，不把失败当作未检出。','',
        '|条件|预定次数|有效run|失败|检出次数|检出率|描述性Wilson 95%区间|银行实际暴露run|暴露条件下检出率|',
        '|---|---:|---:|---:|---:|---|---|---:|---|']
    for s in summaries:
        interval=s['descriptive_wilson95']
        ci='NA' if interval is None else f'[{interval[0]:.3f}, {interval[1]:.3f}]'
        lines.append(f"|{s['condition']}|6|{s['valid_runs']}|{s['failed_runs']}|{s['flagged_invoice_discrepancy_count']}|{s['flagged_invoice_discrepancy_rate']}|{ci}|{s['runs_with_bank_exposure']}|{s['detection_rate_given_exposure']}|")
    rates=[s['flagged_invoice_discrepancy_rate'] for s in summaries]
    if all(rate is not None for rate in rates):
        lines+=['',f'观察到的B−A检出率差：{100*(rates[1]-rates[0]):.2f}个百分点；不作因果或显著性解释。']
    lines+=['','描述性Wilson区间、温度、完成/升级/拒绝、重提交与检查范围频率见aggregate.json和runs.csv。',
        '如银行实际暴露为0，即使主指标为0，也只能说明现有流程不给银行检出原始冲突的机会，不能说明银行没有检出能力或framing无效。完成率不替代主指标。',
        '若两组检出率都接近1，主指标处于天花板，只能说明这个固定输入下两种framing都促成了检出，不能据此判断遗漏责任文本的增量效果；应结合处置动作及更难的后续场景。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


def execute(case,env_file,out):
    out.mkdir(parents=True,exist_ok=False); hashes=case_hashes(case); keys={o:keypair() for o in ORGS}
    from trust_network.demo import framing,discrepancy
    import hashlib
    manifest={'experiment_design':'controlled_exposure','controlled_input':json.loads((case/'controlled_bank_input.json').read_text()),'estimate':estimate(),'case_hashes':hashes,'conditions':[asdict(c) for c in CONDITIONS],
        'objectives':{c.name:{o:framing.objective_text(c.objective,o) for o in ORGS} for c in CONDITIONS},
        'extraction_system':discrepancy.EXTRACTION_SYSTEM,'signing_public_keys':{o:k[1] for o,k in keys.items()},
        'model_decisions_sha256':hashlib.sha256((ROOT/'MODEL_DECISIONS.md').read_bytes()).hexdigest()}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    records=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run_condition,i,c,case,env_file,out,hashes,keys) for i in range(6) for c in CONDITIONS]
        for future in as_completed(futures):
            r=future.result(); records.append(r); report(out,records)
            print(f"pair={r['pair']} condition={r['condition']} status={r['status']} flagged={r['flagged_invoice_discrepancy']}",flush=True)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--env-file',type=Path,default=Path('/home/cjy/cyberagent/.env'))
    parser.add_argument('--case',type=Path,default=ROOT/'examples/letter_of_credit')
    parser.add_argument('--out',type=Path,default=Path('results/framing_v3_controlled'))
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    print(json.dumps(estimate(),ensure_ascii=False,indent=2),flush=True)
    if not args.execute:
        print('PREPARATION ONLY: no API requests; await user confirmation.'); return
    execute(args.case,args.env_file,args.out)


if __name__=='__main__': main()
