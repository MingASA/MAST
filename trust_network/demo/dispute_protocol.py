"""Signed settlement disputes, routed through existing handoff receipts.

A third-party dispute is never an issuer retraction. Only the issuer can choose
an explicit correction; downstream recovery then reuses closure v3.
"""
import copy
from trust_network.demo.claim_channel import issue,read
from trust_network.demo.documents import digest
from trust_network.demo.fact_evidence import SCOPE,inspect,scope_key
from trust_network.demo.propagation_notice import validate_handoff,_receipt_event

PROTOCOL='dependency-dispute-v1'


def validate_dispute(gateway,proof):
    signer,body=read(proof,gateway.public)
    request=body['request'];requester,q=read(request,gateway.public)
    authority=gateway.fact_authorities.get(SCOPE)
    if (authority is None or signer!=authority or q.get('scope')!=SCOPE or q.get('authority')!=authority or
            q.get('requester')!=requester or q.get('workflow')!=gateway.workflow or
            not q.get('nonce') or not q.get('batch') or not q.get('proposal')):
        raise ValueError('untrusted or unbound dispute')
    _,claim=read(q['claim'],gateway.public);cid=digest(q['claim'])
    if claim.get('kind')!='claim' or claim.get('workflow')!=gateway.workflow or cid!=q.get('claim_id'):
        raise ValueError('dispute claim mismatch')
    scope_key(gateway.workflow,claim['fact'])
    # Negative evidence remains an immutable historical objection to this
    # artifact. Its expiry does not silently rehabilitate the old artifact.
    if inspect(proof,{'request':request},gateway.public,authority,body['issued_at'])!='CONTRADICTED':
        raise ValueError('not a contradictory attestation')
    return cid


def register_dispute(gateway,proof):
    cid=validate_dispute(gateway,proof)
    if cid not in gateway.fact_disputes:
        gateway.fact_disputes[cid]=copy.deepcopy(proof)
        gateway.record('fact_dispute_registered',cid,[digest(proof)])
    enqueue_dispute(gateway,gateway.fact_disputes[cid])
    return cid


def enqueue_dispute(gateway,proof):
    cid=validate_dispute(gateway,proof);groups={}
    for hid in gateway.handoff_index.get(cid,[]):
        handoff=gateway.handoffs[hid]
        groups.setdefault(handoff['body']['recipient'],[]).append(handoff)
    for recipient,handoffs in sorted(groups.items()):
        packet=issue(gateway.owner,gateway.key,{'kind':'dependency_dispute','protocol':PROTOCOL,
            'workflow':gateway.workflow,'recipient':recipient,'target':cid,'proof':copy.deepcopy(proof),
            'handoffs':sorted(handoffs,key=digest)})
        nid=digest(packet)
        if nid not in gateway.notification_outbox:
            gateway.notification_outbox[nid]=packet
            gateway.record('dispute_notification_queued',nid,[recipient,cid])


def validate_notice(gateway,packet):
    sender,body=read(packet,gateway.public)
    if (body.get('kind')!='dependency_dispute' or body.get('protocol')!=PROTOCOL or
            body.get('workflow')!=gateway.workflow or body.get('recipient')!=gateway.owner):
        raise ValueError('wrong dispute destination/scope')
    cid=validate_dispute(gateway,body['proof'])
    if body.get('target')!=cid or not isinstance(body.get('handoffs'),list) or not body['handoffs']:
        raise ValueError('unbound dispute route')
    seen=set()
    for packet in body['handoffs']:
        signer,forward,nodes=validate_handoff(gateway,packet)
        if signer!=sender or forward['recipient']!=gateway.owner or cid not in nodes or digest(packet) in seen:
            raise ValueError('unrelated dispute handoff')
        seen.add(digest(packet))
    return sender,body


def accept_dispute(gateway,packet):
    sender,body=validate_notice(gateway,packet);nid=digest(packet)
    if nid in gateway.notification_receipts:return copy.deepcopy(gateway.notification_receipts[nid])
    staged=gateway.fork();register_dispute(staged,body['proof'])
    event=staged.record('dispute_notification_received',nid,[sender,body['target'],digest(body['proof'])])
    receipt=issue(gateway.owner,gateway.key,{'kind':'dispute_receipt','protocol':PROTOCOL,'workflow':gateway.workflow,
        'notice':nid,'sender':sender,'target':body['target'],'proof':digest(body['proof']),'event':event})
    staged.notification_receipts[nid]=receipt;gateway.adopt(staged)
    return copy.deepcopy(receipt)


def acknowledge_dispute(gateway,receipt):
    owner,body=read(receipt,gateway.public);nid=body.get('notice');original=gateway.notification_outbox.get(nid)
    if (original is None or original['body'].get('kind')!='dependency_dispute' or body.get('kind')!='dispute_receipt' or
            body.get('protocol')!=PROTOCOL or body.get('workflow')!=gateway.workflow or
            owner!=original['body']['recipient'] or body.get('sender')!=gateway.owner or
            body.get('target')!=original['body']['target'] or body.get('proof')!=digest(original['body']['proof'])):
        raise ValueError('unbound dispute receipt')
    _receipt_event(gateway,owner,body['event'],'dispute_notification_received',nid)
    if body['event']['body']['reasons']!=[gateway.owner,body['target'],body['proof']]:raise ValueError('dispute not registered')
    prior=gateway.notification_acks.get(nid)
    if prior is not None and digest(prior)!=digest(receipt):raise ValueError('conflicting dispute ACK')
    if prior is None:
        gateway.notification_acks[nid]=copy.deepcopy(receipt)
        gateway.record('dispute_notification_acknowledged',nid,[digest(receipt)])
    return {'acknowledged':True,'action_authorized':False}


