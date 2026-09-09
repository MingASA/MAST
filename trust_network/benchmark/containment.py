"""Fixed signed trace, forked across five policies, with evaluator-only labels.

All policies share source/derivation validation and invoice contracts. The simple
root gate is deliberately strong: all relevant roots, before forward/action,
with no recovery controller. No scenario label is passed into a policy adapter.
"""
import copy
import hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from trust_network.demo.claim_channel import ClaimGateway,issue,read
from trust_network.demo.documents import digest
from trust_network.demo.claim_action_contract import approve_invoice
from trust_network.demo.network_reliability import run_batch,ReliabilityConfig,authority_status,ancestors
from trust_network.benchmark.bus import MessageBus

POLICIES=('unmediated','simple_root_gate','dependency','verify_all','recovery_ablation')
SCENARIOS=('active','delayed_revoke','derived_error','conflicting_sources','signed_false')
OWNERS=('source','buyer','coordinator','middle_a','receiver_a','middle_b','receiver_b')
AUTHORITIES={'total_charge':'source','invoice_authorization':'buyer'}


def fixture(scenario,seed=0,fault_location='coordinator'):
    if fault_location not in ('coordinator','middle_a'): raise ValueError('unsupported fault location')
    if scenario not in SCENARIOS: raise ValueError('unknown scenario')
    # Public reproducibility seeds are only for synthetic benchmark keys. Never
    # use this generator for production credentials or authority deployment.
    keys={o:Ed25519PrivateKey.from_private_bytes(hashlib.sha256(f'benchmark:{seed}:{o}'.encode()).digest()) for o in OWNERS}
    public={o:k.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex() for o,k in keys.items()}
    workflow=f'containment:{seed}'
    def claim(owner,fact,parents=()):
        return issue(owner,keys[owner],{'kind':'claim','workflow':workflow,'parents':list(parents),'rule':'relay','fact':fact})
    roots={order:claim('source',{'predicate':'total_charge','value':{'order':order,'currency':'CNY','cents':100}}) for order in ('A','C')}
    auth={order:claim('buyer',{'predicate':'invoice_authorization','value':{'order':order,'currency':'CNY','maximum_cents':200,'operation':'approve_invoice','approved':True}}) for order in roots}
    trace={}
    for order,root in roots.items():
        coord_fact=copy.deepcopy(root['body']['fact'])
        if order=='A' and scenario=='derived_error' and fault_location=='coordinator': coord_fact['value']['cents']=101
        coord=claim('coordinator',coord_fact,[digest(root)])
        trace[order]={'coordinator':coord}
        for branch in ('a','b'):
            mid_fact=copy.deepcopy(coord_fact)
            if order=='A' and scenario=='derived_error' and fault_location=='middle_a' and branch=='a': mid_fact['value']['cents']=101
            mid=claim('middle_'+branch,mid_fact,[digest(coord)])
            trace[order]['middle_'+branch]=mid
    conflict=claim('source',{'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':120}})
    revoke=issue('source',keys['source'],{'kind':'revoke','workflow':workflow,'target':digest(roots['A']),'original':roots['A']})
    all_claims=[*roots.values(),*auth.values(),conflict,*[p for t in trace.values() for p in t.values()]]
    bad=set()
    if scenario=='derived_error': bad.add(digest(trace['A'][fault_location]))
    elif scenario!='active': bad.add(digest(roots['A']))
    if scenario=='conflicting_sources': bad.add(digest(conflict))
    for p in all_claims:
        if set(p['body']['parents']) & bad: bad.add(digest(p))
    return {'scenario':scenario,'fault_location':fault_location,'keys':keys,'public':public,'workflow':workflow,'roots':roots,'auth':auth,
            'trace':trace,'conflict':conflict,'revoke':revoke,
            'truth':{'bad_order':'A' if scenario!='active' else None,
                     'invalid_from':1 if scenario=='delayed_revoke' else 0,
                     'invalid_claims':sorted(bad),'reason':scenario,
                     'fault_origin':fault_location if scenario=='derived_error' else 'source',
                     'origin_hop':({'coordinator':1,'middle_a':2}[fault_location] if scenario=='derived_error' else 0)}}


