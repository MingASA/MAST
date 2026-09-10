"""Offline by default. Live mode requires an explicit paid-call flag and caps."""
import argparse
import hashlib
import json
from pathlib import Path
from trust_network.demo.documents import digest
from .spec import ARMS,CASES,workload,factors,OWNERS
from .backend import MemoryBackend,ProcessBackend
from .engine import Workflow
from .evaluate import audit,score


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def preflight(cases,arms,backend,mode,max_decisions,max_attempts):
    return {'benchmark':'cross-org-workflow-v1','mode':mode,'backend':backend,'cases':cases,'arms':arms,
        'arm_factors':factors(),'organizations':list(OWNERS),'workflows':len(cases)*len(arms),'tasks_per_workflow':4,
        'max_model_decisions':len(cases)*len(arms)*max_decisions if mode=='live' else 0,
        'max_provider_attempts':len(cases)*len(arms)*max_attempts if mode=='live' else 0,
        'max_output_tokens_per_attempt':2048,'input_tokens':'must estimate from archived full prompts before paid pilot; no numeric total fabricated',
        'paid_calls_started':False,'initial_model_stages':18,'recovery_and_verify_share_same_cap':True,
        'limits':['source_and_buyer_are_authoritative_document_services_not_live_models',
                  'local_processes_not_physical_hosts','simulated_business_effects',
                  'root_freshness_does_not_prove_private_fact_truth']}


