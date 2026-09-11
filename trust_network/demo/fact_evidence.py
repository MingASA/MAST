"""Narrow settlement-basis attestations; not arbitrary factual truth.

Only attest reads an authority's registry. The gate consumes signed public
answers and owner-local claims. No affirmative cache or implicit execution.
"""
import math
import secrets
import time
from trust_network.demo.claim_channel import issue,read
from trust_network.demo.documents import digest

SCOPE='settlement_basis_v1'


def scope_key(workflow,fact):
    value=fact.get('value',{})
    if (fact.get('predicate')!='total_charge' or set(value)!={'order','currency','cents'} or
            not isinstance(value['order'],str) or not isinstance(value['currency'],str) or
            type(value['cents']) is not int or value['cents']<0):
        raise ValueError('unsupported settlement assertion')
    return digest([workflow,'total_charge',value['order'],value['currency']])


def validate_config(config,public):
    if config.get('policy') not in ('closure_only','conflict_triggered','verify_all','selective'):
        raise ValueError('unknown fact policy')
    if config.get('authority') not in public:raise ValueError('unknown fact authority')
    for name,default in [('forward_loss',1),('query_cost',1),('threshold',2)]:
        value=config.get(name,default)
        if type(value) not in (int,float) or not math.isfinite(value) or value<0 or (name=='query_cost' and value==0):
            raise ValueError('invalid fact scheduling cost')


def targets(gateway,proposal,config):
    from trust_network.demo.network_reliability import ancestors
    validate_config(config,gateway.public)
    nodes=set().union(*(ancestors(gateway,c) for c in proposal['claims']))
    relevant=sorted(c for c in nodes if c in gateway.claims and
                    gateway.claims[c]['body']['fact'].get('predicate')=='total_charge')
    conflicts=set()
    for c in relevant:
        fact=gateway.claims[c]['body']['fact'];key=scope_key(gateway.workflow,fact)
        for other,p in gateway.claims.items():
            f=p['body']['fact']
            if f.get('predicate')=='total_charge' and not gateway.blockers(other) and scope_key(gateway.workflow,f)==key and f!=fact:
                conflicts.add(c)
    mandatory=proposal.get('intent')=='verify' or proposal['operation']=='approve_invoice'
    policy=config['policy']
    selected=[]
    for c in relevant:
        disputed=c in gateway.fact_disputes
        required=(proposal.get('intent')=='verify' or disputed or
            policy=='verify_all' or
            policy in ('selective','conflict_triggered') and c in conflicts or
            policy=='selective' and (mandatory or config.get('forward_loss',1)/config.get('query_cost',1)>=config.get('threshold',2)))
        if required:selected.append(c)
    return selected,sorted(conflicts)


def attest(gateway,registry,wire,now=None):
    now=time.time() if now is None else now
    requester,q=read(wire['request'],gateway.public)
    if (wire.get('kind')!='fact_evidence_query' or q.get('scope')!=SCOPE or q.get('workflow')!=gateway.workflow or
            q.get('requester')!=requester or q.get('authority')!=gateway.owner or not q.get('nonce') or not q.get('batch')):
        raise ValueError('invalid fact query binding')
    _,body=read(q['claim'],gateway.public)
    if body.get('kind')!='claim' or body.get('workflow')!=gateway.workflow or digest(q['claim'])!=q['claim_id']:
        raise ValueError('wrong query claim')
    key=scope_key(gateway.workflow,body['fact']);entry=registry.get(key)
    status='UNKNOWN';version=None
    if (isinstance(entry,dict) and entry.get('status')=='confirmed' and
            type(entry.get('cents')) is int and entry['cents']>=0 and isinstance(entry.get('version'),str)):
        status='CONFIRMED' if entry['cents']==body['fact']['value']['cents'] else 'CONTRADICTED'
        version=entry['version']
    result=issue(gateway.owner,gateway.key,{'kind':'fact_evidence_reply','scope':SCOPE,'request':wire['request'],
        'status':status,'registry_version':version,'issued_at':now,'expires_at':now+300})
    gateway.record('fact_evidence_replied',q['claim_id'],[digest(result),status])
    return result


def inspect(packet,wire,public,authority,now):
    owner,b=read(packet,public)
    if (owner!=authority or b.get('kind')!='fact_evidence_reply' or b.get('scope')!=SCOPE or digest(b.get('request'))!=digest(wire['request']) or
            b.get('status') not in ('CONFIRMED','CONTRADICTED','UNKNOWN')):
        raise ValueError('unbound fact reply')
    start=b.get('issued_at');end=b.get('expires_at')
    if (type(start) not in (int,float) or type(end) not in (int,float) or
            not math.isfinite(start) or not math.isfinite(end) or not start<=now<end or end-start>300):
        raise ValueError('stale fact evidence')
    if b['status']!='UNKNOWN' and not isinstance(b.get('registry_version'),str):raise ValueError('missing registry version')
    return b['status']