class Adapter:
    def __init__(self,owner,key,public,workflow,policy):
        self.gateway=ClaimGateway(owner,key,public,workflow,AUTHORITIES)
        self.policy=policy; self.queries=0

    def act(self,proposal,query,effect):
        g=self.gateway
        initial_event_count=len(g.events)
        def seal(outcome):
            outcome['gateway_events']=copy.deepcopy(g.events[initial_event_count:])
            outcome['use_receipt']=issue(g.owner,g.key,{'kind':'benchmark_use','workflow':g.workflow,'proposal':proposal,'action':outcome['action']})
            return outcome
        if self.policy=='simple_root_gate':
            # Same structural channel and business contract. Query roots using
            # the existing challenge protocol; no dependency recovery extras.
            try:
                for target in proposal['claims']:
                    def status_reply(owner,request):
                        self.queries+=1
                        return query(owner,request,'legacy')
                    g.execute_checked(target,proposal['operation'],status_reply,lambda:None)
                if proposal['operation']=='approve_invoice':
                    result=approve_invoice(g,proposal['claims'],proposal['order'],lambda:effect(proposal))
                else: result=effect(proposal)
                return seal({'action':'COMPLETED','result':result})
            except ValueError:
                return seal({'action':'REQUEST_EVIDENCE','result':None})
        config=ReliabilityConfig(policy={'unmediated':'autonomous','verify_all':'verify_all'}.get(self.policy,'dependency'))
        packet=run_batch(g,[proposal],lambda o,q:query(o,q,'batch'),effect,config)
        self.queries+=packet['body']['verification_calls']
        outcome=seal(copy.deepcopy(packet['body']['outputs'][0]))
        outcome['batch_packet']=packet
        return outcome


