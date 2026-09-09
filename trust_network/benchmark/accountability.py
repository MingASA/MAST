"""Public-evidence audit. No fixture truth, private state or global notice union."""
from trust_network.demo.claim_channel import read
from trust_network.demo.claim_derivation import valid_derivation
from trust_network.demo.documents import digest


def audit(result):
    packets=result['packets']; public=result['public_keys']; notices={}; findings=[]
    for cid,p in packets.items():
        read(p,public)
        if cid!=digest(p): raise ValueError('packet index mismatch')
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
            if owner!=event['owner'] or body['action']!=event['outcome']['action']:
                raise ValueError('use receipt mismatch')
            if body['action']=='COMPLETED':
                used_roots=set().union(*(roots(c) for c in body['proposal']['claims']))
                notified=[r for r in used_roots if (owner,r) in notices]
                findings.append({'organization':owner,'event':i,'roots':sorted(used_roots),
                    'classification':'use_after_own_notice' if notified else 'no_proven_notice_violation',
                    'notified_roots':notified,'causal_legal_blame':'undetermined'})
    transforms=[]
    for cid,p in packets.items():
        body=p['body']; parents=body.get('parents',[])
        if body.get('kind')=='claim' and parents and all(c in packets for c in parents):
            if not valid_derivation(body.get('rule','relay'),body['fact'],[packets[c]['body']['fact'] for c in parents]):
                transforms.append({'claim':cid,'issuer':p['signature']['issuer'],'classification':'invalid_signed_derivation'})
    return {'findings':findings,'invalid_transformations':transforms,
            'source_issuers':{c:p['signature']['issuer'] for c,p in packets.items() if p['body'].get('kind')=='claim' and not p['body']['parents']},
            'truth_accessed':False,'effect_proven':False,'causal_legal_blame':'undetermined',
            'limits':['controller_hash_chain_is_not_a_remote_delivery_proof',
                      'absence_of_notice_does_not_prove_absence_of_other_knowledge']}
