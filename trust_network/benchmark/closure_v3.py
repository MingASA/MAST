"""Paired offline v3 mechanism harness. No model or ground-truth input to policy.

Every arm gets identical signed claims and scripted proposals. Recovery is an
independent factor; source/derived revisions are controlled issuer decisions.
"""
import argparse
import copy
import json
from pathlib import Path
from trust_network.benchmark.containment import fixture,AUTHORITIES,OWNERS,evaluate
from trust_network.benchmark.bus import MessageBus
from trust_network.benchmark.accountability import audit
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.documents import digest
from trust_network.demo.network_reliability import run_batch,ReliabilityConfig,authority_status,ancestors
from trust_network.demo.recovery_closure import revision_offer,prepare_closure_recovery
from trust_network.demo.recovery_frontier import frontier,rebuild_frontier_claim

ARMS={'autonomous':'autonomous','simple_root_gate':'verify_all','dependency':'dependency',
      'dependency_closure':'dependency_closure','verify_all_closure':'verify_all_closure',
      'dependency_closure_selective':'dependency_closure'}
CASES=('active','root_revoke','shared_intermediate_revoke','branch_intermediate_revoke','partial_notice_old_packet')


def run_case(case,arm,recovery='bound'):
    if case not in CASES or arm not in ARMS or recovery not in ('bound','notice_only'):
        raise ValueError('unknown experimental factor')
    f=fixture('active'); bus=MessageBus();packets={};batches=[];queries=0
    transport_phase='work'
    nodes={o:ClaimGateway(o,f['keys'][o],f['public'],f['workflow'],AUTHORITIES) for o in OWNERS}
    # Trusted loss configuration is identical across arms, never from an Agent.
    config=ReliabilityConfig(ARMS[arm],propagation_threshold=2 if arm=='dependency_closure_selective' else 1)
    def store(p):packets[digest(p)]=p
    def receive(item):
        g=nodes[item['receiver']]; p=item['payload'];store(p);receipt=g.receive(p)
        bus.record('accepted' if receipt['body']['action']=='received' else 'rejected',owner=g.owner,
            packet=digest(p),receipt=receipt,order=item.get('order'),branch=item.get('branch'),hop=item.get('hop',0),phase=item.get('phase'))
    def transfer(sender,receiver,items,order='A',branch=None,hop=0):
        for p in items:store(p);bus.send(sender,receiver,p,1,order=order,branch=branch,hop=hop,phase=transport_phase)
        bus.until(bus.tick+1,receive)
    def query(owner,q):
        reply=authority_status(nodes[owner],q)
        bus.record('authority_reply',owner=owner,request=q,reply=reply)
        return reply
    def act(owner,proposal,order,branch,hop,phase=None):
        nonlocal queries
        g=nodes[owner];start=len(g.events)
        bus.record('agent_input',owner=owner,order=order,branch=branch,hop=hop,claims=proposal['claims'],origin='scripted',phase=phase)
        bus.record('proposal',owner=owner,order=order,branch=branch,hop=hop,proposal=proposal,phase=phase)
        packet=run_batch(g,[proposal],query,lambda p:{'simulated':True},config)
        batches.append(packet);queries+=packet['body']['verification_calls']
        for p in g.claims.values():store(p)
        for p in g.revoked.values():store(p)
        outcome=copy.deepcopy(packet['body']['outputs'][0])
        outcome['gateway_events']=g.events[start:];outcome['batch_packet']=packet
        outcome['use_receipt']=issue(owner,g.key,{'kind':'benchmark_use','workflow':g.workflow,
            'proposal':proposal,'action':outcome['action'],'local_head':digest(g.events[-1])})
        bus.record('task_end' if proposal['operation']=='approve_invoice' else 'gate',owner=owner,
            order=order,branch=branch,hop=hop,claims=proposal['claims'],outcome=outcome,phase=phase)
        return packet
    for order in ('A','C'):
        root=f['roots'][order];auth=f['auth'][order];coord=f['trace'][order]['coordinator']
        for p in (root,auth):nodes[p['signature']['issuer']].receive(p);store(p)
        transfer('source','coordinator',[root],order,hop=1)
        nodes['coordinator'].receive(coord);store(coord)
        for branch in ('a','b'):
            owner='middle_'+branch
            transfer('coordinator',owner,[root,coord],order,branch,2)
            mid=f['trace'][order][owner];nodes[owner].receive(mid);store(mid)
    invalid=[];old=None;fault_owner=None
    if case!='active':
        fault_owner=('source' if case=='root_revoke' else 'middle_a' if case=='branch_intermediate_revoke' else 'coordinator')
        original=f['roots']['A'] if fault_owner=='source' else f['trace']['A'][fault_owner]
        old=digest(original);g=nodes[fault_owner]
        revoke=issue(g.owner,g.key,{'kind':'revoke','workflow':g.workflow,'target':old,'original':original})
        g.receive(revoke);store(revoke);bus.record('issuer_retraction',owner=g.owner,packet=revoke)
        # Truth stays exclusively in the evaluation side of this harness.
        invalid=[c for c in packets if packets[c]['body']['kind']=='claim' and old in ancestors_for_packets(packets,c)]
    fault_tick=bus.tick
    if case=='partial_notice_old_packet':
        transfer(fault_owner,'middle_a',[revoke],branch='a')
        transfer(fault_owner,'middle_a',[original],branch='a')
    # Fixed post-change forward proposals. Every actual forwarding side effect
    # is conditional on the same runtime outcome, not on the scenario label.
    for branch in ('a','b'):
        for order in ('A','C'):
            owner='middle_'+branch;mid=f['trace'][order][owner]
            proposal={'id':order+':forward:'+branch,'operation':'forward','claims':[digest(mid)]}
            report=act(owner,proposal,order,branch,2)
            if report['body']['outputs'][0]['action']=='COMPLETED':
                transfer(owner,'receiver_'+branch,[f['roots'][order],f['trace'][order]['coordinator'],mid,f['auth'][order]],order,branch,3)
    initial=[]
    for branch in ('a','b'):
        for order in ('A','C'):
            owner='receiver_'+branch;target=digest(f['trace'][order]['middle_'+branch])
            proposal={'id':order+':invoice:'+branch,'operation':'approve_invoice','order':order,
                'claims':[target,digest(f['auth'][order])],'intent':'execute'}
            # Missing evidence is an ordinary runtime input, not automatic success.
            packet=act(owner,proposal,order,branch,3);initial.append((owner,branch,order,proposal,packet))
    transport_phase='recovery_evidence'
    recovery_rows=[];offered=None
    # The controlled issuer proposes a revision only for its own retraction.
    if old is not None:
        offered=revision_offer(nodes[fault_owner],old,nodes[fault_owner].claims[old]['body']['fact'])
        store(offered['body']['new']);bus.record('revision_offer',owner=fault_owner,packet=offered)
    for owner,branch,order,proposal,blocked in initial:
        row={'branch':branch,'order':order,'attempted':False,'recovered':False,'rebuilt':0,'error':None}
        recovery_rows.append(row)
        if offered is None or blocked['body']['outputs'][0]['action'] in ('COMPLETED','EFFECT_UNKNOWN'):continue
        # Deliver old public ancestry to the receiver if forwarding was blocked.
        # These are recovery evidence messages, never counted as authorized work.
        chain=[f['roots'][order],f['trace'][order]['coordinator'],f['trace'][order]['middle_'+branch],f['auth'][order]]
        transfer('middle_'+branch,owner,chain,order,branch,3)
        g=nodes[owner]
        if old not in set().union(*(ancestors(g,c) for c in proposal['claims'])):continue
        row['attempted']=True
        try:
            envelope=prepare_closure_recovery(g,blocked,[offered]);completed={}
            bus.record('recovery_envelope',owner=owner,packet=envelope,branch=branch)
            task_id=proposal['id'];seed=offered['body']['new']
            while True:
                if recovery=='bound':
                    state=frontier(g,envelope,task_id,completed,owner)
                else:
                    # Scheduling hints are shared, but no evidence-bound frontier
                    # validator is reintroduced in the worker or completion path.
                    task=next(t for t in envelope['body']['tasks'] if t['proposal']['id']==task_id)
                    mapping={**task['replacement_sources'],**{old:digest(p) for old,p in completed.items()}}
                    graph={n['old']:n for n in task['rebuild_required']}
                    ready=[{**n,'parents':[mapping.get(p,p) for p in n['parents']]}
                        for old,n in graph.items() if old not in completed and
                        all(p not in graph or p in completed for p in n['parents'])]
                    state={'remaining':len(graph)-len(completed),'ready':ready,'replacement_map':mapping}
                if not state['remaining']:break
                if not state['ready']:raise ValueError('no ready recovery node')
                node=state['ready'][0];issuer=node['issuer'];ig=nodes[issuer]
                # Old descendants are public task evidence, delivered explicitly.
                transfer(owner,issuer,chain+[seed]+list(completed.values()),order,branch)
                for parent in node['parents']:
                    if ig.blockers(parent):raise ValueError('new parent blocked')
                fact=copy.deepcopy(ig.claims[node['parents'][0]]['body']['fact'])
                bus.record('agent_input',owner=issuer,order=order,branch=branch,hop=2,
                    phase='recovery',claims=node['parents'],origin='scripted')
                if recovery=='bound':
                    rebuilt=rebuild_frontier_claim(ig,envelope,task_id,completed,owner,node['old'],fact)
                    packet=rebuilt['packet'];bus.record('rebuild',owner=issuer,artifact=rebuilt,branch=branch)
                else:
                    # Same valid replacement facts and channel checks, without
                    # worker-side task/evidence validation. Do not call frontier
                    # validation on ablated completed artifacts as a hidden gate.
                    packet=issue(issuer,ig.key,{'kind':'claim','workflow':ig.workflow,'parents':node['parents'],
                        'rule':node['rule'],'fact':fact,'supersedes':node['old'],
                        'recovery_binding':{'envelope':digest(envelope),'task_id':task_id}})
                    if ig.receive(packet)['body']['action']!='received':raise ValueError('notice rebuild rejected')
                    bus.record('notice_rebuild',owner=issuer,packet=packet,branch=branch)
                completed[node['old']]=packet;row['rebuilt']+=1
                transfer(issuer,owner,[seed]+list(completed.values()),order,branch,3)
            mapping=state['replacement_map']
            renewed={**proposal,'claims':[mapping.get(c,c) for c in proposal['claims']]}
            packet=act(owner,renewed,order,branch,3,'recovery')
            row['recovered']=packet['body']['outputs'][0]['action']=='COMPLETED'
        except (ValueError,KeyError) as exc:
            row['error']=str(exc);bus.record('recovery_failed',owner=owner,error=str(exc),branch=branch)
    raw={'policy':arm,'recovery_policy':recovery,'events':bus.events,'public_keys':f['public'],'packets':packets,
        'verification_queries':queries,'model_calls':0,'tokens':0,'recovery_measured':True,'recovery':recovery_rows,
        'batches':batches,'scripted_trace_hash':digest({'roots':f['roots'],'auth':f['auth'],'trace':f['trace']})}
    truth={'invalid_from':fault_tick,'invalid_claims':invalid,'bad_order':'A' if old else None,
        'fault_origin':fault_owner,'origin_hop':0 if fault_owner=='source' else 2 if fault_owner=='middle_a' else 1}
    return raw,truth