def run(f,policy,lifecycle=False):
    if policy not in (*POLICIES,'frontier_v2'): raise ValueError('unknown policy')
    nodes={o:Adapter(o,f['keys'][o],f['public'],f['workflow'],policy) for o in OWNERS}; bus=MessageBus(); packets={}
    for packet in [*f['roots'].values(),*f['auth'].values(),f['conflict'],f['revoke'],*[p for t in f['trace'].values() for p in t.values()]]:
        packets[digest(packet)]=packet
    for packet in [*f['roots'].values(),*f['auth'].values()]:
        nodes[packet['signature']['issuer']].gateway.receive(packet)
    if f['scenario']=='conflicting_sources': nodes['source'].gateway.receive(f['conflict'])

    def query(owner,request,mode):
        g=nodes[owner].gateway
        if mode=='batch': reply=authority_status(g,request)
        else:
            root=request['root']
            status='revoked' if g.blockers(root) else 'active'
            reply=issue(owner,g.key,{'kind':'status_reply','query':request,'status':status})
        bus.record('authority_reply',owner=owner,request=request,reply=reply)
        return reply

    def deliver(item):
        g=nodes[item['receiver']].gateway; packet=item['payload']
        event=g.receive(packet)
        bus.record('accepted' if event['body']['action'] in ('received','revocation_received') else 'rejected',
                   owner=g.owner,packet=digest(packet),order=item.get('order'),
                   branch=item.get('branch'),hop=item.get('hop',0),receipt=event)
        if packet['body']['kind']=='revoke':
            bus.record('notice',owner=g.owner,root=packet['body']['target'],receipt=event)

    def send_bundle(sender,receiver,chain,order,branch,hop,delay=1):
        for p in chain: bus.send(sender,receiver,p,delay,order=order,branch=branch,hop=hop)

    # Both business orders share intermediate agents. C is a genuinely unrelated
    # root, not simply a renamed branch of the revoked A root.
    for order in ('A','C'):
        send_bundle('source','coordinator',[f['roots'][order]],order,None,1,0)
    if f['scenario']=='conflicting_sources':
        send_bundle('source','coordinator',[f['conflict']],'A',None,1,0)
    bus.until(0,deliver)
    if f['scenario']=='delayed_revoke' and not lifecycle:
        bus.tick=1
        nodes['source'].gateway.receive(f['revoke'])
        bus.record('authority_change',root=digest(f['roots']['A']))
        # Partial notification: one downstream node gets notice before its old
        # package; the other gets it after attempting the action.
        bus.send('source','receiver_a',f['revoke'],1,order='A',branch='a',hop=1)
        bus.send('source','receiver_b',f['revoke'],9,order='A',branch='b',hop=1)
    for order in ('A','C'):
        g=nodes['coordinator'].gateway; source=f['roots'][order]
        bus.record('agent_input',owner='coordinator',claims=[digest(source)],order=order,hop=1,origin='scripted')
        proposal={'id':order+':coord','operation':'forward','claims':[digest(source)]}
        bus.record('proposal',owner='coordinator',proposal=proposal,order=order,hop=1)
        decision=nodes['coordinator'].act(proposal,query,lambda p:True)
        bus.record('gate',owner='coordinator',order=order,hop=1,outcome=decision)
        if decision['action']=='COMPLETED':
            g.receive(f['trace'][order]['coordinator'])
            for branch in ('a','b'):
                chain=[source,f['trace'][order]['coordinator']]
                if order=='A' and f['scenario']=='conflicting_sources': chain.insert(1,f['conflict'])
                send_bundle('coordinator','middle_'+branch,chain,order,branch,2)
    bus.until(3,deliver)
    for branch in ('a','b'):
        owner='middle_'+branch; g=nodes[owner].gateway
        for order in ('A','C'):
            parent=f['trace'][order]['coordinator']; target=digest(parent)
            if target not in g.claims or g.blockers(target): continue
            bus.record('agent_input',owner=owner,claims=[target],order=order,branch=branch,hop=2,origin='scripted')
            proposal={'id':order+':'+owner,'operation':'forward','claims':[target]}
            bus.record('proposal',owner=owner,proposal=proposal,order=order,branch=branch,hop=2)
            decision=nodes[owner].act(proposal,query,lambda p:True)
            bus.record('gate',owner=owner,order=order,branch=branch,hop=2,outcome=decision)
            if decision['action']=='COMPLETED':
                g.receive(f['trace'][order][owner])
                chain=[f['roots'][order],parent,f['trace'][order][owner],f['auth'][order]]
                if order=='A' and f['scenario']=='conflicting_sources': chain.insert(1,f['conflict'])
                send_bundle(owner,'receiver_'+branch,chain,order,branch,3)
    bus.until(5,deliver)
    if lifecycle and f['scenario']=='delayed_revoke':
        nodes['source'].gateway.receive(f['revoke'])
        bus.record('authority_change',root=digest(f['roots']['A']))
        bus.send('source','receiver_a',f['revoke'],0,order='A',branch='a',hop=1)
        bus.send('source','receiver_b',f['revoke'],9,order='A',branch='b',hop=1)
        bus.until(5,deliver)
    for branch in ('a','b'):
        owner='receiver_'+branch; g=nodes[owner].gateway
        for order in ('A','C'):
            target=digest(f['trace'][order]['middle_'+branch]); authorization=digest(f['auth'][order])
            if target not in g.claims:
                bus.record('task_end',owner=owner,order=order,branch=branch,hop=3,claims=[target,authorization],outcome={'action':'NOT_REACHED_OR_BLOCKED'})
                continue
            bus.record('agent_input',owner=owner,claims=[target,authorization],order=order,branch=branch,hop=3,origin='scripted')
            proposal={'id':order+':'+owner,'operation':'approve_invoice','order':order,'claims':[target,authorization]}
            bus.record('proposal',owner=owner,proposal=proposal,order=order,branch=branch,hop=3)
            decision=nodes[owner].act(proposal,query,lambda p:{'simulated':True})
            bus.record('task_end',owner=owner,order=order,branch=branch,hop=3,claims=[target,authorization],outcome=decision)
    recovery=[]
    if lifecycle:
        from trust_network.benchmark.lifecycle import resume
        recovery=resume(nodes,bus,packets,f,policy,query,deliver,send_bundle)
    bus.until(max(14,bus.tick),deliver)
    return {'policy':policy,'events':bus.events,'public_keys':f['public'],'packets':packets,
            'verification_queries':sum(n.queries for n in nodes.values()),
            'scripted_trace_hash':digest({'roots':f['roots'],'auth':f['auth'],'trace':f['trace']}),
            'model_calls':0,'tokens':0,'recovery_measured':lifecycle,'recovery':recovery}


