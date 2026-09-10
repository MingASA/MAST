"""Evidence-bound handoff routes and durable, acknowledged retraction relay.

Each gateway knows only its own outgoing edges. A notification carries the
original issuer's revocation; an intermediary cannot retract another issuer's
claim. Receipts prove local registration, never truth or deadline compliance.
"""
import copy
from trust_network.demo.claim_channel import issue,read,ClaimGateway
from trust_network.demo.documents import digest
from trust_network.demo.network_reliability import ancestors

PROTOCOL='dependency-notice-v1'


def _bundle(gateway,targets):
    ordered=[];seen=set()
    def visit(cid):
        if cid in seen:return
        if gateway.blockers(cid):raise ValueError('handoff has unavailable dependency')
        for parent in gateway.claims[cid]['body']['parents']:visit(parent)
        seen.add(cid);ordered.append(copy.deepcopy(gateway.claims[cid]))
    for cid in targets:visit(cid)
    return ordered


def validate_handoff(gateway,packet):
    owner,body=read(packet,gateway.public)
    if (body.get('kind')!='dependency_handoff' or body.get('protocol')!=PROTOCOL or
        body.get('workflow')!=gateway.workflow or body.get('recipient') not in gateway.public or
        body['recipient']==owner):
        raise ValueError('invalid handoff scope')
    targets=body.get('claims');bundle=body.get('evidence')
    if (not isinstance(targets,list) or not targets or not all(isinstance(c,str) for c in targets) or
        len(set(targets))!=len(targets) or not isinstance(bundle,list)):
        raise ValueError('invalid handoff dependencies')
    # Structural validation is independent of the receiver's current revocations.
    view=ClaimGateway(gateway.owner,gateway.key,gateway.public,gateway.workflow,gateway.authorities)
    for p in bundle:
        if p.get('body',{}).get('kind')!='claim' or digest(p) in view.claims:
            raise ValueError('duplicate or non-claim handoff evidence')
        if view.receive(p)['body']['action']!='received':raise ValueError('invalid handoff evidence')
    if any(c not in view.claims for c in targets):raise ValueError('handoff target missing')
    required=set().union(*(ancestors(view,c) for c in targets))
    if set(view.claims)!=required:raise ValueError('unrelated handoff evidence')
    return owner,body,required


def prepare_handoff(gateway,recipient,claims):
    """Call as a successful forward effect. Register route before transport.

    This enforces local blockers. Its worker entrypoint additionally runs the
    configured reliability policy, so a model cannot bypass required freshness.
    """
    if recipient not in gateway.public or recipient==gateway.owner:
        raise ValueError('unknown or self handoff recipient')
    if not isinstance(claims,list) or not claims or len(set(claims))!=len(claims):
        raise ValueError('empty or duplicate handoff targets')
    body={'kind':'dependency_handoff','protocol':PROTOCOL,'workflow':gateway.workflow,
        'recipient':recipient,'claims':list(claims),'evidence':_bundle(gateway,claims)}
    packet=issue(gateway.owner,gateway.key,body);hid=digest(packet)
    if hid not in gateway.handoffs:
        gateway.handoffs[hid]=copy.deepcopy(packet)
        for claim in body['evidence']:
            gateway.handoff_index.setdefault(digest(claim),[]).append(hid)
        gateway.record('handoff_prepared',hid,[recipient])
    return copy.deepcopy(packet)


def accept_handoff(gateway,packet):
    sender,body,_=validate_handoff(gateway,packet);hid=digest(packet)
    if body['recipient']!=gateway.owner:raise ValueError('handoff addressed to another organization')
    if hid in gateway.incoming_handoffs:
        return copy.deepcopy(gateway.incoming_handoffs[hid]['receipt'])
    staged=gateway.fork()
    for p in body['evidence']:staged.receive(p)
    blocked={c:staged.blockers(c) for c in body['claims'] if staged.blockers(c)}
    event=staged.record('handoff_received',hid,['blocked' if blocked else 'accepted',sender])
    receipt=issue(gateway.owner,gateway.key,{'kind':'handoff_receipt','protocol':PROTOCOL,
        'workflow':gateway.workflow,'handoff':hid,'sender':sender,
        'status':'blocked' if blocked else 'accepted','blocked':blocked,'event':event})
    staged.incoming_handoffs[hid]={'packet':copy.deepcopy(packet),'receipt':receipt}
    gateway.adopt(staged)
    return copy.deepcopy(receipt)


