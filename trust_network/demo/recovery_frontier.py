"""Dependency-frontier recovery v2, leaving recovery-evidence-v1 unchanged.

A receiver's original signed task fixes the affected DAG. A node is ready only
when every affected parent has a verified replacement. Completed derived claims
are evidence, not authority offers: their original issuers and transformations
are verified transitively. No fact is generated here and no action is authorized.
"""
import copy
from trust_network.demo.claim_channel import read,issue
from trust_network.demo.documents import digest
from trust_network.demo.claim_derivation import valid_derivation
from trust_network.demo.reliability_recovery import scope


def frontier(gateway,envelope_packet,task_id,completed,receiver):
    signer,envelope=read(envelope_packet,gateway.public)
    if (signer!=receiver or envelope.get('kind')!='recovery_envelope' or
        envelope.get('workflow')!=gateway.workflow or envelope.get('action_authorized') is not False or
        envelope.get('fresh_status_check_still_required') is not True):
        raise ValueError('wrong recovery authority/scope')
    closure=envelope.get('protocol')=='recovery-frontier-v3'
    if closure:
        from trust_network.demo.recovery_closure import validate_envelope
        validate_envelope(gateway,envelope_packet,receiver)
    tasks=[t for t in envelope['tasks'] if t['proposal']['id']==task_id]
    if len(tasks)!=1 or tasks[0].get('requires_new_model_decision') is not True:
        raise ValueError('task not uniquely authorized')
    task=tasks[0]; graph={r['old']:r for r in task['rebuild_required']}
    if len(graph)!=len(task['rebuild_required']) or (not graph and not closure):
        raise ValueError('invalid rebuild graph')
    for old_id,node in graph.items():
        original=gateway.claims.get(old_id)
        if original is None: raise ValueError('old DAG evidence missing')
        owner,old=read(original,gateway.public)
        if (old.get('kind')!='claim' or old.get('workflow')!=gateway.workflow or
            owner!=node['issuer'] or old['parents']!=node['parents'] or
            old.get('rule','relay')!=node['rule'] or not old['parents']):
            raise ValueError('old DAG scope mismatch')
    mapping={}; available=dict(gateway.claims)
    required=task['replacement_sources']
    for offer_packet in envelope['offers']:
        authority,offer=read(offer_packet,gateway.public)
        old_id=offer['old']
        if old_id not in required: continue
        if old_id in mapping: raise ValueError('duplicate source replacement')
        if closure:
            from trust_network.demo.recovery_closure import validate_offer
            _,new_packet=validate_offer(gateway,offer_packet)
            new_id=digest(new_packet)
            if required[old_id]!=new_id: raise ValueError('revision mapping mismatch')
            mapping[old_id]=new_id; available[new_id]=new_packet
            continue
        original=gateway.claims.get(old_id)
        if original is None: raise ValueError('old root unavailable')
        old_owner,old=read(original,gateway.public)
        new_packet=offer['new']; new_owner,new=read(new_packet,gateway.public)
        new_id=digest(new_packet)
        if (offer.get('kind')!='replacement_offer' or offer.get('workflow')!=gateway.workflow or
            authority!=old_owner or new_owner!=authority or old['parents'] or new['parents'] or
            new.get('kind')!='claim' or new.get('workflow')!=gateway.workflow or
            gateway.authorities.get(new['fact']['predicate'])!=authority or
            scope(old['fact'])!=scope(new['fact']) or new_id==old_id or required[old_id]!=new_id or
            sum(digest(p)==new_id for p in envelope['new_source_packets'])!=1):
            raise ValueError('invalid source replacement')
        mapping[old_id]=new_id; available[new_id]=new_packet
    if mapping!=required: raise ValueError('source replacements incomplete')
    if not isinstance(completed,dict) or not set(completed)<=set(graph):
        raise ValueError('completion from another task')
    pending=dict(completed)
    while pending:
        ready=[old for old in pending if all(p not in graph or p in mapping for p in graph[old]['parents'])]
        if not ready: raise ValueError('completion bypasses an unfinished parent')
        for old_id in sorted(ready):
            node=graph[old_id]; packet=pending.pop(old_id); owner,new=read(packet,gateway.public)
            parents=[mapping.get(p,p) for p in node['parents']]
            if (owner!=node['issuer'] or new.get('kind')!='claim' or new.get('workflow')!=gateway.workflow or
                new['parents']!=parents or new.get('rule','relay')!=node['rule'] or
                any(p not in available for p in parents) or
                not valid_derivation(node['rule'],new['fact'],[available[p]['body']['fact'] for p in parents])):
                raise ValueError('invalid completed derivation')
            if closure and (new.get('supersedes')!=old_id or
                new.get('recovery_binding')!={'envelope':digest(envelope_packet),'task_id':task_id}):
                raise ValueError('completed revision not bound to this task')
            if digest(packet)==old_id: raise ValueError('rebuild reused old identity')
            mapping[old_id]=digest(packet); available[digest(packet)]=packet
    invalidated={};suspended={};usable_mapping=dict(mapping)
    if closure:
        # Signatures prove how a completion was built, not that it remains
        # usable after a subsequent local retraction. Preserve unaffected work.
        def negatives(cid,seen=None):
            seen=set() if seen is None else seen
            if cid in seen: raise ValueError('cyclic replacement evidence')
            if cid in gateway.revoked:return [cid]
            packet=available.get(cid)
            if packet is None:return ['missing:'+cid]
            found=[]
            for parent in packet['body']['parents']:
                found.extend(negatives(parent,seen|{cid}))
            return sorted(set(found))
        for old_id,new_id in mapping.items():
            reasons=negatives(new_id)
            if reasons:invalidated[old_id]=reasons;usable_mapping.pop(old_id,None)
        for old_id,node in graph.items():
            reasons=list(invalidated.get(old_id,[]))
            for parent in node['parents']:
                reasons.extend(negatives(mapping.get(parent,parent)))
            if reasons:suspended[old_id]=sorted(set(reasons))
    ready=[]
    for old_id,node in graph.items():
        if old_id not in mapping and old_id not in suspended and all(p not in graph or p in usable_mapping for p in node['parents']):
            ready.append({'old':old_id,'issuer':node['issuer'],'rule':node['rule'],
                          'parents':[mapping.get(p,p) for p in node['parents']]})
    return {'protocol':'recovery-frontier-v3' if closure else 'recovery-frontier-v2','envelope':digest(envelope_packet),'task_id':task_id,
            'completed':{old:digest(packet) for old,packet in completed.items()},
            'ready':sorted(ready,key=lambda x:(x['issuer'],x['old'])),
            'remaining':len(graph)-len(completed)+(len(invalidated) if closure else 0),'action_authorized':False,
            **({'replacement_map':usable_mapping,
                'usable_completed':{old:digest(p) for old,p in completed.items() if old in usable_mapping},
                'invalidated_replacements':invalidated,'suspended':suspended,
                'requires_replan':bool(invalidated),
                'recovery_complete':len(graph)==len(completed) and not invalidated} if closure else {})}


