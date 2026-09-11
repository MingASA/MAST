import copy
import pytest
from trust_network.benchmark.dispute_lifecycle import run
from trust_network.benchmark.workflow.backend import MemoryBackend
from trust_network.benchmark.workflow.spec import workload,ARMS,OWNERS
from trust_network.demo.dispute_protocol import register_dispute,accept_dispute,acknowledge_dispute,propose_revision
from trust_network.demo.notification_pump import pump_notifications
from trust_network.demo.claim_channel import issue
from trust_network.demo.documents import digest


def test_multi_hop_dispute_freezes_only_A_and_confirmed_recovery_completes():
    metrics,log,b=run()
    assert metrics['notifications']['acknowledged']==4
    assert metrics['A_blocked']=={'a':'REQUEST_EVIDENCE','b':'REQUEST_EVIDENCE'}
    assert metrics['C_continues']==metrics['A_recovered']=={'a':'COMPLETED','b':'COMPLETED'}
    assert all(a['registration_proven'] for a in metrics['notice_audits'])
    # Receivers retain both negative evidence and old issuer revocation; repaired
    # descendants use fresh IDs, never a blanket removal of historical state.
    root=digest(workload()['roots']['A'])
    assert all(root in b.nodes[o].fact_disputes for o in ('coordinator','middle_a','middle_b','receiver_a','receiver_b'))
    assert root in b.nodes['source'].revoked
    notice=next(r['request']['packet'] for r in log if r['request']['operation']=='reliability_notification_accept')
    owner=notice['body']['recipient'];receiver=b.nodes[owner]
    first=accept_dispute(receiver,notice);before=receiver.snapshot()
    assert accept_dispute(receiver,notice)==first and receiver.snapshot()==before


def test_untrusted_scope_route_and_ack_cannot_freeze_another_branch():
    _,log,b=run();f=workload()
    notice=next(r['request']['packet'] for r in log if r['request']['operation']=='reliability_notification_accept')
    receiver=b.nodes[notice['body']['recipient']]
    body=copy.deepcopy(notice['body']);body['target']=digest(f['roots']['C'])
    with pytest.raises(ValueError):accept_dispute(receiver,issue('coordinator',f['keys']['coordinator'],body))
    proof=notice['body']['proof'];bad=copy.deepcopy(proof['body']);bad['status']='UNKNOWN'
    with pytest.raises(ValueError):register_dispute(receiver,issue('buyer',f['keys']['buyer'],bad))
    other=MemoryBackend(f,ARMS['dependency']).nodes['middle_a'];other.fact_authorities={}
    with pytest.raises(ValueError):register_dispute(other,proof)
    ack=accept_dispute(receiver,notice);forged=copy.deepcopy(ack['body']);forged['target']=digest(f['roots']['C'])
    with pytest.raises(ValueError):acknowledge_dispute(b.nodes['coordinator'],issue(receiver.owner,receiver.key,forged))


def test_revision_requires_original_issuer_confirmation_and_no_partial_commit():
    _,log,b=run();f=workload()
    proof=next(r['request']['packet']['body']['proof'] for r in log if r['request']['operation']=='reliability_notification_accept')
    fresh=MemoryBackend(f,ARMS['dependency'])
    for g in fresh.nodes.values():g.receive(f['roots']['A'])
    root=digest(f['roots']['A']);fact=f['roots']['A']['body']['fact']
    with pytest.raises(ValueError):propose_revision(fresh.nodes['middle_a'],proof,fact,lambda *args:None)
    source=fresh.nodes['source'];register_dispute(source,proof);before=source.snapshot()
    with pytest.raises((TypeError,ValueError)):propose_revision(source,proof,fact,lambda *args:None)
    assert source.snapshot()==before and root not in source.revoked
    offer=next(r['response']['offer'] for r in log if r['request']['operation']=='reliability_dispute_revision')
    from trust_network.demo.recovery_closure import validate_offer
    stripped={k:v for k,v in offer['body'].items() if k!='fact_resolution'}
    with pytest.raises(ValueError):validate_offer(source,issue('source',source.key,stripped))
    bad=copy.deepcopy(offer['body']);bad['fact_resolution']['query']['request']['body']['nonce']='wrong'
    with pytest.raises(ValueError):validate_offer(source,issue('source',source.key,bad))