def ancestors_for_packets(packets,c):
    p=packets[c]
    return {c}.union(*(ancestors_for_packets(packets,parent) for parent in p['body'].get('parents',[])))


def metrics_for(raw,truth):
    """Keep work propagation, repair transport and action interception distinct."""
    metrics=evaluate(raw,truth);events=raw['events']
    actions=[e for e in events if e['kind'] in ('gate','task_end')]
    blocked=[e for e in actions if e['outcome']['action'] in ('REQUEST_EVIDENCE','ESCALATE','BLOCKED')]
    invalid=set(truth['invalid_claims'])
    metrics['program_blocks']=len(blocked)
    metrics['error_actions_blocked']=sum(e['tick']>=truth['invalid_from'] and
        bool(set(e['claims'])&invalid) for e in blocked)
    metrics['unaffected_branch_blocks']=sum(not bool(set(e['claims'])&invalid) for e in blocked)
    metrics['work_messages']=sum(e['kind']=='send' and e.get('phase')!='recovery_evidence' for e in events)
    metrics['recovery_evidence_messages']=sum(e['kind']=='send' and e.get('phase')=='recovery_evidence' for e in events)
    metrics['verification_cost_units']=raw['verification_queries']  # default authority cost = 1
    metrics['api_attempts']=0
    metrics['agents']={owner:{
        'exposures':sum(e['kind']=='agent_input' and e.get('owner')==owner for e in events),
        'error_exposures':sum(e['kind']=='agent_input' and e.get('owner')==owner and
            e['tick']>=truth['invalid_from'] and bool(set(e.get('claims',[]))&invalid) for e in events),
        'citations':sum(e['kind']=='proposal' and e.get('owner')==owner for e in events),
        'allowed_forwards':sum(e['kind']=='gate' and e['owner']==owner and e['outcome']['action']=='COMPLETED' for e in actions),
        'blocked_actions':sum(e['owner']==owner for e in blocked)} for owner in OWNERS}
    return metrics


