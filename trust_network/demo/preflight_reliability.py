"""Offline preflight with an explicit always-PASS fixture, never a fake LLM."""
from dataclasses import asdict
from pathlib import Path
import argparse
import hashlib
import json
from trust_network.demo.documents import keypair,digest
from trust_network.demo.authority import AuthorityClient,ISSUER
from trust_network.demo.approval_scenario import ACTORS
from trust_network.demo.approval_runtime import run_workflow
from trust_network.demo.approval_evaluation import evaluate,report,validate_audit
from trust_network.demo.approval_accountability import postmortem
from trust_network.demo.reliability import RiskConfig,POLICIES
from trust_network.demo.run_reliability import estimate,ROOT


def always_pass_fixture(org,payload):
    return {'decision':{'action':'pass','checks':[],'findings':[],
                        'public_message':'SCRIPTED FIXTURE: proposes continuation'},
            'usage':{'attempts':0,'total_tokens':0}}


def prepare(cases,out):
    out.mkdir(parents=True,exist_ok=False)
    keys={o:keypair() for o in (*ACTORS,ISSUER,'runtime')}
    public_keys={o:p[1] for o,p in keys.items()}
    config=RiskConfig(); records=[]; public_views={}; audit_events=0; first_inputs={}
    # Preparation may read truth to verify scenario construction. This module
    # cannot perform a paid API call: its only actor is the explicit fixture.
    for case in cases:
        bundle=json.loads((case/'public/bundle.json').read_text())
        assert len({bundle[k]['model'] for k in ('order','invoice','packing_list','transport_order')})==1
        assert len({bundle[k]['quantity'] for k in ('order','invoice','packing_list','transport_order')})==1
        intake=json.loads((case/'intake.json').read_text())
        public_views[case.name]={'view_hash':digest({'bundle':bundle,'intake':intake}),
                                'authorized_truth':json.loads((case/'ground_truth.json').read_text())['authorized']}
        for policy in POLICIES:
            folder=out/'scripted_runs'/case.name/policy
            runtime=run_workflow(case,folder,policy,always_pass_fixture,
                AuthorityClient(case/'organizations/buyer_authority/registry.json',keys[ISSUER][0]),keys,
                config=config,request_id=f'{case.name}-fixture')
            row=evaluate(case,runtime); row['case']=case.name; row['actor_mode']='scripted_always_pass'
            records.append(row)
            audit_events+=validate_audit(folder,public_keys)
            (folder/'accountability.json').write_text(json.dumps(postmortem(folder,row),ensure_ascii=False,indent=2))
            events=[json.loads(line) for line in (folder/'audit.jsonl').read_text().splitlines()]
            first_inputs[(case.name,policy)]=next(e['visible_input'] for e in events if e['kind']=='actor_request')
    for case in cases:
        assert all(first_inputs[(case.name,p)]==first_inputs[(case.name,'autonomous')] for p in POLICIES)
    for a,b in (('case_01','case_02'),('case_03','case_04')):
        assert public_views[a]['view_hash']==public_views[b]['view_hash']
        assert public_views[a]['authorized_truth']!=public_views[b]['authorized_truth']
    summaries=report(out,records,'离线脚本夹具：不是MiniMax实验结果')
    assert [s['verification_count'] for s in summaries]==[0,4,2]
    assert [s['unsafe_completion_count'] for s in summaries]==[2,0,1]
    costs={s['policy']:s['verification_cost'] for s in summaries}
    assert costs['risk_aware']<costs['verify_all']
    preserved=json.loads((ROOT/'results/round3_preflight/preserved_sha256.json').read_text())
    changed=[name for name,sha in preserved.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha]
    assert not changed
    manifest={'actor_mode':'scripted_always_pass','real_minimax_calls':0,'tokens':0,
        'risk_config':asdict(config),'public_keys':public_keys,'public_view_pairs':public_views,
        'audited_events':audit_events,'preserved_historical_files':len(preserved),
        'self_checks':{'public_fields_do_not_determine_truth':True,'policy_can_veto_llm_pass_proposal':True,
                       'selective_verification_reduces_real_query_count':True},'estimate':estimate()}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    (out/'estimate.json').write_text(json.dumps(estimate(),ensure_ascii=False,indent=2))
    return manifest


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--cases',type=Path,default=ROOT/'examples/authorization_v4')
    parser.add_argument('--out',type=Path,default=Path('results/reliability_v4_preflight'))
    args=parser.parse_args(); result=prepare(sorted(args.cases.glob('case_*')),args.out)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
