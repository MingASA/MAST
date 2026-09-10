import copy
import json
import pytest
from trust_network.benchmark.containment import fixture,AUTHORITIES
from trust_network.demo.claim_channel import ClaimGateway,issue
from trust_network.demo.documents import digest
from trust_network.demo.network_reliability import run_batch,ReliabilityConfig
from trust_network.demo.propagation_notice import (prepare_handoff,accept_handoff,acknowledge_handoff,
    pending_notifications,accept_notice,acknowledge_notice,audit_notification_exchange)


def network():
    f=fixture('active');nodes={o:ClaimGateway(o,f['keys'][o],f['public'],f['workflow'],AUTHORITIES) for o in f['keys']}
    for packet in f['roots'].values():nodes['source'].receive(packet)
    return f,nodes


def deliver(nodes,sender,receiver,claims,ack=True):
    packet=prepare_handoff(nodes[sender],receiver,claims)
    receipt=accept_handoff(nodes[receiver],packet)
    if ack:acknowledge_handoff(nodes[sender],receipt)
    return packet,receipt


def retract(g,target):
    packet=issue(g.owner,g.key,{'kind':'revoke','workflow':g.workflow,'target':target,'original':g.claims[target]})
    g.receive(packet);return packet


def drain(nodes):
    transmitted=[]
    for _ in range(20):
        pending=[(owner,p) for owner,g in nodes.items() for p in pending_notifications(g)]
        if not pending:return transmitted
        for owner,packet in pending:
            receiver=packet['body']['recipient'];receipt=accept_notice(nodes[receiver],packet)
            acknowledge_notice(nodes[owner],receipt);transmitted.append((packet,receipt))
    pytest.fail('notification relay did not terminate')


def test_shared_retraction_pushes_to_two_branches_preserving_unrelated_claims():
    f,nodes=network()
    for order in ('A','C'):
        deliver(nodes,'source','coordinator',[digest(f['roots'][order])])
        nodes['coordinator'].receive(f['trace'][order]['coordinator'])
    for branch in ('a','b'):
        for order in ('A','C'):
            middle='middle_'+branch;receiver='receiver_'+branch
            deliver(nodes,'coordinator',middle,[digest(f['trace'][order]['coordinator'])],ack=False)
            nodes[middle].receive(f['trace'][order][middle])
            deliver(nodes,middle,receiver,[digest(f['trace'][order][middle])])
    old=digest(f['trace']['A']['coordinator']);retract(nodes['coordinator'],old)
    exchanges=drain(nodes)
    assert len(exchanges)==4  # two direct peers, then each peer's receiver
    for notice,receipt in exchanges:
        assert notice['body']['revocation']['signature']['issuer']=='coordinator'
        assert all(old in {digest(p) for p in h['body']['evidence']} for h in notice['body']['handoffs'])
        assert audit_notification_exchange(notice,receipt,f['public'],AUTHORITIES)['registration_proven']
    for branch in ('a','b'):
        g=nodes['receiver_'+branch];bad=digest(f['trace']['A']['middle_'+branch]);good=digest(f['trace']['C']['middle_'+branch])
        assert g.blockers(bad)==[old] and not g.blockers(good)
        effects=[]
        packet=run_batch(g,[{'id':'bad','operation':'forward','claims':[bad]},
                           {'id':'good','operation':'forward','claims':[good]}],
            lambda *args:pytest.fail('push control must not require polling'),lambda p:effects.append(p['id']),ReliabilityConfig('autonomous'))
        assert effects==['good'] and packet['body']['outputs'][0]['action']=='REQUEST_EVIDENCE'
    assert old not in nodes['source'].revoked  # no global broadcast or upstream state access


def test_notice_before_handoff_and_duplicate_delivery_are_monotone():
    f,nodes=network();source=nodes['source'];receiver=nodes['coordinator'];root=digest(f['roots']['A'])
    handoff=prepare_handoff(source,receiver.owner,[root]);retract(source,root)
    notice=pending_notifications(source)[0];receipt=accept_notice(receiver,notice)
    count=len(receiver.events)
    assert accept_notice(receiver,notice)==receipt and len(receiver.events)==count
    ack=accept_handoff(receiver,handoff)
    assert ack['body']['status']=='blocked' and receiver.blockers(root)==[root]
    assert accept_handoff(receiver,handoff)==ack
    acknowledge_notice(source,receipt);assert not pending_notifications(source)
    # An old accepted receipt or a duplicate cannot clear monotone revocation.
    assert receiver.blockers(root)==[root]


def test_restart_preserves_routes_pending_outbox_and_receipt_deduplication():
    f,nodes=network();root=digest(f['roots']['A'])
    deliver(nodes,'source','coordinator',[root],ack=False)
    g=nodes['source'];retract(g,root)
    saved=json.loads(json.dumps(g.snapshot()))
    restarted=ClaimGateway(g.owner,g.key,g.public,g.workflow,g.authorities);restarted.restore(saved)
    assert digest(pending_notifications(restarted))==digest(pending_notifications(g))
    packet=pending_notifications(restarted)[0];ack=accept_notice(nodes['coordinator'],packet)
    acknowledge_notice(restarted,ack)
    saved=restarted.snapshot();restarted.restore(saved)
    assert not pending_notifications(restarted)
    legacy=ClaimGateway(g.owner,g.key,g.public,g.workflow,g.authorities)
    legacy.restore({'claims':{},'revoked':{},'events':[]})
    assert not legacy.handoffs and not pending_notifications(legacy)