def execute(out,cases,arms,backend='memory',mode='replay',env_file=None,allow_paid=False,tape=None,max_decisions=32,max_attempts=64):
    if mode=='live' and (not allow_paid or backend!='process' or env_file is None):
        raise ValueError('live requires process backend, explicit --allow-paid and --env-file')
    if mode=='live' and len(cases)*len(arms)>6:raise ValueError('v1 live pilot is capped at six workflows; select explicit cases and arms')
    if mode=='live' and tape is not None:raise ValueError('live and fixed tape cannot be combined')
    if any(c not in CASES for c in cases) or any(a not in ARMS for a in arms):raise ValueError('unknown matrix entry')
    if type(max_decisions) is not int or max_decisions<=0 or type(max_attempts) is not int or max_attempts<2:
        raise ValueError('invalid decision/provider cap')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[3]
    source_hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'trust_network').rglob('*.py'))}
    manifest={**preflight(cases,arms,backend,mode,max_decisions,max_attempts),'status':'running','source_hashes':source_hashes,
        'decision_source':'live' if mode=='live' else 'fixed_tape' if tape is not None else 'scripted',
        'tape_hash':digest(tape) if tape is not None else None}
    write(out/'manifest.json',manifest);rows=[];paid_started=False
    try:
        for case in cases:
            for arm in arms:
                folder=out/(case+'__'+arm);folder.mkdir()
                private={'source':{'actual_cents':125 if case=='signed_false' else 120 if case=='conflicting_sources' else 100}}
                implementation=(MemoryBackend(workload(),ARMS[arm],private_state=private) if backend=='memory' else
                    ProcessBackend(workload(),ARMS[arm],folder/'organizations',env_file,allow_paid,private))
                runner=Workflow(implementation,case,arm,mode=mode,tape=tape,max_decisions=max_decisions,max_attempts=max_attempts)
                try:
                    raw,truth=runner.run()
                    paid_started=paid_started or runner.decisions.calls>0
                    write(folder/'trace.json',raw);write(folder/'truth.json',truth)
                    assessment=audit(raw);metrics=score(raw,truth,assessment)
                    write(folder/'audit.json',assessment);write(folder/'metrics.json',metrics)
                    write(folder/'decision_tape.json',{d['stage']:d['draft'] for d in raw['decisions']})
                    rows.append({'case':case,'arm':arm,'mode':mode,'workload_hash':raw['workload_hash'],**metrics})
                    write(out/'metrics.json',rows)
                except Exception:
                    paid_started=paid_started or runner.decisions.calls>0
                    write(folder/'partial_events.json',runner.bus.events)
                    write(folder/'partial_decisions.json',runner.decisions.records)
                    raise
        # Each within-case comparison starts from exactly the same public workload.
        for case in cases:
            if len({r['workload_hash'] for r in rows if r['case']==case})!=1:raise ValueError('unpaired public workload')
        lines=['# 跨组织工作流 benchmark v1','',
            f'模式：{mode}；后端：{backend}；决定来源：{manifest["decision_source"]}。共{len(rows)}条workflow，每条4项业务任务。',
            '签名和私有事实正确性分别评估。跨任务恢复绑定失败另列，不伪装成已发生金额错误。','',
            '|条件|机制|错误完成/4|业务安全完成/4|恢复成功|错误接收组织|无关误冻|查证|跨任务绑定完成|',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for r in rows:lines.append(f"|{r['case']}|{r['arm']}|{r['unsafe_completed']}|{r['safe_completed']}|{r['recovery_successes']}|{r['error_accepting_organizations']}|{r['unrelated_overfreeze']}|{r['verification_queries']}|{r['invalid_binding_completed']}|")
        lines += ['', '## 运行有效性计数', '',
            '|条件|机制|实际注入故障|模型 hold|模型无效动作|worker error|未实现阶段|上游未实现任务|',
            '|---|---|---:|---:|---:|---:|---:|---:|']
        for r in rows:
            lines.append(f"|{r['case']}|{r['arm']}|{r['faults_realized']}|{r['model_holds']}|{r['model_invalid_actions']}|{r['worker_errors']}|{r['unrealized_stages']}|{r['upstream_unrealized_tasks']}|")
        lines+=['','## 必须保留的解释边界','',
            '- simple_dependency_gate / dependency / verify_all 在默认配置下有相同检查覆盖，是等价校准，不应虚构机制差异。',
            '- dependency_push 的通知按虚拟时钟投递；late_notice 不保证在动作前到达。',
            '- scripted决定不是LLM能力结果；fixed_tape缺失阶段会hold，不补造批准。live样本单独归档。',
            '- 来源身份匹配不等于事实责任；无本地签名顺序证明，不指控通知后违规使用。',
            '- 冲突与签名事实错误可能被所有当前策略漏过；这是检测边界，不删除失败案例。']
        (out/'report.md').write_text('\n'.join(lines)+'\n')
        cases_text=['# 机制案例','']
        for r in rows:
            cases_text += [f"## {r['case']} / {r['arm']}",
                f"错误完成 {r['unsafe_completed']}/4；错误触达组织 {r['error_accepting_organizations']}；恢复 {r['recovery_successes']}；查证 {r['verification_queries']}。",
                f"检测记录：`{json.dumps(r['fault_detection'],ensure_ascii=False)}`",
                f"停止原因：`{json.dumps(r['recovery_stops'],ensure_ascii=False)}`",'']
        (out/'mechanism_cases.md').write_text('\n'.join(cases_text))
        final_hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'trust_network').rglob('*.py'))}
        if source_hashes!=final_hashes:raise ValueError('source changed during run')
        from trust_network.benchmark.accountability_cases import evaluate_cases
        write(out/'accountability_calibration.json',evaluate_cases())
        manifest['status']='completed'
    except Exception as exc:
        manifest['status']='failed';manifest['error']=type(exc).__name__;raise
    finally:
        manifest['paid_calls_started']=paid_started
        write(out/'manifest.json',manifest)
        hashes={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('signing.key','integrity.json')}
        write(out/'integrity.json',hashes)
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path);p.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES))
    p.add_argument('--arms',nargs='+',choices=ARMS,default=list(ARMS));p.add_argument('--backend',choices=('memory','process'),default='memory')
    p.add_argument('--mode',choices=('replay','live'),default='replay');p.add_argument('--env-file',type=Path)
    p.add_argument('--allow-paid',action='store_true');p.add_argument('--preflight',action='store_true');p.add_argument('--tape',type=Path)
    p.add_argument('--max-model-decisions',type=int,default=32);p.add_argument('--max-provider-attempts',type=int,default=64)
    args=p.parse_args()
    if args.preflight or args.out is None:
        print(json.dumps(preflight(args.cases,args.arms,args.backend,args.mode,args.max_model_decisions,args.max_provider_attempts),ensure_ascii=False,indent=2));return
    execute(args.out,args.cases,args.arms,args.backend,args.mode,args.env_file,args.allow_paid,
            json.loads(args.tape.read_text()) if args.tape else None,args.max_model_decisions,args.max_provider_attempts)

if __name__=='__main__':main()
