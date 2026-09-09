"""Receiver-side workflow; organization private keys are not runtime inputs."""
from dataclasses import asdict
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import urllib.request
from trust_network.demo.approval_runtime import Audit
from trust_network.demo.approval_scenario import ACTORS
from trust_network.demo.authority import inspect
from trust_network.demo.contract_protocol import check_contract, receive_proposal, receive_packet
from trust_network.demo.documents import Certificate, Decision, digest

POLICIES = ('autonomous', 'authority_only', 'evidence_contract')


class ProcessGateway:
    def __init__(self, directory, env_file=None, fixture=False):
        self.directory, self.env_file, self.fixture = directory, env_file, fixture

    def call(self, operation, request, **extra):
        command = [sys.executable, '-m', 'trust_network.demo.contract_worker',
                   '--organization-dir', str(self.directory)]
        if self.fixture: command.append('--fixture')
        if self.env_file is not None: command += ['--env-file',str(self.env_file)]
        result = subprocess.run(command, input=json.dumps(dict(operation=operation,request=request,**extra)),
                                text=True,capture_output=True,timeout=120)
        if result.returncode: raise RuntimeError('organization gateway failed; no synthetic fallback')
        return json.loads(result.stdout)


class RemoteGateway:
    """Network adapter contains no organization directory or signing key."""
    def __init__(self, endpoint): self.endpoint=endpoint

    def call(self, operation, request, **extra):
        wire=dict(operation=operation,request=request,**extra)
        req=urllib.request.Request(self.endpoint,data=json.dumps(wire).encode(),
                                   headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=120) as response: return json.load(response)


def run(bundle, policy, gateways, public_keys, authority, runtime_key, out,
        *, temperature=.2, verification_price=3., budget=9.):
    if policy not in POLICIES: raise ValueError('unknown protocol')
    out.mkdir(parents=True, exist_ok=False)
    audit = Audit(out/'audit.jsonl'); workflow_id = uuid.uuid4().hex
    audit.add('start',schema_version=2,protocol='evidence_contract_v5',policy=policy,bundle=bundle,
              workflow_id=workflow_id,verification_price=verification_price,budget=budget)
    evidence = None; history = []; cost=0.; queries=0; calls=0; tokens=0; api=0
    repairs=0; committed=False; outcome='completed'; error=None

    def status():
        if evidence is None: return 'missing'
        return inspect(Certificate(**evidence['certificate']),bundle,bundle['document_version'],
                       public_keys['buyer_authority'],evidence['request_id'],time.time())

    def query(org):
        nonlocal evidence,cost,queries
        if evidence is not None:
            status()  # Expired evidence fails closed; cannot erase prior denial.
            audit.add('cache_hit',organization=org)
            return
        if cost+verification_price > budget: raise ValueError('evidence budget exhausted')
        request={'documents':copy.deepcopy(bundle),'version':bundle['document_version'],
                 'request_id':uuid.uuid4().hex,'now':time.time()}
        queries+=1; cost+=verification_price
        audit.add('evidence_request',organization=org,request=request,charged_cost=verification_price)
        certificate=authority.request(request)
        evidence={'certificate':asdict(certificate),'request_id':request['request_id']}
        inspected_at=time.time()
        verified=inspect(certificate,bundle,bundle['document_version'],public_keys['buyer_authority'],
                         request['request_id'],inspected_at)
        audit.add('evidence_received',evidence=evidence,status=verified,verified_at=inspected_at)

    try:
        for org in ACTORS:
            feedback=[]; finished=False
            for attempt in range(3):
                current=status()
                request={'organization':org,'request_id':uuid.uuid4().hex,'workflow_id':workflow_id,
                         'documents':copy.deepcopy(bundle),'messages':copy.deepcopy(history),
                         'authority_evidence':copy.deepcopy(evidence),
                         'evidence_verification':{'status':current,'verified_at':time.time()},
                         'feedback':feedback,'temperature':temperature}
                calls+=1
                audit.add('actor_request',organization=org,request=request)
                reply=gateways[org].call('propose',request)
                tokens+=reply['usage'].get('total_tokens',0); api+=reply['usage'].get('attempts',0)
                envelope=reply['envelope']
                proposal=receive_proposal(org,public_keys[org],request,envelope)
                audit.add('proposal',organization=org,envelope=envelope,usage=reply['usage'])
                if proposal.get('action') in ('reject','escalate'):
                    outcome='stopped_by_agent'; break
                if proposal.get('action')=='request_evidence':
                    query(org)
                    feedback=['Authority query completed; use the verified result or explain why you must stop.']
                    continue
                if proposal.get('action')!='pass':
                    outcome='invalid_action'; break
                current=status()
                checked=None
                if policy=='evidence_contract':
                    checked=check_contract(org,bundle,proposal,current,
                                           digest(evidence['certificate']) if evidence else None)
                    audit.add('contract',organization=org,decision=asdict(checked),status=current,
                              verified_at=time.time())
                    if checked.action=='repair':
                        repairs+=1; feedback=list(checked.reasons)
                        continue
                    if checked.action=='stop': outcome='blocked_contract'; break
                if policy=='authority_only' and current!='approved' or (
                        checked is not None and checked.action=='request_evidence'):
                    query(org); current=status()
                    if current!='approved': outcome='blocked_authority'; break
                # Sender gateway independently checks before signing acceptance.
                finalized=gateways[org].call('finalize',request,envelope=envelope,evidence=evidence)['envelope']
                packet=receive_proposal(org,public_keys[org],request,finalized)
                if packet['policy']!=policy or packet['source_proposal_hash']!=digest(envelope):
                    raise ValueError('finalized packet disagrees with proposal or protocol')
                if policy=='evidence_contract':
                    checked=check_contract(org,bundle,proposal,status(),digest(evidence['certificate']))
                    if checked.action!='allow' or packet['accepted_message']!=checked.accepted_message:
                        raise ValueError('receiver rejected gateway packet')
                receive_packet(org,public_keys,bundle,workflow_id,policy,finalized,time.time())
                # Record time and both evidence and sender signatures for replay.
                audit.add('forward',organization=org,envelope=finalized,request=request,verified_at=time.time())
                history.append(finalized); finished=True
                break
            if not finished:
                if outcome=='completed': outcome='interaction_limit'
                break
        if outcome=='completed':
            committed=True
            audit.add('execution_commit',transaction=bundle['transaction'],document_hash=digest(bundle))
    except Exception as exc:
        outcome='runtime_error'; error=type(exc).__name__
        audit.add('runtime_error',error_type=error)
    result={'policy':policy,'outcome':outcome,'status':'error' if error else 'finished',
            'committed':committed,'verification_cost':cost,'verification_count':queries,
            'actor_call_attempts':calls,'logged_api_requests':api,'tokens':tokens,'repairs':repairs,
            'audit_root':audit.previous,'error_type':error}
    result['seal']=asdict(Certificate.issue('runtime',1,result,
        Decision('pass',('audit_and_result',),(),'sealed result'),runtime_key))
    (out/'runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