def acknowledge_handoff(gateway,receipt):
    owner,body=read(receipt,gateway.public);hid=body.get('handoff')
    original=gateway.handoffs.get(hid)
    if (original is None or body.get('kind')!='handoff_receipt' or body.get('protocol')!=PROTOCOL or
        body.get('workflow')!=gateway.workflow or owner!=original['body']['recipient'] or
        body.get('sender')!=gateway.owner or body.get('status') not in ('accepted','blocked')):
        raise ValueError('unbound handoff receipt')
    _receipt_event(gateway,owner,body['event'],'handoff_received',hid)
    if (not isinstance(body.get('blocked'),dict) or bool(body['blocked'])!=(body['status']=='blocked') or
        body['event']['body'].get('reasons')!=[body['status'],gateway.owner]):
        raise ValueError('contradictory handoff receipt')
    existing=gateway.handoff_receipts.get(hid)
    if existing is not None and digest(existing)!=digest(receipt):raise ValueError('conflicting handoff receipt')
    if existing is None:
        gateway.handoff_receipts[hid]=copy.deepcopy(receipt)
        gateway.record('handoff_acknowledged',hid,[digest(receipt)])
    return {'registered':True,'action_authorized':False}


def _receipt_event(gateway,owner,packet,action,target):
    signer,event=read(packet,gateway.public)
    if (signer!=owner or event.get('kind')!='gateway_event' or event.get('workflow')!=gateway.workflow or
        event.get('action')!=action or event.get('target')!=target):
        raise ValueError('invalid receipt event binding')


def enqueue_revocation(gateway,revocation):
    """Local dependency routing: one envelope per affected direct peer.

    Pending handoffs count too: losing their ACK must not suppress a warning.
    The deterministic envelope ID deduplicates repeated retractions and retries.
    """
    target=revocation['body']['target'];groups={}
    for hid in gateway.handoff_index.get(target,[]):
        packet=gateway.handoffs[hid]
        groups.setdefault(packet['body']['recipient'],[]).append(hid)
    for recipient,ids in sorted(groups.items()):
        body={'kind':'dependency_notice','protocol':PROTOCOL,'workflow':gateway.workflow,
            'recipient':recipient,'target':target,'revocation':copy.deepcopy(revocation),
            'handoffs':[copy.deepcopy(gateway.handoffs[hid]) for hid in sorted(ids)]}
        packet=issue(gateway.owner,gateway.key,body);nid=digest(packet)
        if nid not in gateway.notification_outbox:
            gateway.notification_outbox[nid]=packet
            gateway.record('notification_queued',nid,[recipient,target])


def validate_notice(gateway,packet):
    sender,body=read(packet,gateway.public)
    if (body.get('kind')!='dependency_notice' or body.get('protocol')!=PROTOCOL or
        body.get('workflow')!=gateway.workflow or body.get('recipient')!=gateway.owner):
        raise ValueError('invalid notification scope')
    handoffs=body.get('handoffs')
    if not isinstance(handoffs,list) or not handoffs:raise ValueError('notification has no handoff')
    seen=set()
    for handoff in handoffs:
        signer,forward,dependencies=validate_handoff(gateway,handoff);hid=digest(handoff)
        if (signer!=sender or forward['recipient']!=gateway.owner or hid in seen or
            body.get('target') not in dependencies):raise ValueError('notification unrelated to handoff')
        seen.add(hid)
    revocation=body['revocation']
    if revocation.get('body',{}).get('kind')!='revoke' or revocation['body'].get('target')!=body['target']:
        raise ValueError('notification revocation mismatch')
    # Reuse the channel's original-issuer and workflow checks without mutation.
    view=ClaimGateway(gateway.owner,gateway.key,gateway.public,gateway.workflow,gateway.authorities)
    view.receive(revocation)
    return sender,body


