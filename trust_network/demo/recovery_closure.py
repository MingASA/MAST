"""Recovery v3: issuer revisions may start at a root or an intermediate claim.

A retraction is not a correction. An issuer must explicitly propose a valid
replacement, and each descendant must be rebuilt by its own issuer. This module
uses only signed public evidence and the gateway's local state.
"""
import copy
from trust_network.demo.claim_channel import issue, read
from trust_network.demo.documents import digest
from trust_network.demo.claim_derivation import valid_derivation
from trust_network.demo.network_reliability import ancestors
from trust_network.demo.reliability_recovery import scope
from trust_network.demo.reliability_audit import audit_with_authorities

PROTOCOL='recovery-frontier-v3'


def validate_offer(gateway, packet):
    signer,offer=read(packet,gateway.public)
    if offer.get('kind')!='claim_revision_offer' or offer.get('workflow')!=gateway.workflow:
        raise ValueError('invalid revision offer')
    old_id=offer['old']; original=gateway.claims.get(old_id)
    if original is None: raise ValueError('missing revision predecessor')
    owner,old=read(original,gateway.public); new_owner,new=read(offer['new'],gateway.public)
    if (owner!=signer or new_owner!=owner or old.get('kind')!='claim' or
        new.get('kind')!='claim' or new.get('workflow')!=gateway.workflow or
        new.get('supersedes')!=old_id or digest(offer['new'])==old_id or
        new.get('parents')!=old['parents'] or new.get('rule','relay')!=old.get('rule','relay') or
        scope(old['fact'])!=scope(new['fact'])):
        raise ValueError('revision issuer/dependency/business scope mismatch')
    revoker,revocation=read(offer['revocation'],gateway.public)
    if (revoker!=owner or revocation.get('kind')!='revoke' or
        revocation.get('workflow')!=gateway.workflow or revocation.get('target')!=old_id or
        digest(revocation.get('original'))!=old_id):
        raise ValueError('revision lacks original issuer retraction')
    parents=new['parents']
    if parents:
        if any(p not in gateway.claims for p in parents) or not valid_derivation(
            new.get('rule','relay'),new['fact'],[gateway.claims[p]['body']['fact'] for p in parents]):
            raise ValueError('invalid revised derivation')
    elif gateway.authorities.get(new['fact']['predicate'])!=owner:
        raise ValueError('revision source is not authoritative')
    return old_id,offer['new']


def revision_offer(gateway,old_id,fact):
    """Local issuer proposes a correction, never a receiver-forced reissue."""
    old=gateway.claims[old_id]
    if old['signature']['issuer']!=gateway.owner or old_id not in gateway.revoked:
        raise ValueError('revision requires own directly retracted claim')
    if any(gateway.blockers(p) for p in old['body']['parents']):
        raise ValueError('revise invalid parents first')
    original_body={k:copy.deepcopy(v) for k,v in old['body'].items() if k!='recovery_binding'}
    packet=issue(gateway.owner,gateway.key,{**original_body,
        'fact':copy.deepcopy(fact),'supersedes':old_id})
    offer=issue(gateway.owner,gateway.key,{'kind':'claim_revision_offer','workflow':gateway.workflow,
        'old':old_id,'new':packet,'revocation':gateway.revoked[old_id]})
    validate_offer(gateway,offer)
    if gateway.receive(packet)['body']['action']!='received': raise ValueError('revision not usable locally')
    gateway.record('claim_revision_offered',digest(offer),[old_id,digest(packet)])
    return offer


def tasks_for(gateway,batch, replacements):
    proposals={p['id']:p for p in batch['plan']['body']['proposals']}
    tasks=[]
    for outcome in batch['outputs']:
        if outcome['action'] not in ('REQUEST_EVIDENCE','ESCALATE','BLOCKED'): continue
        proposal=proposals[outcome['proposal']]
        nodes=set().union(*(ancestors(gateway,c) for c in proposal['claims']))
        selected={old:new for old,new in replacements.items() if old in nodes}
        if not selected: continue
        rebuild=[]
        for cid in sorted(nodes-set(selected)):
            packet=gateway.claims.get(cid)
            if packet and packet['body']['parents'] and ancestors(gateway,cid).intersection(selected):
                rebuild.append({'old':cid,'issuer':packet['signature']['issuer'],
                    'parents':packet['body']['parents'],'rule':packet['body'].get('rule','relay')})
        tasks.append({'proposal':proposal,'replacement_sources':selected,
                      'rebuild_required':rebuild,'requires_new_model_decision':True})
    return tasks


def validate_envelope(gateway,packet,receiver):
    signer,body=read(packet,gateway.public)
    if (signer!=receiver or body.get('protocol')!=PROTOCOL or body.get('kind')!='recovery_envelope' or
        body.get('workflow')!=gateway.workflow or body.get('action_authorized') is not False or
        body.get('fresh_status_check_still_required') is not True):
        raise ValueError('invalid closure recovery envelope')
    batch_packet=body['batch_packet']; batch_owner,batch=read(batch_packet,gateway.public)
    if batch_owner!=receiver or batch.get('workflow')!=gateway.workflow or digest(batch_packet)!=body['batch']:
        raise ValueError('recovery batch binding mismatch')
    assessment=audit_with_authorities(batch_packet,gateway.public,gateway.authorities)
    if any(f['classification']!='no_proven_evidence_duty_violation' for f in assessment['findings']):
        raise ValueError('violating batch cannot authorize recovery')
    mapping={}; packets=[]
    for offer in body['offers']:
        old,new=validate_offer(gateway,offer)
        if old in mapping: raise ValueError('duplicate revision')
        mapping[old]=digest(new); packets.append(new)
    # v3 starts at an antichain: fix invalid parents first, then descendants.
    if any((ancestors(gateway,c)-{c}).intersection(mapping) for c in mapping):
        raise ValueError('revision seeds overlap')
    expected=tasks_for(gateway,batch,mapping)
    used={old for task in expected for old in task['replacement_sources']}
    if not mapping or used!=set(mapping) or expected!=body['tasks'] or packets!=body['new_source_packets']:
        raise ValueError('recovery task/offer binding mismatch')
    return body


def prepare_closure_recovery(gateway,batch_packet,offers):
    _,batch=read(batch_packet,gateway.public)
    mapping={}
    for offer in offers:
        old,new=validate_offer(gateway,offer)
        if old in mapping: raise ValueError('duplicate revision')
        mapping[old]=digest(new)
    body={'kind':'recovery_envelope','protocol':PROTOCOL,'workflow':gateway.workflow,
        'batch':digest(batch_packet),'batch_packet':copy.deepcopy(batch_packet),'offers':copy.deepcopy(offers),
        'new_source_packets':[p['body']['new'] for p in offers],
        'tasks':tasks_for(gateway,batch,mapping),'action_authorized':False,
        'fresh_status_check_still_required':True}
    packet=issue(gateway.owner,gateway.key,body)
    validate_envelope(gateway,packet,gateway.owner)
    staged=gateway.fork()
    for offer in offers:
        staged.receive(offer['body']['revocation'])
        if staged.receive(offer['body']['new'])['body']['action']!='received':
            raise ValueError('replacement parents not locally valid')
    gateway.adopt(staged)
    gateway.record('closure_recovery_prepared',digest(packet),[digest(batch_packet)])
    return packet
