"""Deterministic dispute propagation and explicit confirmed recovery via RPC.

All proposed amounts are supplied by the scripted issuer, not invented from
negative evidence. This is an offline protocol exercise, not live Agent data.
"""
import argparse
import json
from pathlib import Path
from trust_network.benchmark.workflow.backend import MemoryBackend,ProcessBackend
from trust_network.benchmark.workflow.spec import workload,ARMS,OWNERS,AUTHORITIES
from trust_network.demo.fact_evidence import scope_key
from trust_network.demo.documents import digest
from trust_network.demo.notification_pump import guarded_handoff,pump_notifications
from trust_network.demo.dispute_protocol import audit_exchange
from trust_network.demo.reliability_audit import audit_with_authorities


def run(backend='memory',directory=None):
    f=workload();ledger={scope_key(f['workflow'],f['roots'][o]['body']['fact']):
        {'cents':125 if o=='A' else 100,'version':'v1','status':'confirmed'} for o in ('A','C')}
    private={'buyer':{'settlement_registry':ledger}}
    b=MemoryBackend(f,ARMS['dependency'],private_state=private) if backend=='memory' else ProcessBackend(f,ARMS['dependency'],directory,private_state=private)
    log=[];b.observer=lambda owner,request,response,sender:log.append({'owner':owner,'request':request,'response':response,'sender':sender})
    def rpc(o,op,**kw):return b.call(o,{'operation':op,**kw},sender='scripted-lifecycle')
    def invoice(o,order,claims,intent='execute'):
        packet=rpc(o,'reliability_batch',proposals=[{'id':o+order,'operation':'approve_invoice',
            'order':order,'claims':claims,'intent':intent}])['batch']
        audit_with_authorities(packet,f['public'],AUTHORITIES,{'settlement_basis_v1':'buyer'})
        return packet
    # Existing claim graph is already shared before anyone discovers dispute.
    mids={}
    for order in ('A','C'):
        root=f['roots'][order];rpc('source','receive',packet=root)
        guarded_handoff(b.call,'source','coordinator',[digest(root)],'publish'+order)
        coord=rpc('coordinator','reliability_sign_derived',parents=[digest(root)],fact_ref=digest(root))['packet']
        rpc('buyer','receive',packet=f['auth'][order])
        for branch in ('a','b'):
            mid='middle_'+branch;receiver='receiver_'+branch
            guarded_handoff(b.call,'coordinator',mid,[digest(coord)],'coord'+order+branch)
            packet=rpc(mid,'reliability_sign_derived',parents=[digest(coord)],fact_ref=digest(coord))['packet'];mids[(branch,order)]=packet
            guarded_handoff(b.call,mid,receiver,[digest(packet)],'mid'+order+branch)
            guarded_handoff(b.call,'buyer',receiver,[digest(f['auth'][order])],'auth'+order+branch)
    # Coordinator now checks its already-propagated A graph against authority.
    policy={'policy':'verify_all','authority':'buyer'}
    if backend=='memory':b.configs['coordinator']['fact_policy']=policy
    else:
        p=Path(directory)/'coordinator'/'config.json';config=json.loads(p.read_text());config['fact_policy']=policy;p.write_text(json.dumps(config))
    cid=digest(f['roots']['A'])
    detection=rpc('coordinator','reliability_batch',proposals=[{'id':'discover','operation':'forward','claims':[cid],'intent':'verify'}])['batch']
    proof=detection['body']['fact_checks']['discover']['exchanges'][0]['reply']
    pumped=pump_notifications(b.call,OWNERS)
    blocked={};normal={};claims={}
    for branch in ('a','b'):
        owner='receiver_'+branch;claims[branch]=[digest(mids[(branch,'A')]),digest(f['auth']['A'])]
        blocked[branch]=invoice(owner,'A',claims[branch]);normal[branch]=invoice(owner,'C',[digest(mids[(branch,'C')]),digest(f['auth']['C'])])
    # Explicit issuer input, independently checked. Registration alone never
    # retracts source: this API is the source's affirmative correction choice.
    rpc('source','reliability_dispute_register',proof=proof)
    fact={**f['roots']['A']['body']['fact'],'value':{**f['roots']['A']['body']['fact']['value'],'cents':125}}
    offer=rpc('source','reliability_dispute_revision',proof=proof,fact=fact)['offer']
    recovery={}
    for branch in ('a','b'):
        owner='receiver_'+branch;task=owner+'A'
        envelope=rpc(owner,'reliability_closure_recovery',batch=blocked[branch],offers=[offer])['recovery']
        completed={}
        for _ in range(8):
            state=rpc(owner,'reliability_frontier',envelope=envelope,task_id=task,completed=completed)['frontier']
            if not state['remaining']:break
            if not state['ready']:raise ValueError('recovery did not progress')
            node=state['ready'][0];actor=node['issuer']
            for p in [*envelope['body']['batch_packet']['body']['evidence']['claims'],offer['body']['new'],*completed.values()]:rpc(actor,'receive',packet=p)
            packet=rpc(actor,'reliability_frontier_rebuild',envelope=envelope,task_id=task,completed=completed,old=node['old'],fact_ref=node['parents'][0])['packet']
            completed[node['old']]=packet;rpc(owner,'receive',packet=packet)
        else:raise ValueError('recovery budget exhausted')
        newclaims=[state['replacement_map'].get(c,c) for c in claims[branch]]
        # Fresh confirmation is checked again before the final explicit action.
        if backend=='memory':b.configs[owner]['fact_policy']=policy
        else:
            p=Path(directory)/owner/'config.json';config=json.loads(p.read_text());config['fact_policy']=policy;p.write_text(json.dumps(config))
        recovery[branch]=invoice(owner,'A',newclaims)
    audits=[]
    for row in log:
        if row['request']['operation']=='reliability_notification_accept' and row['request']['packet']['body']['kind']=='dependency_dispute':
            audits.append(audit_exchange(row['request']['packet'],row['response'].get('result'),f['public'],AUTHORITIES,{'settlement_basis_v1':'buyer'}))
    result={'backend':backend,'decision_source':'scripted','new_model_calls':0,'notifications':pumped,
        'A_blocked':{k:v['body']['outputs'][0]['action'] for k,v in blocked.items()},
        'C_continues':{k:v['body']['outputs'][0]['action'] for k,v in normal.items()},
        'A_recovered':{k:v['body']['outputs'][0]['action'] for k,v in recovery.items()},'notice_audits':audits}
    return result,log,b


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--backend',choices=['memory','process'],default='memory')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    result,log,_=run(a.backend,a.out/'organizations')
    (a.out/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (a.out/'trace.json').write_text(json.dumps(log,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
