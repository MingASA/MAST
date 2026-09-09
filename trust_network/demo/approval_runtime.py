"""Commit gate for autonomous business actors; no ground-truth reads here."""
from dataclasses import asdict
from pathlib import Path
import copy
import json
import subprocess
import sys
import time
import urllib.request
import uuid
from trust_network.demo.documents import Decision,Certificate,digest
from trust_network.demo.authority import inspect,ISSUER
from trust_network.demo.approval_scenario import ACTORS
from trust_network.demo.reliability import VisibleContext,RiskConfig,decide


class Audit:
    def __init__(self,path):
        self.path=path; self.previous='0'*64; self.events=[]
        if path.exists(): raise FileExistsError(path)

    def add(self,kind,**data):
        event={'index':len(self.events),'kind':kind,'previous_hash':self.previous,**data}
        event['hash']=digest(event)
        with self.path.open('a') as stream: stream.write(json.dumps(event,ensure_ascii=False)+'\n')
        self.previous=event['hash']; self.events.append(event)


class ModelActor:
    def __init__(self,case,env_file,endpoints=None):
        self.case=case; self.env_file=env_file; self.endpoints=endpoints

    def __call__(self,org,payload):
        if self.endpoints is not None:
            request=urllib.request.Request(self.endpoints[org],data=json.dumps(payload,ensure_ascii=False).encode(),
                                           headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=120) as response: return json.load(response)
        result=subprocess.run([sys.executable,'-m','trust_network.demo.approval_worker',
            '--dossier',str(self.case/'organizations'/org/'private.md'),'--env-file',str(self.env_file)],
            input=json.dumps(payload,ensure_ascii=False),capture_output=True,text=True,timeout=120)
        if result.returncode: raise RuntimeError('model worker failed; raw response withheld')
        return json.loads(result.stdout)