def check(gateway,proposal,batch,config,query):
    selected,conflicts=targets(gateway,proposal,config)
    if gateway.fact_authorities.get(SCOPE)!=config['authority']:raise ValueError('fact policy authority not trusted')
    exchanges=[];action='PASS'
    for cid in selected:
        request=issue(gateway.owner,gateway.key,{'scope':SCOPE,'workflow':gateway.workflow,
            'requester':gateway.owner,'authority':config['authority'],'batch':batch,
            'proposal':digest(proposal),'nonce':secrets.token_hex(24),'claim_id':cid,'claim':gateway.claims[cid]})
        wire={'kind':'fact_evidence_query','request':request};packet=None;status='UNAVAILABLE'
        try:
            packet=query(config['authority'],wire);checked_at=time.time()
            status=inspect(packet,wire,gateway.public,config['authority'],checked_at)
        except Exception:
            checked_at=time.time()
        # A contradictory old artifact is never silently rehabilitated. A new
        # issuer-signed artifact/recovery graph must be submitted instead.
        if status=='CONTRADICTED':
            from trust_network.demo.dispute_protocol import register_dispute
            register_dispute(gateway,packet)
        if cid in gateway.fact_disputes or status!='CONFIRMED':action='REQUEST_EVIDENCE'
        exchanges.append({'claim_id':cid,'query':wire,'reply':packet,'checked_at':checked_at,'status':status})
        gateway.record('fact_evidence_received',cid,[digest(packet) if packet else '',status])
    return {'proposal':digest(proposal),'selected':selected,'conflicts':conflicts,'exchanges':exchanges,
            'action':action,'disputed':sorted(c for c in selected if c in gateway.fact_disputes)}


def audit_checks(gateway,body,signed_plan,fact_authorities=None):
    config=signed_plan.get('fact_config')
    if config is None:
        if 'fact_checks' in body:raise ValueError('undeclared fact policy')
        return
    validate_config(config,gateway.public)
    if (fact_authorities or {}).get(SCOPE)!=config['authority']:raise ValueError('fact authority not independently trusted')
    for cid,proof in body['evidence'].get('fact_disputes',{}).items():
        _,b=read(proof,gateway.public);request=b['request'];_,q=read(request,gateway.public)
        if (q['claim_id']!=cid or q['workflow']!=gateway.workflow or digest(q['claim'])!=cid or
                inspect(proof,{'request':request},gateway.public,config['authority'],b['issued_at'])!='CONTRADICTED'):
            raise ValueError('unproven dispute')
        gateway.fact_disputes[cid]=proof
    proposals={p['id']:p for p in signed_plan['proposals']};checks=body.get('fact_checks',{})
    if set(checks)-set(proposals):raise ValueError('foreign fact check')
    if body.get('fact_verification_calls')!=sum(len(c['exchanges']) for c in checks.values()):raise ValueError('fact count mismatch')
    for pid,check_result in checks.items():
        p=proposals[pid];selected,conflicts=targets(gateway,p,config)
        if check_result['proposal']!=digest(p) or check_result['selected']!=selected or check_result['conflicts']!=conflicts:
            raise ValueError('fact schedule mismatch')
        if [e['claim_id'] for e in check_result['exchanges']]!=selected:raise ValueError('missing fact exchange')
        action='PASS'
        for e in check_result['exchanges']:
            wire=e['query'];requester,q=read(wire['request'],gateway.public)
            if (wire.get('kind')!='fact_evidence_query' or q.get('requester')!=requester or requester!=body['plan']['signature']['issuer'] or
                    q.get('scope')!=SCOPE or q.get('workflow')!=gateway.workflow or q.get('authority')!=config['authority'] or
                    q.get('batch')!=digest(body['plan']) or q.get('proposal')!=digest(p) or not q.get('nonce') or
                    q.get('claim_id')!=e['claim_id'] or digest(q.get('claim'))!=digest(gateway.claims[e['claim_id']])):
                raise ValueError('fact request scope mismatch')
            status='UNAVAILABLE'
            try:status=inspect(e['reply'],wire,gateway.public,config['authority'],e['checked_at'])
            except (ValueError,KeyError,TypeError):pass
            if status!=e['status']:raise ValueError('unproven fact observation')
            if status=='CONTRADICTED':gateway.fact_disputes[e['claim_id']]=e['reply']
            if status!='CONFIRMED' or e['claim_id'] in gateway.fact_disputes:action='REQUEST_EVIDENCE'
        if check_result['action']!=action or check_result['disputed']!=sorted(c for c in selected if c in gateway.fact_disputes):
            raise ValueError('fact decision mismatch')
    for output in body['outputs']:
        if output['action'] in ('COMPLETED','VERIFIED') and (output['proposal'] not in checks or checks[output['proposal']]['action']!='PASS'):
            raise ValueError('execution bypassed fact gate')
