"""Small real-model protocol experiment; no hidden fixture or synthetic fallback."""
from pathlib import Path
import argparse
import json
import tempfile
from trust_network.demo.preflight_contract import provision, ProcessAuthority
from trust_network.demo.approval_scenario import ACTORS
from trust_network.demo.contract_workflow import POLICIES, ProcessGateway, run
from trust_network.demo.contract_audit import validate
from trust_network.demo.provider import ProviderConfig


def execute(out, env_file):
    out.mkdir(parents=True,exist_ok=False)
    provider=ProviderConfig.load(env_file)
    manifest={'label':'Real MiniMax gateway pilot; no injected faults',
              'configured_model':provider.model,'policies':list(POLICIES),
              'cases':['approved','unauthorized'],'temperature':.2,'planned_runs':6,
              'purpose':'Check real agent/gateway interaction before broadening human-business scenarios',
              'limitations':'Two alternate authorization worlds; not proof of broad protocol benefit.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    bundle=json.loads(Path('examples/authorization_v4/case_01/public/bundle.json').read_text())
    rows=[]
    for case,approved in (('approved',True),('unauthorized',False)):
        for policy in POLICIES:
            with tempfile.TemporaryDirectory(prefix='contract-real-orgs-') as temporary:
                root=Path(temporary); public,runtime_key=provision(root,policy,approved,None)
                folder=out/case/policy
                result=run(bundle,policy,{org:ProcessGateway(root/org,env_file) for org in ACTORS},
                           public,ProcessAuthority(root/'buyer_authority'),runtime_key,folder)
                verification=validate(folder,public)
                (folder/'public_keys.json').write_text(json.dumps(public,indent=2))
                (folder/'validation.json').write_text(json.dumps(verification,indent=2))
                valid=result['status']=='finished'
                row=dict(result,case=case,authorized_truth=approved,
                         unsafe_completion=(result['committed'] and not approved) if valid else None,
                         approved_completion=(result['committed'] and approved) if valid else None)
                rows.append(row)
                (out/'records.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
                print(f"{case} {policy}: {result['outcome']}; calls={result['logged_api_requests']} tokens={result['tokens']}",flush=True)
    lines=['# 第五轮真实MiniMax网关试运行','',
           '无故障注入、无脚本替代。两种授权世界只验证接口及运行行为，不足以证明一般收益。','',
           '|Protocol|有效/尝试|未授权提交|正常完成|验证成本|修正次数|已记录API|已记录token|',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for policy in POLICIES:
        group=[r for r in rows if r['policy']==policy]; valid=[r for r in group if r['status']=='finished']
        totals=[sum(r[k] for r in valid) for k in ('unsafe_completion','approved_completion')]
        totals += [sum(r[k] for r in group) for k in ('verification_cost','repairs','logged_api_requests','tokens')]
        lines.append('|'+policy+f'|{len(valid)}/{len(group)}|'+'|'.join(map(str,totals))+'|')
    lines+=['','失败usage未知，不能把日志中的0视为实际零消耗。未实际跨物理设备部署。',
            '本试运行不替代人工判断场景、错误信息传播实验或大样本结论。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,default=Path('/home/cjy/cyberagent/.env'))
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    if args.execute: execute(args.out,args.env_file)
    else: print('Plan: 6 runs, up to 54 actor attempts / 108 model HTTP attempts; no API calls without --execute.')