def run_workflow(case: Path,out: Path,policy: str,actor,authority,keys,*,
                 config=RiskConfig(),temperature=.2,request_id='local-run',clock=time.time):
    """Actor proposals never reach a peer or the execution sink before the gate.

    Injected actor/authority adapters are shared by all policies. Tests use named
    scripted actors; actual experiments use subprocess MiniMax actors.
    """
    out.mkdir(parents=True,exist_ok=False)
    bundle=json.loads((case/'public/bundle.json').read_text())
    intake=json.loads((case/'intake.json').read_text())['intake_class']
    version=bundle['document_version']; audit=Audit(out/'audit.jsonl')
    initial_hash=digest(bundle)
    audit.add('start',schema_version=2,policy=policy,bundle=bundle,intake_class=intake,
              config=asdict(config),request_id=request_id,temperature=temperature)
    cache=None; query_id=None; messages=[]; certificates=[]
    last_evidence_status=None
    workflow_nonce=uuid.uuid4().hex
    cost=0.; queries=0; requests=0; calls=0; usage={'total_tokens':0,'attempts':0}
    outcome='completed'; failed=None; interventions=0; committed=False

    def evidence_status():
        nonlocal cache
        if cache is None:
            return 'missing' if last_evidence_status is None else 'stale_'+last_evidence_status
        try: return inspect(cache,bundle,version,keys[ISSUER][1],query_id,clock())
        except ValueError:
            audit.add('evidence_invalidated',certificate_hash=digest(asdict(cache)))
            cache=None
            return 'missing' if last_evidence_status is None else 'stale_'+last_evidence_status

    def query(org,source):
        nonlocal cache,query_id,cost,queries,requests,last_evidence_status
        requests+=1
        if evidence_status() in ('approved','denied','unknown'):
            audit.add('evidence_cache_hit',organization=org,source=source)
            return True
        if cost+config.verification_cost>config.budget+1e-10:
            audit.add('evidence_budget_exhausted',organization=org,source=source)
            return False
        queries+=1; cost+=config.verification_cost
        query_id=f'{request_id}:{workflow_nonce}:{queries}'
        request={'documents':copy.deepcopy(bundle),'version':version,'request_id':query_id,'now':clock()}
        audit.add('evidence_request',organization=org,source=source,request=request,
                  charged_cost=config.verification_cost,budget_remaining=config.budget-cost)
        cache=authority.request(request)
        status=inspect(cache,bundle,version,keys[ISSUER][1],query_id,clock())
        last_evidence_status=status
        audit.add('evidence_received',organization=org,status=status,certificate=asdict(cache))
        return True

    try:
        for org in ACTORS:
            decision=None
            for attempt in range(2):
                status=evidence_status()
                payload={'organization':org,'documents':copy.deepcopy(bundle),
                    'task':'完成本组织的业务判断并给出下一步操作。',
                    'risk_context':{'intake_class':intake,
                        'error_prior':config.change_prior if intake=='change_order' else config.routine_prior,
                        'potential_downstream_loss':config.change_loss if intake=='change_order' else config.routine_loss,
                        'escalation_cost':config.escalation_cost,'budget_remaining':config.budget-cost},
                    'public_messages':copy.deepcopy(messages),'certificates':copy.deepcopy(certificates),
                    'authority_evidence':asdict(cache) if cache is not None else None,
                    'evidence_verification':{'status':status,
                        'verified_by':'runtime','fresh':status in ('approved','denied','unknown'),
                        'meaning':'Signature, scope, document binding and validity checked by runtime; cached evidence is reusable.'},
                    'verification_service':{'authority':ISSUER,'scope':'formal_model_authorization',
                                            'price':config.verification_cost},
                    '_sampling_temperature':temperature}
                # Never expose experiment policy labels, case filenames, priors
                # derived from labels, evaluator truth or the buyer registry.
                calls+=1
                audit.add('actor_request',organization=org,visible_input=payload)
                reply=actor(org,payload)
                for k in usage: usage[k]+=reply['usage'].get(k,1 if k=='attempts' else 0)
                decision=Decision.parse(reply['decision'])
                audit.add('proposal',organization=org,decision=asdict(decision),
                          usage=reply['usage'],visible_input_hash=digest(payload))
                if decision.action!='request_evidence': break
                if decision.requested_from!=ISSUER:
                    outcome='escalated_invalid_request'; break
                if attempt==1:
                    outcome='escalated_repeated_request'; break
                if not query(org,'agent'):
                    outcome='escalated_budget'; break
            if outcome!='completed': break
            if decision.action!='pass':
                outcome='rejected' if decision.action=='reject' else 'escalated_agent'
                audit.add('stop',organization=org,reason=outcome)
                break
            context=VisibleContext(intake,evidence_status(),config.budget-cost)
            gate=decide(policy,context,config)
            audit.add('gate',organization=org,proposal='pass',context=asdict(context),gate=asdict(gate))
            if gate.action!='allow': interventions+=1
            if gate.action=='request_evidence':
                if not query(org,'policy'):
                    outcome='escalated_budget'; break
                context=VisibleContext(intake,evidence_status(),config.budget-cost)
                gate=decide(policy,context,config)
                audit.add('gate_after_evidence',organization=org,proposal='pass',context=asdict(context),gate=asdict(gate))
            if gate.action!='allow':
                outcome='escalated_policy'
                audit.add('stop',organization=org,reason=gate.reason)
                break
            # Only accepted proposals produce downstream messages/certificates.
            cert=Certificate.issue(org,version,bundle,decision,keys[org][0])
            certificates.append(asdict(cert)); messages.append({'from':org,'message':decision.public_message})
            audit.add('forward',organization=org,certificate=asdict(cert))
        if outcome=='completed':
            committed=True
            audit.add('execution_commit',transaction=bundle['transaction'],bundle_hash=digest(bundle))
    except Exception as exc:
        outcome='runtime_error'; failed=type(exc).__name__
        audit.add('runtime_error',error_type=failed,message='no synthetic decision substituted')
    result={'policy':policy,'status':'error' if failed else 'finished','outcome':outcome,
        'committed':committed,'verification_count':queries,'verification_cost':cost,
        'evidence_requests':requests,'policy_interventions':interventions,
        'actor_call_attempts':calls,'logged_api_requests':usage['attempts'],'tokens':usage['total_tokens'],
        'potential_downstream_loss':config.change_loss if intake=='change_order' else config.routine_loss,
        'error_type':failed,'audit_root':audit.previous,'initial_bundle_hash':initial_hash}
    # Seal the audit with the existing signature primitive; independent readers
    # can detect editing, reordering and truncation against this signed root.
    seal=Certificate.issue('runtime',1,{'audit_root':audit.previous},
        Decision('pass',('audit_integrity',),(),'audit sealed'),keys['runtime'][0])
    result['audit_seal']=asdict(seal)
    result['result_seal']=asdict(Certificate.issue('runtime',1,result,
        Decision('pass',('result_integrity',),(),'result sealed'),keys['runtime'][0]))
    (out/'runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