def test_cycle_terminates_without_broadcast_or_repeat_storm():
    f,nodes=network();root=digest(f['roots']['A'])
    deliver(nodes,'source','coordinator',[root]);coord=f['trace']['A']['coordinator']
    nodes['coordinator'].receive(coord);deliver(nodes,'coordinator','source',[digest(coord)])
    retract(nodes['source'],root)
    assert len(drain(nodes))==2


def test_wrong_target_recipient_and_receipt_rejected_without_state_changes():
    f,nodes=network();root=digest(f['roots']['A'])
    deliver(nodes,'source','coordinator',[root]);retract(nodes['source'],root)
    notice=pending_notifications(nodes['source'])[0];receiver=nodes['coordinator']
    before=receiver.snapshot()
    wrong=copy.deepcopy(notice['body']);wrong['target']=digest(f['roots']['C'])
    with pytest.raises(ValueError):accept_notice(receiver,issue('source',nodes['source'].key,wrong))
    with pytest.raises(ValueError):accept_notice(nodes['middle_a'],notice)
    assert receiver.snapshot()==before
    receipt=accept_notice(receiver,notice);wrong=copy.deepcopy(receipt['body']);wrong['notice']='another-notice'
    with pytest.raises(ValueError):acknowledge_notice(nodes['source'],issue(receiver.owner,receiver.key,wrong))
    assert pending_notifications(nodes['source'])
    assert audit_notification_exchange(notice,None,f['public'],AUTHORITIES)['omission_fault']=='undetermined'


def test_worker_handoff_and_persistent_notification_operations(tmp_path):
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
    from trust_network.demo.claim_worker import handle
    f,nodes=network()
    def save(owner):
        g=nodes[owner];directory=tmp_path/owner;directory.mkdir()
        (directory/'config.json').write_text(json.dumps({'owner':owner,'workflow':g.workflow,
            'public_keys':g.public,'authorities':g.authorities,'reliability':{'policy':'autonomous'}}))
        (directory/'signing.key').write_bytes(g.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
        (directory/'channel_state.json').write_text(json.dumps(g.snapshot()))
        return directory
    source=save('source');receiver=save('coordinator');root=digest(f['roots']['A'])
    def invoke(directory,operation,**kwargs):return handle(directory,{'operation':operation,**kwargs},tmp_path/'unused.env')
    from trust_network.demo.notification_pump import guarded_handoff
    def call(owner,request,sender=None):
        return handle({'source':source,'coordinator':receiver}[owner],request,tmp_path/'unused.env')
    delivery=guarded_handoff(call,'source','coordinator',[root],'transfer')
    assert delivery['status']=='RECEIVED' and delivery['action_authorized'] is False
    invoke(source,'reliability_revoke',target=root)
    notice=invoke(source,'reliability_notifications')['pending'][0]
    receipt=invoke(receiver,'reliability_notification_accept',packet=notice)['result']
    invoke(source,'reliability_notification_ack',packet=receipt)
    assert not invoke(source,'reliability_notifications')['pending']
    assert root in json.loads((receiver/'channel_state.json').read_text())['revoked']
    # The exact entrypoint refuses to publish a new handoff after local revoke.
    blocked=invoke(source,'reliability_handoff_prepare',id='again',recipient='coordinator',claims=[root])['batch']
    assert blocked['body']['outputs'][0]['action']=='REQUEST_EVIDENCE'


def test_bounded_pump_retries_after_lost_ack_without_reprocessing_notice():
    from trust_network.demo.notification_pump import pump_notifications
    f,nodes=network();root=digest(f['roots']['A'])
    deliver(nodes,'source','coordinator',[root]);retract(nodes['source'],root)
    lose_ack=[True]
    def call(owner,request,sender=None):
        g=nodes[owner];op=request['operation']
        if op=='reliability_notifications':return {'pending':pending_notifications(g)}
        if op=='reliability_notification_accept':return {'result':accept_notice(g,request['packet'])}
        if op=='reliability_notification_ack':
            if lose_ack.pop() if lose_ack else False:raise TimeoutError('simulated lost ACK')
            return {'result':acknowledge_notice(g,request['packet'])}
        pytest.fail('unexpected operation')
    first=pump_notifications(call,('source','coordinator'),max_deliveries=1)
    assert first['delivery_attempts']==1 and first['acknowledged']==0
    count=len(nodes['coordinator'].events)
    second=pump_notifications(call,('source','coordinator'),max_deliveries=1)
    assert second['acknowledged']==1 and not pending_notifications(nodes['source'])
    assert len(nodes['coordinator'].events)==count


def test_failed_evidence_transaction_does_not_leak_notification_outbox():
    from trust_network.demo.network_reliability import apply_status_evidence
    f,nodes=network();g=nodes['coordinator'];root=digest(f['roots']['A'])
    deliver(nodes,'source','coordinator',[root]);g.receive(f['trace']['A']['coordinator'])
    target=digest(f['trace']['A']['coordinator'])
    prepare_handoff(g,'middle_a',[target])
    valid=issue(g.owner,g.key,{'kind':'revoke','workflow':g.workflow,'target':target,'original':g.claims[target]})
    invalid=issue('source',nodes['source'].key,{'kind':'revoke','workflow':g.workflow,'target':root,'original':f['roots']['C']})
    before=g.snapshot()
    with pytest.raises(ValueError):
        apply_status_evidence(g,{'query':{'root':target},'status':'revoked',
            'revocation':valid,'dependency_revocations':[invalid]})
    assert g.snapshot()==before and not pending_notifications(g)
