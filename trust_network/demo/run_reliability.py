"""Cost-gated policy-only experiment; default performs no API calls."""
from dataclasses import asdict
from pathlib import Path
import argparse
import json
from trust_network.demo.documents import keypair
from trust_network.demo.authority import AuthorityClient,RemoteAuthorityClient,ISSUER
from trust_network.demo.approval_scenario import ACTORS
from trust_network.demo.approval_runtime import ModelActor,run_workflow
from trust_network.demo.approval_evaluation import evaluate,report,validate_audit
from trust_network.demo.approval_accountability import postmortem
from trust_network.demo.reliability import RiskConfig,POLICIES

ROOT=Path(__file__).resolve().parents[2]


def estimate():
    history=json.loads((ROOT/'results/minimax_batch_v2/aggregate.json').read_text())
    group=next(g for g in history if g['combination']=='verified_certificate:resp')
    tokens_per_call=group['logged_tokens_all']/group['logged_calls_all']
    return {'cases':4,'policies':list(POLICIES),'temperatures':[.2,.5,.8],
        'planned_runs':36,'runs_per_policy':12,'planning_actor_calls':144,
        'planning_tokens':round(144*tokens_per_call),'max_actor_calls':216,
        'max_model_http_attempts_with_format_retry':432,'max_authority_queries':108,
        'basis':{'historical_logged_calls':85,'historical_tokens':180854,
                 'historical_tokens_per_call':tokens_per_call},
        'interpretation':'36run×规划4次业务调用；每组织最多2次、每run最多6次。权威查证是确定性组织服务，无LLM评估调用。',
        'budget_warning':'新场景没有实测用量；历史均值是规划参照，不是上限或账单。失败usage可能缺失。',
        'requires_confirmation':True}


def execute(cases,out,env_file,config,actor_endpoints=None,authority_endpoints=None):
    # Execution remains explicit; no preflight path reads credentials.
    out.mkdir(parents=True,exist_ok=False)
    keys={org:keypair() for org in (*ACTORS,ISSUER,'runtime')}
    public_keys={org:pair[1] for org,pair in keys.items()}
    manifest={'config':asdict(config),'estimate':estimate(),'public_keys':public_keys,
              'actor_endpoints':actor_endpoints,'authority_endpoints':authority_endpoints,
              'case_public_inputs':{p.name:json.loads((p/'public/bundle.json').read_text()) for p in cases},
              'model':'configured MiniMax, resolved only during execution'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    records=[]
    for repeat,temperature in enumerate((.2,.5,.8)):
        for index,case in enumerate(cases):
            # Rotate order independently of truth, avoiding always-A-first timing.
            shift=(index+repeat)%3
            order=POLICIES[shift:]+POLICIES[:shift]
            for policy in order:
                folder=out/f'repeat_{repeat}'/case.name/policy
                case_keys=dict(keys)
                authority=AuthorityClient(case/'organizations/buyer_authority/registry.json',keys[ISSUER][0])
                if authority_endpoints is not None:
                    service=authority_endpoints[case.name]
                    case_keys[ISSUER]=(None,service['public_key'])
                    authority=RemoteAuthorityClient(service['endpoint'])
                runtime=run_workflow(case,folder,policy,ModelActor(case,env_file,actor_endpoints),authority,case_keys,
                    config=config,temperature=temperature,request_id=f'{case.name}-{repeat}')
                record=evaluate(case,runtime)
                record.update(case=case.name,temperature=temperature,repeat=repeat)
                validate_audit(folder,{o:p[1] for o,p in case_keys.items()})
                (folder/'accountability.json').write_text(json.dumps(postmortem(folder,record),ensure_ascii=False,indent=2))
                records.append(record); report(out,records,'MiniMax真实调用：运行时Reliability Policy实验')
                print(f"{case.name} {policy} T={temperature} {runtime['outcome']}",flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',type=Path,default=ROOT/'examples/authorization_v4')
    parser.add_argument('--out',type=Path,default=Path('results/reliability_v4_minimax'))
    parser.add_argument('--env-file',type=Path,default=Path('/home/cjy/cyberagent/.env'))
    parser.add_argument('--omission-weight',type=float,default=0.)
    parser.add_argument('--actor-endpoints',type=Path)
    parser.add_argument('--authority-endpoints',type=Path)
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    print(json.dumps(estimate(),ensure_ascii=False,indent=2))
    if args.execute:
        execute(sorted(args.cases.glob('case_*')),args.out,args.env_file,RiskConfig(omission_weight=args.omission_weight),
                json.loads(args.actor_endpoints.read_text()) if args.actor_endpoints else None,
                json.loads(args.authority_endpoints.read_text()) if args.authority_endpoints else None)
    else: print('Preflight only. No MiniMax requests. Await experiment approval.')


if __name__=='__main__': main()
