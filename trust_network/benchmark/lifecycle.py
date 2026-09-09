"""Continue the SAME bus, gateways and tasks after a blocked action.

No fixture reset or direct preload of evidence. Authority source changes are
controlled business events. Every cross-organization claim goes through the bus;
recovery models are fixed scripted decisions, labeled accordingly.
"""
import copy
from trust_network.demo.claim_channel import issue
from trust_network.demo.documents import digest
from trust_network.demo.reliability_recovery import replacement_offer,prepare_recovery,build_recovery_evidence,rebuild_derived_claim
from trust_network.demo.recovery_frontier import rebuild_frontier_claim


def resume(nodes,bus,packets,f,policy,query,deliver,send_bundle):
    initial=[e for e in bus.events if e['kind']=='task_end' and e['order']=='A']
    results=[]; source=nodes['source'].gateway; original=f['roots']['A']
    newsource=None; offer=None
    def transfer(sender,receiver,items,branch,hop=0):
        for p in items: packets[digest(p)]=p
        send_bundle(sender,receiver,items,'A',branch,hop)
        bus.until(bus.tick+1,deliver)
    for end in initial:
        branch=end['branch']; recipient=end['owner']; receiver=nodes[recipient].gateway
        row={'branch':branch,'attempted':False,'recovered':False,'error':None,'rebuilt':0}
        results.append(row)
        if end['outcome']['action'] in ('COMPLETED','EFFECT_UNKNOWN'):
            row['reason']='completed_or_unknown_never_retried';continue
        if policy in ('unmediated','simple_root_gate'):
            row['reason']='no_automatic_recovery_in_arm';continue
        blocked=end['outcome'].get('batch_packet')
        # Eligible from local signed failure plus the authority's own state;
        # there is no branch on scenario labels or evaluator truth here.
        if blocked is None or digest(original) not in source.revoked:
            row['reason']='no_recoverable_authority_change';continue
        row['attempted']=True
        try:
            if newsource is None:
                fact=copy.deepcopy(original['body']['fact']);fact['value']['cents']=110
                newsource=issue(source.owner,source.key,{**original['body'],'fact':fact})
                source.receive(newsource);packets[digest(newsource)]=newsource
                offer=replacement_offer(source,digest(original),newsource)
                bus.record('replacement_issued',owner=source.owner,old=digest(original),packet=digest(newsource),
                           offer=offer,decision_origin='controlled_business_event')
            # Offer is a protocol artifact, not a claim-channel message.
            bus.record('recovery_offer_delivered',sender='source',owner=recipient,offer=offer)
            envelope=prepare_recovery(receiver,blocked,[offer]);task=envelope['body']['tasks'][0]
            bus.record('recovery_envelope',owner=recipient,packet=envelope,branch=branch)
            oldmid=receiver.claims[end['claims'][0]]
            oldcoord=receiver.claims[oldmid['body']['parents'][0]]
            # Coordinator needs public old downstream proof to validate the task
            # DAG. It arrives from receiver, not from a shared/global claim store.
            transfer(recipient,'coordinator',[oldcoord,oldmid],branch)
            transfer('source','coordinator',[newsource],branch,1)
            coordinator=nodes['coordinator'].gateway
            registration=next(e for e in reversed(coordinator.events) if e['body']['action']=='received' and e['body']['target']==digest(newsource))
            fact=copy.deepcopy(newsource['body']['fact'])
            bus.record('agent_input',owner='coordinator',order='A',branch=branch,hop=1,
                       claims=[digest(newsource)],origin='scripted',phase='recovery')
            bus.record('recovery_decision',owner='coordinator',fact=fact,branch=branch,origin='scripted')
            completed={}
            if policy=='frontier_v2':
                rebuilt=rebuild_frontier_claim(coordinator,envelope,task['proposal']['id'],completed,recipient,digest(oldcoord),fact)
                coord=rebuilt['packet'];bus.record('rebuild',owner='coordinator',branch=branch,artifact=rebuilt)
                completed[digest(oldcoord)]=coord
            elif policy=='recovery_ablation':
                coord=issue(coordinator.owner,coordinator.key,{**oldcoord['body'],'parents':[digest(newsource)],'fact':fact})
                if coordinator.receive(coord)['body']['action']!='received': raise ValueError('notice-only coordinator rejected')
            else:
                evidence=build_recovery_evidence(coordinator,envelope,task,offer,registration,newsource)
                coord=rebuild_derived_claim(coordinator,envelope,task,fact,evidence=evidence)
            row['rebuilt']+=1
            middle=nodes['middle_'+branch].gateway
            transfer('coordinator',middle.owner,[newsource,coord],branch,2)
            bus.record('agent_input',owner=middle.owner,order='A',branch=branch,hop=2,
                       claims=[digest(coord)],origin='scripted',phase='recovery')
            bus.record('recovery_decision',owner=middle.owner,fact=fact,branch=branch,origin='scripted')
            if policy=='frontier_v2':
                rebuilt=rebuild_frontier_claim(middle,envelope,task['proposal']['id'],completed,recipient,digest(oldmid),fact)
                mid=rebuilt['packet'];bus.record('rebuild',owner=middle.owner,branch=branch,artifact=rebuilt)
            else:
                mid=issue(middle.owner,middle.key,{**oldmid['body'],'parents':[digest(coord)],'fact':fact})
                if middle.receive(mid)['body']['action']!='received': raise ValueError('notice-only middle rejected')
            row['rebuilt']+=1
            transfer(middle.owner,recipient,[newsource,coord,mid],branch,3)
            proposal={**task['proposal'],'claims':[digest(mid),digest(f['auth']['A'])]}
            bus.record('agent_input',owner=recipient,order='A',branch=branch,hop=3,phase='recovery',
                       claims=proposal['claims'],origin='scripted')
            bus.record('proposal',owner=recipient,order='A',branch=branch,hop=3,phase='recovery',proposal=proposal)
            decision=nodes[recipient].act(proposal,query,lambda p:{'simulated':True})
            bus.record('task_end',owner=recipient,order='A',branch=branch,hop=3,claims=proposal['claims'],
                       phase='recovery',outcome=decision)
            row['recovered']=decision['action']=='COMPLETED'
        except ValueError as exc:
            row['error']=str(exc)
            bus.record('recovery_failed',owner=recipient,branch=branch,error=str(exc))
        row['old_revocation_retained']=digest(original) in receiver.revoked
    return results
