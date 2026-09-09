"""Multi-level recovery capability probe with fixed scripted new facts.

This is separated from containment runs: old evidence is already delivered when
revocation occurs. The notice-only arm retains signed sources/derivation/action
checks but intentionally omits the standard recovery task/evidence binding.
"""
import copy
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.documents import digest
from trust_network.demo.network_reliability import run_batch,authority_status
from trust_network.demo.reliability_recovery import replacement_offer,prepare_recovery,build_recovery_evidence,rebuild_derived_claim
from trust_network.demo.recovery_frontier import rebuild_frontier_claim
from trust_network.benchmark.containment import AUTHORITIES,OWNERS


def probe(f,policy,branch='b'):
    nodes={o:ClaimGateway(o,f['keys'][o],f['public'],f['workflow'],AUTHORITIES) for o in OWNERS}
    original=f['roots']['A']; coord=f['trace']['A']['coordinator']; middle=f['trace']['A']['middle_'+branch]
    receiver=nodes['receiver_'+branch]
    for owner in ('source','coordinator','middle_'+branch,'receiver_'+branch):
        for packet in (original,coord,middle,f['auth']['A']): nodes[owner].receive(packet)
    nodes['buyer'].receive(f['auth']['A'])
    nodes['source'].receive(f['revoke']); receiver.receive(f['revoke'])
    proposal={'id':'recovery-A','operation':'approve_invoice','order':'A','claims':[digest(middle),digest(f['auth']['A'])]}
    query=lambda owner,q:authority_status(nodes[owner],q)
    blocked=run_batch(receiver,[proposal],query,lambda p: {'simulated':True})
    result={'branch':branch,'initial':blocked['body']['outputs'][0]['action'],
            'proposal_hash':digest(proposal),'recovery_attempted':False,'recovered':False,
            'source_replaced':False,'derived_rebuilt':0,'error':None,
            'verification_queries':blocked['body']['verification_calls'],
            'decision_origin':'scripted, not a model usability experiment'}
    if policy in ('unmediated','simple_root_gate'):
        result['reason']='no automatic recovery controller in this arm'; return result
    result['recovery_attempted']=True
    newfact=copy.deepcopy(original['body']['fact']); newfact['value']['cents']=110
    newsource=issue('source',f['keys']['source'],{**original['body'],'fact':newfact})
    nodes['source'].receive(newsource)
    offer=replacement_offer(nodes['source'],digest(original),newsource)
    envelope=prepare_recovery(receiver,blocked,[offer]); task=envelope['body']['tasks'][0]
    registration=nodes['coordinator'].receive(newsource)
    result['source_replaced']=True; result['required_rebuild_count']=len(task['rebuild_required'])
    try:
        if policy=='frontier_v2':
            complete={}
            first=rebuild_frontier_claim(nodes['coordinator'],envelope,proposal['id'],complete,receiver.owner,digest(coord),newfact)
            newcoord=first['packet']; complete[digest(coord)]=newcoord
        elif policy!='recovery_ablation':
            evidence=build_recovery_evidence(nodes['coordinator'],envelope,task,offer,registration,newsource)
            newcoord=rebuild_derived_claim(nodes['coordinator'],envelope,task,newfact,evidence=evidence)
        else:
            # Notice-only adapter. Exactly the same correct fixed fact and new
            # parent, no forced invalid bundle passed to the protected API.
            newcoord=issue('coordinator',f['keys']['coordinator'],{**coord['body'],'parents':[digest(newsource)],'fact':newfact})
            if nodes['coordinator'].receive(newcoord)['body']['action']!='received': raise ValueError('notice derivation rejected')
        result['derived_rebuilt']+=1
        mid=nodes['middle_'+branch]
        for packet in (newsource,newcoord): mid.receive(packet)
        if policy=='frontier_v2':
            newmiddle=rebuild_frontier_claim(mid,envelope,proposal['id'],complete,receiver.owner,digest(middle),newfact)['packet']
        else:
            newmiddle=issue(mid.owner,mid.key,{**middle['body'],'parents':[digest(newcoord)],'fact':newfact})
        if mid.receive(newmiddle)['body']['action']!='received': raise ValueError('middle derivation rejected')
        result['derived_rebuilt']+=1
        for packet in (newsource,newcoord,newmiddle): receiver.receive(packet)
        retry={**proposal,'claims':[digest(newmiddle),digest(f['auth']['A'])]}
        final=run_batch(receiver,[retry],query,lambda p:{'simulated':True})
        result['verification_queries']+=final['body']['verification_calls']
        result['recovered']=final['body']['outputs'][0]['action']=='COMPLETED'
        result['final_batch']=final
    except ValueError as exc: result['error']=str(exc)
    result['old_revocation_retained']=digest(original) in receiver.revoked
    return result