def execute(out):
    import hashlib
    root=Path(__file__).resolve().parents[2]
    sources={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'trust_network').rglob('*.py'))}
    out=Path(out);out.mkdir(parents=True,exist_ok=False);rows=[]
    for case in CASES:
        for arm,recovery in [*( (a,'bound') for a in ARMS),('dependency_closure','notice_only')]:
            raw,truth=run_case(case,arm,recovery)
            metrics=metrics_for(raw,truth);assessment=audit(raw)
            name=f'{case}__{arm}__{recovery}'
            (out/(name+'.json')).write_text(json.dumps({'trace':raw,'truth':truth,'audit':assessment},ensure_ascii=False,indent=2))
            rows.append({'case':case,'arm':arm,'recovery':recovery,**metrics})
    (out/'metrics.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    (out/'manifest.json').write_text(json.dumps({'protocol':'closure-v3-offline','proposal_origin':'scripted',
        'source_hashes':sources,'workflows':len(rows),'model_calls':0,'tokens':0,'paid_calls_authorized':False},indent=2))
    lines=['# Closure v3 offline replay','',
        'Scripted proposals; no live model calls. Root gate uses batched all-root checks and the same v3 recovery. ',
        'Recovery evidence transport is excluded from erroneous work propagation. Signed issuer status does not establish factual truth.','',
        '|Case|Arm|Recovery|Unsafe / 4|Safe / 4|Recovered|Unrelated frozen|Queries|',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"|{r['case']}|{r['arm']}|{r['recovery']}|{r['unsafe_completed']}|{r['safe_completed']}|{r['recovery_successes']}|{r['unrelated_overfreeze']}|{r['verification_queries']}|")
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True)
    execute(parser.parse_args().out)