def accept_notice(gateway,packet):
    sender,body=validate_notice(gateway,packet);nid=digest(packet)
    if nid in gateway.notification_receipts:
        return copy.deepcopy(gateway.notification_receipts[nid])
    staged=gateway.fork()
    revocation_event=staged.receive(body['revocation'])  # also enqueues affected downstream peers
    event=staged.record('notification_received',nid,[sender,body['target'],digest(revocation_event)])
    receipt=issue(gateway.owner,gateway.key,{'kind':'notification_receipt','protocol':PROTOCOL,
        'workflow':gateway.workflow,'notice':nid,'sender':sender,'target':body['target'],
        'revocation_event':revocation_event,'event':event})
    staged.notification_receipts[nid]=receipt;gateway.adopt(staged)
    return copy.deepcopy(receipt)


def acknowledge_notice(gateway,receipt):
    owner,body=read(receipt,gateway.public);nid=body.get('notice');original=gateway.notification_outbox.get(nid)
    if (original is None or body.get('kind')!='notification_receipt' or body.get('protocol')!=PROTOCOL or
        body.get('workflow')!=gateway.workflow or owner!=original['body']['recipient'] or
        body.get('sender')!=gateway.owner or body.get('target')!=original['body']['target']):
        raise ValueError('unbound notification receipt')
    _receipt_event(gateway,owner,body['event'],'notification_received',nid)
    _receipt_event(gateway,owner,body['revocation_event'],'revocation_received',body['target'])
    if body['event']['body'].get('reasons')!=[gateway.owner,body['target'],digest(body['revocation_event'])]:
        raise ValueError('notification receipt lacks revocation registration binding')
    existing=gateway.notification_acks.get(nid)
    if existing is not None and digest(existing)!=digest(receipt):raise ValueError('conflicting notification receipt')
    if existing is None:
        gateway.notification_acks[nid]=copy.deepcopy(receipt)
        gateway.record('notification_acknowledged',nid,[digest(receipt)])
    return {'acknowledged':True,'action_authorized':False}


def pending_notifications(gateway):
    return [copy.deepcopy(packet) for nid,packet in sorted(gateway.notification_outbox.items())
            if nid not in gateway.notification_acks]


def notification_audit(gateway):
    """Local delivery evidence, deliberately no blame for unacknowledged edges."""
    rows=[]
    for nid,notice in sorted(gateway.notification_outbox.items()):
        receipt=gateway.notification_acks.get(nid)
        rows.append({'notice':nid,'recipient':notice['body']['recipient'],'target':notice['body']['target'],
            'handoffs':[digest(p) for p in notice['body']['handoffs']],
            'status':'signed_receipt' if receipt else 'unacknowledged',
            'receipt':copy.deepcopy(receipt),'protocol_fault':'undetermined'})
    return {'protocol':PROTOCOL,'notifications':rows,'action_authorized':False,
        'limits':['outbox_is_not_delivery','receipt_is_not_agent_attention',
                  'no_deadline_or_complete_log_assumption_no_omission_blame']}


def audit_notification_exchange(notice,receipt,public,authorities):
    """Independent audit from exchanged packets only; no organization database."""
    from trust_network.demo.documents import keypair
    sender,body=read(notice,public)
    verifier=ClaimGateway(body['recipient'],keypair()[0],public,body['workflow'],authorities)
    validate_notice(verifier,notice)
    if receipt is not None:
        verifier.owner=sender
        verifier.notification_outbox[digest(notice)]=notice
        acknowledge_notice(verifier,receipt)
    return {'notice':digest(notice),'target':body['target'],'sender':sender,'recipient':body['recipient'],
        'registration_proven':receipt is not None,'attention_proven':False,
        'omission_fault':'undetermined','legal_blame':'undetermined',
        'handoffs':[digest(p) for p in body['handoffs']]}
