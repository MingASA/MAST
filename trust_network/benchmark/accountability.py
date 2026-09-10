"""Public-evidence audit. No fixture truth, private state or global notice union."""
from trust_network.demo.claim_channel import read
from trust_network.demo.claim_derivation import valid_derivation
from trust_network.demo.documents import digest


def audit(result):
    packets=result['packets']; public=result['public_keys']; notices={}; findings=[]
    for cid,p in packets.items():
        read(p,public)
        if cid!=digest(p): raise ValueError('packet index mismatch')
    # Signed local predecessors, not transport order, establish notice-before-use.
    local={}; notices_by_owner={}
    for event in result['events']:
        receipts=([event['receipt']] if event.get('receipt') else [])
        receipts+=event.get('outcome',{}).get('gateway_events',[])
        for packet in receipts:
            owner,body=read(packet,public)
            if body.get('kind')!='gateway_event': raise ValueError('invalid local event')
            if event.get('owner')!=owner: raise ValueError('foreign local gateway event')
            local[digest(packet)]=(owner,body)
            if body.get('action')=='revocation_received':
                notices_by_owner.setdefault(owner,[]).append((body['target'],digest(packet)))
    from trust_network.demo.evidence_order import precedes
    def dependencies(cid,visiting=None):
        visiting=set() if visiting is None else visiting
        if cid in visiting: raise ValueError('cyclic evidence')
        if cid not in packets: return {cid}
        path=visiting|{cid}
        return {cid}.union(*(dependencies(p,path) for p in packets[cid]['body'].get('parents',[])))
    def roots(cid):
        if cid not in packets: return set()
        parents=packets[cid]['body'].get('parents',[])
        return set().union(*(roots(p) for p in parents)) if parents else {cid}
    for i,event in enumerate(result['events']):
        if event['sequence']!=i or event['previous']!=(digest(result['events'][i-1]) if i else None):
            raise ValueError('transport trace chain mismatch')
        if event['kind']=='notice':
            owner,receipt=read(event['receipt'],public)
            if owner!=event['owner'] or receipt.get('action')!='revocation_received' or receipt['target']!=event['root']:
                raise ValueError('invalid receiver notice receipt')
            notices[(owner,event['root'])]=i
        if event['kind'] in ('gate','task_end'):
            for packet in event['outcome'].get('gateway_events',[]):
                owner,receipt=read(packet,public)
                if owner!=event['owner']: raise ValueError('foreign local gateway event')
                if receipt.get('action')=='revocation_received':
                    notices[(owner,receipt['target'])]=i
        if event['kind'] in ('gate','task_end') and 'use_receipt' in event['outcome']:
            owner,body=read(event['outcome']['use_receipt'],public)
            if body.get('kind')!='benchmark_use' or owner!=event['owner'] or body['action']!=event['outcome']['action']:
                raise ValueError('use receipt mismatch')
            if body['action']=='COMPLETED':
                if any(c in packets and packets[c]['body'].get('workflow')!=body['workflow'] for c in body['proposal']['claims']):
                    raise ValueError('foreign workflow claim use')
                used_roots=set().union(*(roots(c) for c in body['proposal']['claims']))
                used=set().union(*(dependencies(c) for c in body['proposal']['claims']))
                notified=sorted({target for target,receipt in notices_by_owner.get(owner,[])
                    if target in used and precedes(local,receipt,body.get('local_head'),owner,body['workflow'])})
                findings.append({'organization':owner,'event':i,'roots':sorted(used_roots),
                    'classification':'use_after_own_notice' if notified else 'no_proven_notice_violation',
                    'notified_roots':sorted(set(notified)&used_roots),'notified_claims':notified,
                    'dependencies':sorted(used),'ordering_basis':'signed_local_predecessors','causal_legal_blame':'undetermined'})
    transforms=[]
    for cid,p in packets.items():
        body=p['body']; parents=body.get('parents',[])
        if body.get('kind')=='claim' and parents and all(c in packets for c in parents):
            if not valid_derivation(body.get('rule','relay'),body['fact'],[packets[c]['body']['fact'] for c in parents]):
                transforms.append({'claim':cid,'issuer':p['signature']['issuer'],'classification':'invalid_signed_derivation'})
    return {'findings':findings,'invalid_transformations':transforms,
            'source_issuers':{c:p['signature']['issuer'] for c,p in packets.items() if p['body'].get('kind')=='claim' and not p['body']['parents']},
            'claim_issuers':{c:p['signature']['issuer'] for c,p in packets.items() if p['body'].get('kind')=='claim'},
            'dependency_edges':[{'parent':parent,'child':c,'issuer':p['signature']['issuer']}
                for c,p in packets.items() if p['body'].get('kind')=='claim' for parent in p['body']['parents']],
            'truth_accessed':False,'effect_proven':False,'causal_legal_blame':'undetermined',
            'limits':['controller_hash_chain_is_not_a_remote_delivery_proof',
                      'absence_of_notice_does_not_prove_absence_of_other_knowledge']}
