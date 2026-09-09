"""Independent reconstruction of signatures, evidence, actions and metrics."""
from dataclasses import asdict
import json
from trust_network.demo.approval_scenario import ACTORS
from trust_network.demo.authority import inspect
from trust_network.demo.contract_protocol import check_contract, receive_proposal, receive_packet, receive_history
from trust_network.demo.documents import Certificate, digest


def validate(out, public_keys):
    result=json.loads((out/'runtime.json').read_text())
    unsigned=dict(result); seal=Certificate(**unsigned.pop('seal'))
    if seal.issuer!='runtime' or not seal.verify(public_keys['runtime'],unsigned,1):
        raise ValueError('invalid result seal')
    events=[json.loads(line) for line in (out/'audit.jsonl').read_text().splitlines()]
    previous='0'*64
    for index,original in enumerate(events):
        event=dict(original); stored=event.pop('hash')
        if event['index']!=index or event['previous_hash']!=previous or digest(event)!=stored:
            raise ValueError('audit chain changed')
        previous=stored
    if previous!=result['audit_root']: raise ValueError('audit root mismatch')
    start=events[0]; bundle=start['bundle']; policy=start['policy']; evidence=None
    request=None; proposal=None; envelope=None; pending_evidence=None
    forwarded=[]; costs=0.; queries=0; calls=0; api=0; tokens=0; repairs=0; commits=0
    if result['policy']!=policy: raise ValueError('result policy mismatch')
    for event in events[1:]:
        kind=event['kind']
        if kind=='actor_request':
            request=event['request']; proposal=None; envelope=None; calls+=1
            if len(forwarded)>=len(ACTORS) or event['organization']!=ACTORS[len(forwarded)]:
                raise ValueError('incorrect actor order')
            if request['documents']!=bundle or request['workflow_id']!=start['workflow_id']:
                raise ValueError('request binding mismatch')
            if start.get('schema_version',1)>=2:
                receive_history(event['organization'],public_keys,bundle,start['workflow_id'],policy,
                                request['messages'],request['evidence_verification']['verified_at'])
        elif kind=='proposal':
            envelope=event['envelope']
            proposal=receive_proposal(event['organization'],public_keys[event['organization']],request,envelope)
            api+=event['usage'].get('attempts',0); tokens+=event['usage'].get('total_tokens',0)
        elif kind=='evidence_request':
            pending_evidence=event['request']; queries+=1
            if event['charged_cost']!=start['verification_price']: raise ValueError('wrong evidence fee')
            costs+=event['charged_cost']
            if costs>start['budget']: raise ValueError('exceeded evidence budget')
        elif kind=='evidence_received':
            evidence=event['evidence']
            if pending_evidence is None or evidence['request_id']!=pending_evidence['request_id']:
                raise ValueError('unsolicited evidence response')
            verified=inspect(Certificate(**evidence['certificate']),bundle,bundle['document_version'],
                public_keys['buyer_authority'],evidence['request_id'],event['verified_at'])
            if verified!=event['status']: raise ValueError('incorrect evidence status')
            pending_evidence=None
        elif kind=='contract':
            verified='missing' if evidence is None else inspect(Certificate(**evidence['certificate']),
                bundle,bundle['document_version'],public_keys['buyer_authority'],
                evidence['request_id'],event['verified_at'])
            decision=check_contract(event['organization'],bundle,proposal,verified,
                                    digest(evidence['certificate']) if evidence else None)
            if asdict(decision)!=dict(event['decision'],reasons=tuple(event['decision']['reasons'])):
                raise ValueError('contract decision does not follow evidence')
            repairs+=decision.action=='repair'
        elif kind=='forward':
            org=event['organization']
            if org!=ACTORS[len(forwarded)] or proposal is None or proposal.get('action')!='pass':
                raise ValueError('forward without correct proposal')
            packet=receive_proposal(org,public_keys[org],request,event['envelope'])
            if packet['source_proposal_hash']!=digest(envelope): raise ValueError('proposal link mismatch')
            receive_packet(org,public_keys,bundle,start['workflow_id'],policy,event['envelope'],event['verified_at'])
            if packet['evidence']!=evidence: raise ValueError('unrecorded evidence in packet')
            if policy=='evidence_contract':
                decision=check_contract(org,bundle,proposal,'approved',digest(evidence['certificate']))
                if decision.action!='allow' or decision.accepted_message!=packet['accepted_message']:
                    raise ValueError('forwarded message not derived from signed proposal')
            forwarded.append(org)
        elif kind=='execution_commit':
            if forwarded!=list(ACTORS) or event['document_hash']!=digest(bundle):
                raise ValueError('commit without all required organization receipts')
            commits+=1
    expected={'actor_call_attempts':calls,'verification_count':queries,'verification_cost':costs,
              'logged_api_requests':api,'tokens':tokens,'repairs':repairs,'committed':commits==1}
    if commits>1 or any(result[k]!=v for k,v in expected.items()):
        raise ValueError('result counters disagree with audited events')
    return {'events':len(events),'forwarded':forwarded,'reconstructed_counters':expected}
