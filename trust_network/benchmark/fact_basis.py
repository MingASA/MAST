"""Offline settlement-basis matrix, kept separate from generic signed_false.

The ledger is independently provisioned; the runtime never receives truth.
Five downstream roles share the same fact policy. Publishers remain fixed
services so the first control opportunity is a downstream explicit proposal.
"""
import argparse
import hashlib
import json
from pathlib import Path
from trust_network.benchmark.workflow.spec import workload,ARMS,OWNERS
from trust_network.benchmark.workflow.backend import MemoryBackend,ProcessBackend
from trust_network.benchmark.workflow.engine import Workflow
from trust_network.benchmark.workflow.evaluate import audit,score
from trust_network.demo.fact_evidence import scope_key
from trust_network.demo.documents import digest

POLICIES=('closure_only','conflict_triggered','verify_all','selective')
CASES=('confirmed_basis','unconfirmed_settlement_basis','conflicting_basis','authority_unknown')


def run(case,policy,backend='memory',directory=None):
    f=workload();ledger={scope_key(f['workflow'],f['roots'][o]['body']['fact']):
        {'cents':125 if o=='A' and case=='unconfirmed_settlement_basis' else 120 if o=='A' and case=='conflicting_basis' else 100,
         'version':'record-v1','status':'confirmed'} for o in ('A','C')}
    if case=='authority_unknown':ledger.pop(scope_key(f['workflow'],f['roots']['A']['body']['fact']))
    private={'buyer':{'settlement_registry':ledger}}
    b=(MemoryBackend(f,ARMS['dependency'],private_state=private) if backend=='memory' else
       ProcessBackend(f,ARMS['dependency'],directory,private_state=private))
    config={'policy':policy,'authority':'buyer','forward_loss':1,'query_cost':1,'threshold':2}
    for owner in OWNERS:
        if owner in ('source','buyer'):continue
        if backend=='memory':b.configs[owner]['fact_policy']=config
        else:
            path=Path(directory)/owner/'config.json';c=json.loads(path.read_text());c['fact_policy']=config;path.write_text(json.dumps(c))
    raw,truth=Workflow(b,'conflicting_sources' if case=='conflicting_basis' else 'active','dependency').run()
    raw['case']=case;raw['arm']=policy;raw['fact_config']=config
    # Evaluator labels measure completion without the required confirmed basis;
    # UNKNOWN is unsupported execution, not proof that the amount is false.
    truth={'faults':[],'scope':'confirmed_settlement_basis_required','authority_registry':ledger}
    if case!='confirmed_basis':truth['faults']=[{'target':digest(f['roots']['A']),'issuer':'source',
        'kind':case,'tick':0,'origin_hop':0}]
    result=score(raw,truth,audit(raw))
    result['fact_queries']=sum(p['body'].get('fact_verification_calls',0) for p in raw['batches'])
    result['disputed_claims']=len({c for p in raw['batches'] for g in p['body'].get('fact_checks',{}).values() for c in g['disputed']})
    if case=='confirmed_basis':result.update(fault_expected=False,fault_trial_evaluable=False,validity_reason='active_control')
    return raw,truth,result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--backend',choices=('memory','process'),default='memory')
    parser.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES));parser.add_argument('--policies',nargs='+',choices=POLICIES,default=list(POLICIES))
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False);rows=[]
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('trust_network').rglob('*.py')}
    for case in args.cases:
        for policy in args.policies:
            folder=args.out/(case+'__'+policy);folder.mkdir()
            raw,truth,metrics=run(case,policy,args.backend,folder/'organizations')
            for name,value in [('trace',raw),('truth',truth),('metrics',metrics)]:
                (folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2))
            rows.append({'case':case,'policy':policy,**metrics})
    (args.out/'metrics.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    (args.out/'manifest.json').write_text(json.dumps({'decision_source':'scripted','new_model_calls':0,'source_hashes':sources,'backend':args.backend},indent=2))
    lines=['# 结算依据事实门禁：离线矩阵','','UNKNOWN 的错误完成表示无确认依据执行，不证明金额必然为假。所有模型决定为脚本；没有新增付费调用。','',
        '|条件|策略|无依据完成/4|安全完成/4|错误触达组织|补证查询|争议声明|','|---|---|---:|---:|---:|---:|---:|']
    for r in rows:lines.append(f"|{r['case']}|{r['policy']}|{r['unsafe_completed']}|{r['safe_completed']}|{r['error_accepting_organizations']}|{r['fact_queries']}|{r['disputed_claims']}|")
    (args.out/'report.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