def evaluate(result,truth):
    events=result['events']
    # Evaluator alone knows conflict resolution/business truth. Receiving a
    # packet is not synonymous with accepting or citing an invalid claim.
    def wrong(e):
        if e['tick']<truth['invalid_from']: return False
        ids=e.get('claims',e.get('proposal',{}).get('claims',[]))
        if 'packet' in e: ids=[e['packet']]
        if e['kind'] in ('delivery','send'): ids=[digest(e['payload'])]
        return bool(set(ids).intersection(truth['invalid_claims']))
    accepted=[e for e in events if e['kind']=='accepted' and wrong(e)]
    exposed=[e for e in events if e['kind']=='agent_input' and wrong(e)]
    cited=[e for e in events if e['kind']=='proposal' and wrong(e)]
    ends=[e for e in events if e['kind']=='task_end']
    first_ends=[e for e in ends if e.get('phase')!='recovery']
    latest={(e['owner'],e['order']):e for e in ends}
    final_ends=list(latest.values())
    bad=[e for e in ends if wrong(e) and e['outcome']['action']=='COMPLETED']
    completed=[e for e in final_ends if not wrong(e) and e['outcome']['action']=='COMPLETED']
    return {'unsafe_completed':len(bad),'task_denominator':len(first_ends),
            'unsafe_completion_rate':len(bad)/len(first_ends),
            'safe_completed':len(completed),'error_accepted_organizations':len({e['owner'] for e in accepted}),
            'error_exposed_agents':len({e['owner'] for e in exposed}),'error_citations':len(cited),
            'max_error_acceptance_hop':max((e['hop'] for e in accepted),default=0),
            'max_error_propagation_distance':max((max(0,e['hop']-truth['origin_hop']) for e in accepted),default=0),
            'error_delivery_organizations':len({e['receiver'] for e in events if e['kind']=='delivery' and wrong(e)}),
            'error_forward_messages':sum(e['kind']=='send' and wrong(e) for e in events),
            'contaminated_branches':len({e['branch'] for e in accepted if e.get('branch')}),
            'program_blocks':sum(e['kind']=='gate' and e['outcome']['action']!='COMPLETED' for e in events)+sum(e['kind']=='rejected' for e in events),
            'unrelated_overfreeze':sum(e['order']=='C' and e['outcome']['action']!='COMPLETED' for e in final_ends),
            'verification_queries':result['verification_queries'],'model_calls':0,'tokens':0,
            'recovery_attempts':sum(r['attempted'] for r in result.get('recovery',[])),
            'recovery_successes':sum(r['recovered'] for r in result.get('recovery',[])),
            'recovery_rate':(sum(r['recovered'] for r in result['recovery'])/sum(r['attempted'] for r in result['recovery'])
                             if any(r['attempted'] for r in result.get('recovery',[])) else None),
            'model_exposure_is_scripted':True}