def validate_resolution(gateway,offer):
    """Validate the issuer's exact correction and its independent confirmation.

    Historical signature validity is checked at the signed observation time;
    freshness/fact checks are mandatory again at final business execution.
    """
    from trust_network.demo.reliability_recovery import scope
    resolution=offer.get('fact_resolution')
    if not isinstance(resolution,dict):raise ValueError('missing fact resolution')
    old=validate_dispute(gateway,resolution['dispute'])
    signer,intent=read(resolution['intent'],gateway.public)
    if (old!=offer['old'] or signer!=offer['new']['signature']['issuer'] or
            intent.get('kind')!='dispute_revision_intent' or intent.get('workflow')!=gateway.workflow or
            intent.get('old')!=old or digest(intent.get('candidate'))!=digest(offer['new'])):
        raise ValueError('wrong resolution intent')
    wire=resolution['query'];requester,q=read(wire['request'],gateway.public)
    if (wire.get('kind')!='fact_evidence_query' or requester!=signer or q.get('requester')!=signer or
            q.get('scope')!=SCOPE or q.get('workflow')!=gateway.workflow or
            q.get('authority')!=gateway.fact_authorities.get(SCOPE) or not q.get('nonce') or
            q.get('batch')!=digest(resolution['intent']) or q.get('proposal')!=digest(resolution['intent']) or
            q.get('claim_id')!=digest(offer['new']) or digest(q.get('claim'))!=digest(offer['new'])):
        raise ValueError('wrong resolution query')
    if inspect(resolution['reply'],wire,gateway.public,gateway.fact_authorities[SCOPE],resolution['checked_at'])!='CONFIRMED':
        raise ValueError('new fact not independently confirmed')
    original=resolution['dispute']['body']['request']['body']['claim']['body']
    if scope(original['fact'])!=scope(offer['new']['body']['fact']):raise ValueError('resolution scope changed')


def propose_revision(gateway,proof,fact,query):
    """Explicit issuer API: confirm candidate first, then retract and reissue.

    No amount is inferred from a denial. The issuer must supply the new fact.
    Failure leaves its old claim/revocation state unchanged (apart from audit).
    """
    import secrets,time
    from trust_network.demo.recovery_closure import revision_offer,validate_offer
    old=validate_dispute(gateway,proof);original=gateway.claims.get(old)
    if original is None or original['signature']['issuer']!=gateway.owner:raise ValueError('only original issuer may revise')
    staged=gateway.fork()
    staged.fact_disputes.pop(old,None)  # candidate-only staging; restored before adoption
    revocation=issue(gateway.owner,gateway.key,{'kind':'revoke','workflow':gateway.workflow,'target':old,'original':original})
    staged.receive(revocation)
    proposed=revision_offer(staged,old,fact)  # structural/scope validation before query
    intent=issue(gateway.owner,gateway.key,{'kind':'dispute_revision_intent','workflow':gateway.workflow,
        'old':old,'candidate':proposed['body']['new']})
    request=issue(gateway.owner,gateway.key,{'scope':SCOPE,'workflow':gateway.workflow,'requester':gateway.owner,
        'authority':gateway.fact_authorities[SCOPE],'batch':digest(intent),'proposal':digest(intent),
        'nonce':secrets.token_hex(24),'claim_id':digest(proposed['body']['new']),'claim':proposed['body']['new']})
    wire={'kind':'fact_evidence_query','request':request}
    reply=query(gateway.fact_authorities[SCOPE],wire);checked_at=time.time()
    if inspect(reply,wire,gateway.public,gateway.fact_authorities[SCOPE],checked_at)!='CONFIRMED':
        raise ValueError('revision lacks independent confirmation')
    body={**proposed['body'],'fact_resolution':{'dispute':proof,'intent':intent,'query':wire,'reply':reply,'checked_at':checked_at}}
    offer=issue(gateway.owner,gateway.key,body);validate_offer(staged,offer)
    register_dispute(staged,proof)  # historical dispute retained; no resurrection
    staged.record('dispute_revision_confirmed',digest(offer),[old,digest(body['new']),digest(reply)])
    gateway.adopt(staged)
    return offer


def audit_exchange(packet,receipt,public,authorities,fact_authorities):
    from trust_network.demo.claim_channel import ClaimGateway
    from trust_network.demo.documents import keypair
    sender,body=read(packet,public)
    verifier=ClaimGateway(body['recipient'],keypair()[0],public,body['workflow'],authorities,fact_authorities)
    validate_notice(verifier,packet)
    if receipt is not None:
        verifier.owner=sender;verifier.notification_outbox[digest(packet)]=packet
        acknowledge_dispute(verifier,receipt)
    return {'target':body['target'],'sender':sender,'recipient':body['recipient'],
        'proof':digest(body['proof']),'registration_proven':receipt is not None,
        'attention_proven':False,'omission_fault':'undetermined','legal_blame':'undetermined'}
