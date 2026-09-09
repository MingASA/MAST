"""Real multi-organization negotiation pilot; no fault injection or fixture fallback."""
from pathlib import Path
from dataclasses import asdict
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from trust_network.demo.documents import keypair, Certificate, Decision, digest
from trust_network.demo.negotiation import OWNERS, CommitmentBook, ExecutionSink, AutonomousExecutionSink
from trust_network.demo.negotiation_worker import verify


def provision(case,root):
    public={}
    runtime_key,runtime_public=keypair(); public['runtime']=runtime_public
    for owner in OWNERS:
        directory=root/owner; directory.mkdir()
        key,pub=keypair(); public[owner]=pub
        path=directory/'signing.key'; path.write_bytes(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
        path.chmod(0o600)
        for name in ('state.json','private.md'): shutil.copyfile(case/owner/name,directory/name)
    for owner in OWNERS:
        (root/owner/'config.json').write_text(json.dumps({'organization':owner,'public_keys':public}))
    return public,runtime_key


def run_case(case,out,env_file,*,binding_mode='dependency',autonomous=False,selective=False,rate_update=False,supply_update=False,repair_mode=False,frontier=False,compact_repair=False):
    out.mkdir(parents=True,exist_ok=False)
    public_request=json.loads((case/'public.json').read_text()); workflow=uuid.uuid4().hex
    calls=0; api=0; tokens=0; queries=0; outcome='incomplete'; final=None
    from trust_network.demo.verification_schedule import VerificationSchedule
    schedule=VerificationSchedule(OWNERS); blockers=[]
    with tempfile.TemporaryDirectory(prefix='negotiation-orgs-') as temporary:
        root=Path(temporary); public,runtime_key=provision(case,root)
        (out/'public_keys.json').write_text(json.dumps(public,indent=2))
        book=CommitmentBook(public,workflow,binding_mode); messages=[]
        events=[{'kind':'start','schema_version':2,'workflow_id':workflow,'public_request':public_request,
                 'binding_mode':binding_mode,'protocol':'autonomous' if autonomous else binding_mode}]
        def call(owner,operation,**kwargs):
            nonlocal calls,api,tokens
            request={'operation':operation,'public_request':public_request,'workflow_id':workflow,
                     'request_id':uuid.uuid4().hex,**kwargs}
            request=json.loads(json.dumps(request))  # Freeze the actual wire input before later message appends.
            if operation!='attest': calls+=1
            events.append({'kind':'request','owner':owner,'request':request})
            process=subprocess.run([sys.executable,'-m','trust_network.demo.negotiation_worker',
                '--organization-dir',str(root/owner),'--env-file',str(env_file)],
                input=json.dumps(request),text=True,capture_output=True,timeout=120)
            if process.returncode: raise RuntimeError('organization process failed; raw response withheld')
            response=json.loads(process.stdout)
            if 'message' in response:
                body=verify(response['message'],owner,public[owner],workflow)
                if body['request_id']!=request['request_id'] or body['input_hash']!=digest(request):
                    raise ValueError('organization response is not bound to request')
            api+=response.get('usage',{}).get('attempts',0); tokens+=response.get('usage',{}).get('total_tokens',0)
            events.append({'kind':'response','owner':owner,'response':response,'received_at':time.time()})
            (out/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
            return response
        try:
            for owner in ('supplier','carrier'):
                feedback=[]
                for attempt in range(2):
                    reply=call(owner,'offer',messages=messages,feedback=feedback)
                    if 'message' in reply:
                        verify(reply['message'],owner,public[owner],workflow)
                        messages.append(reply['message']); break
                    feedback=reply['feedback']
                else: raise ValueError('owner could not produce a valid resource offer')
            if rate_update:
                # Explicit experiment event, outside the policy's visible inputs.
                # Signed earlier quotes are estimates, not firm reservations.
                state_path=root/'carrier'/'state.json'
                state=json.loads(state_path.read_text())
                for service in state['services'].values(): service['price']+=100
                state_path.write_text(json.dumps(state))
            if supply_update:
                state_path=root/'supplier'/'state.json'
                state=json.loads(state_path.read_text())
                state['lots']={name+'_replacement':value for name,value in state['lots'].items()}
                state_path.write_text(json.dumps(state))
            feedback=[]
            for attempt in range(3):
                reply=call('buyer','plan',messages=messages,feedback=feedback)
                if 'message' not in reply:
                    feedback=reply['feedback']; continue
                body=verify(reply['message'],'buyer',public['buyer'],workflow)
                if body['content']['action']=='reject': outcome='buyer_rejected'; break
                plan=body['content']['plan']; final=plan
                if autonomous and body['content']['action']=='propose':
                    receipt=AutonomousExecutionSink(out/'execution.sqlite',public).commit(plan,reply['message'],workflow,time.time())
                    (out/'execution.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
                    outcome='completed'; break
                needed=book.required(plan,time.time())
                ordered=schedule.order(needed['missing']+needed['denied'],blockers) if selective else OWNERS
                if frontier:
                    from trust_network.demo.repair_envelope import verification_frontiers
                    ordered=[o for stage in verification_frontiers(needed['missing']+needed['denied']) for o in stage]
                for owner in ordered:
                    if owner not in needed['missing']+needed['denied']: continue
                    if frontier and owner=='buyer' and book.required(plan,time.time())['denied']: break
                    response=call(owner,'attest',plan=plan,buyer_decision=reply['message'],binding_mode=binding_mode)
                    queries+=1; book.add(owner,plan,response['commitment'],time.time())
                    denied=response['commitment']['body']['status']=='denied'
                    schedule.observe(owner,denied)
                    if selective and denied:
                        blockers=[owner]
                        break
                needed=book.required(plan,time.time())
                for owner in ('supplier','carrier'):
                    if (rate_update or supply_update) and owner in needed['denied']:
                        refreshed=call(owner,'offer',messages=messages,
                                       feedback=['请提供当前有效资源和报价，供买方重新协商。'])
                        if 'message' in refreshed:
                            messages=[m for m in messages if m['body']['organization']!=owner]+[refreshed['message']]
                if body['content']['action']=='verify':
                    feedback=[{'owner':o,'status':'denied' if o in needed['denied'] else
                               'missing' if o in needed['missing'] else 'approved'} for o in OWNERS]
                    continue
                if not needed['missing'] and not needed['denied']:
                    receipt=ExecutionSink(out/'execution.sqlite',public,binding_mode).commit(plan,book,time.time())
                    (out/'execution.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
                    outcome='completed'; break
                feedback=[{'owner':o,'problem':'current plan not confirmed'} for o in needed['missing']+needed['denied']]
                if repair_mode:
                    from trust_network.demo.repair_envelope import build_repair_envelope, compact_repair_view
                    builder=compact_repair_view if compact_repair else build_repair_envelope
                    feedback=[builder(book,plan,time.time(),messages)]
            else: outcome='negotiation_limit'
        except Exception as exc:
            outcome='runtime_error'
            events.append({'kind':'error','error_type':type(exc).__name__})
        (out/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
    result={'case':case.name,'outcome':outcome,'actor_call_attempts':calls,'logged_api_requests':api,
            'tokens':tokens,'commitment_queries':queries,'final_plan':final,
            'schema_version':2,'binding_mode':binding_mode,'protocol':'autonomous' if autonomous else binding_mode,'audit_root':digest(events),
            'execution_hash':digest(json.loads((out/'execution.json').read_text())) if (out/'execution.json').exists() else None,
            'scope':'real model pilot, separate local organizations; no comparative benefit claim'}
    result['verification_schedule']='adaptive_short_circuit' if selective else 'all_required'
    result['controlled_event']='carrier_rates_plus_100_after_offers' if rate_update else None
    result['supply_update']=supply_update
    result['repair_mode']=repair_mode
    result['frontier']=frontier
    result['compact_repair']=compact_repair
    result['seal']=asdict(Certificate.issue('runtime',1,result,
        Decision('pass',('negotiation_audit_result',),(),'sealed negotiation audit'),runtime_key))
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,default=Path('/home/cjy/cyberagent/.env'))
    parser.add_argument('--cases',type=Path,default=Path('examples/negotiation_v6'))
    parser.add_argument('--compare-bindings',action='store_true'); parser.add_argument('--repeats',type=int,default=2)
    parser.add_argument('--compare-protocols',action='store_true')
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    if not args.execute: print('Plan: 3 real negotiation cases; at most 21 model calls before provider format retries.')
    elif args.compare_bindings or args.compare_protocols:
        from trust_network.demo.run_binding_comparison import execute
        protocols=('autonomous','full','dependency') if args.compare_protocols else ('full','dependency')
        print(json.dumps(execute(args.cases,args.out,args.env_file,args.repeats,protocols),ensure_ascii=False,indent=2))
    else:
        args.out.mkdir(parents=True,exist_ok=False)
        rows=[]
        for case in sorted(args.cases.iterdir()):
            if not case.is_dir(): continue
            result=run_case(case,args.out/case.name,args.env_file); rows.append(result)
            (args.out/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
            print(json.dumps(result,ensure_ascii=False),flush=True)
