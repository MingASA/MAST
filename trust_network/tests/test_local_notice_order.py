import copy
from trust_network.benchmark.containment import fixture,run
from trust_network.benchmark.accountability import audit
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.documents import digest


def case(binding=True,notified='receiver_a',missing=False):
    f=fixture('active');raw=run(f,'unmediated');owner='receiver_a'
    target=digest(f['trace']['A']['coordinator']);child=digest(f['trace']['A']['middle_a'])
    g=ClaimGateway(notified,f['keys'][notified],f['public'],f['workflow'],{})
    revoke=issue('coordinator',f['keys']['coordinator'],{'kind':'revoke','workflow':f['workflow'],
        'target':target,'original':f['trace']['A']['coordinator']})
    notice=g.receive(revoke);middle=g.record('other_local_event',target)
    def append(kind,**fields):
        raw['events'].append({'kind':kind,'tick':100,'sequence':len(raw['events']),
            'previous':digest(raw['events'][-1]),**fields})
    append('notice',owner=notified,root=target,receipt=notice)
    proposal={'id':'faulty','operation':'forward','claims':[child]}
    use=issue(owner,f['keys'][owner],{'kind':'benchmark_use','workflow':f['workflow'],
        'proposal':proposal,'action':'COMPLETED','local_head':digest(middle) if binding else None})
    append('gate',owner=owner,outcome={'action':'COMPLETED','use_receipt':use,
        'gateway_events':[middle] if not missing and notified==owner else []})
    return raw,target


def test_middle_notice_is_found_in_full_dependency_graph():
    raw,target=case();finding=audit(raw)['findings'][-1]
    assert finding['classification']=='use_after_own_notice'
    assert finding['notified_claims']==[target] and finding['notified_roots']==[]
    assert finding['causal_legal_blame']=='undetermined'


def test_transport_order_alone_other_organization_and_missing_chain_do_not_prove_fault():
    for kwargs in ({'binding':False},{'notified':'receiver_b'},{'missing':True}):
        raw,_=case(**kwargs)
        assert audit(raw)['findings'][-1]['classification']=='no_proven_notice_violation'