def rebuild_frontier_claim(gateway,envelope_packet,task_id,completed,receiver,old_id,fact):
    """The caller supplies a fresh model fact; this operation only verifies it."""
    state=frontier(gateway,envelope_packet,task_id,completed,receiver)
    candidates=[n for n in state['ready'] if n['old']==old_id and n['issuer']==gateway.owner]
    if len(candidates)!=1: raise ValueError('node is not in this issuer recovery frontier')
    node=candidates[0]; registrations=[]
    for parent in node['parents']:
        if gateway.blockers(parent): raise ValueError('new parent not locally usable')
        receipts=[e for e in gateway.events if e['body']['action']=='received' and e['body']['target']==parent]
        if not receipts: raise ValueError('new parent has no local receive evidence')
        owner,receipt=read(receipts[-1],gateway.public)
        if owner!=gateway.owner: raise ValueError('foreign registration receipt')
        registrations.append(receipts[-1])
    inputs=[gateway.claims[p]['body']['fact'] for p in node['parents']]
    if not valid_derivation(node['rule'],fact,inputs): raise ValueError('model fact violates derivation')
    proof={'state':state,'old':old_id,'registrations':registrations,
           'completed_packets':copy.deepcopy(completed),'envelope_packet':copy.deepcopy(envelope_packet)}
    revision=({'supersedes':old_id,'recovery_binding':{'envelope':digest(envelope_packet),'task_id':task_id}}
              if state['protocol']=='recovery-frontier-v3' else {})
    packet=issue(gateway.owner,gateway.key,{**revision,'kind':'claim','workflow':gateway.workflow,
        'parents':node['parents'],'rule':node['rule'],'fact':copy.deepcopy(fact)})
    if gateway.receive(packet)['body']['action']!='received': raise ValueError('rebuilt claim rejected')
    event=gateway.record('frontier_claim_rebuilt',digest(packet),[old_id,digest(proof)])
    return {'packet':packet,'proof':proof,'event':event,'action_authorized':False}
