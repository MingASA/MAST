import copy
import json
import pytest
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from trust_network.tests.test_network_reliability import network
from trust_network.demo.claim_channel import ClaimGateway, issue
from trust_network.demo.claim_worker import handle
from trust_network.demo.documents import digest, keypair
from trust_network.demo.network_reliability import run_batch,authority_status
from trust_network.demo.reliability_recovery import (build_recovery_evidence,
    rebuild_derived_claim, replacement_offer, prepare_recovery)


def derived_network():
    owners=('buyer','supplier','carrier','coordinator','receiver')
    keys={owner:keypair() for owner in owners}
    public={owner:pair[1] for owner,pair in keys.items()}
    authorities={'invoice_authorization':'buyer','charge_manifest':'buyer',
                 'charge/goods':'supplier','charge/freight':'carrier',
                 'delivery_schedule':'carrier','total_charge':'coordinator'}
    nodes={owner:ClaimGateway(owner,keys[owner][0],public,'w',authorities)
           for owner in owners}

    def source(owner,predicate,value):
        packet=issue(owner,keys[owner][0],{'kind':'claim','workflow':'w','parents':[],
            'fact':{'predicate':predicate,'value':value}})
        nodes[owner].receive(packet)
        return packet

    packets=[
        source('buyer','charge_manifest',
               {'order':'A','currency':'CNY','components':['goods','freight']}),
        source('buyer','invoice_authorization',
               {'order':'A','operation':'approve_invoice','currency':'CNY',
                'maximum_cents':11000,'approved':True}),
        source('supplier','charge/goods',
               {'order':'A','currency':'CNY','component':'goods','cents':10000}),
        source('carrier','charge/freight',
               {'order':'A','currency':'CNY','component':'freight','cents':700}),
        source('carrier','delivery_schedule',
               {'order':'A','currency':'CNY','window':'2026-10-01/2026-10-03',
                'reference_only':True}),
    ]
    for packet in packets:
        nodes['coordinator'].receive(packet)
        nodes['receiver'].receive(packet)
    ids=[digest(packet) for packet in packets]
    total=issue('coordinator',keys['coordinator'][0],{
        'kind':'claim','workflow':'w','parents':[ids[0],ids[2],ids[3]],
        'fact':{'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':10700}},
        'rule':'sum_charges'})
    nodes['coordinator'].receive(total)
    nodes['receiver'].receive(total)
    return nodes,keys,packets,total


def test_recovery_requires_new_proposal_and_keeps_revocation():
    nodes,claims,_=network(); receiver=nodes['receiver']; buyer=nodes['buyer']
    original=buyer.claims[claims[0]]
    revoke=issue('buyer',buyer.key,{'kind':'revoke','workflow':'w','target':claims[0],'original':original})
    buyer.receive(revoke); receiver.receive(revoke)
    proposals=[{'id':'invoice','operation':'approve_invoice','order':'A','claims':claims}]
    effects=[]
    invoke=lambda o,q:authority_status(nodes[o],q)
    blocked=run_batch(receiver,proposals,invoke,lambda p:effects.append(p['id']))
    new=copy.deepcopy(original['body']); new['fact']['value']['maximum_cents']=300
    packet=issue('buyer',buyer.key,new); buyer.receive(packet)
    offer=replacement_offer(buyer,claims[0],packet)
    envelope=prepare_recovery(receiver,blocked,[offer])['body']
    assert not envelope['action_authorized'] and not effects
    assert claims[0] in receiver.revoked and envelope['tasks'][0]['requires_new_model_decision']
    assert run_batch(receiver,proposals,invoke,lambda p:effects.append('old'))['body']['outputs'][0]['action']=='REQUEST_EVIDENCE'
    new_proposal=[dict(proposals[0],claims=[digest(packet),claims[1]])]
    assert run_batch(receiver,new_proposal,invoke,lambda p:effects.append('new'))['body']['outputs'][0]['action']=='COMPLETED'
    assert effects==['new']


def test_invalid_offer_set_is_atomic_and_cross_order_rejected():
    nodes,claims,_=network(); receiver=nodes['receiver']; buyer=nodes['buyer']
    p=[{'id':'invoice','operation':'approve_invoice','order':'A','claims':claims}]
    batch=run_batch(receiver,p,lambda o,q:authority_status(nodes[o],q),lambda p:None,verification_budget=0)
    value=copy.deepcopy(buyer.claims[claims[0]]['body']); value['fact']['value']['maximum_cents']=300
    packet=issue('buyer',buyer.key,value); offer=replacement_offer(buyer,claims[0],packet)
    before=list(receiver.claims); events=len(receiver.events)
    with pytest.raises(ValueError,match='duplicate'):
        prepare_recovery(receiver,batch,[offer,offer])
    assert list(receiver.claims)==before and len(receiver.events)==events
    value['fact']['value']['order']='another-order'
    with pytest.raises(ValueError,match='scope'):
        replacement_offer(buyer,claims[0],issue('buyer',buyer.key,value))


def test_effect_value_error_is_unknown_and_never_auto_retried():
    nodes,claims,_=network(); receiver=nodes['receiver']; effects=[]
    p=[{'id':'invoice','operation':'approve_invoice','order':'A','claims':claims}]
    def effect(proposal):
        effects.append(proposal['id'])
        raise ValueError('effect happened but adapter failed to decode receipt')
    report=run_batch(receiver,p,lambda o,q:authority_status(nodes[o],q),effect)
    assert effects==['invoice'] and report['body']['outputs'][0]['action']=='EFFECT_UNKNOWN'
    envelope=prepare_recovery(receiver,report,[])['body']
    assert envelope['tasks']==[] and envelope['excluded_proposals']==['invoice']


def test_recovery_rebuilds_derived_claim_then_requires_fresh_action_proposal(tmp_path):
    nodes,keys,packets,old_total=derived_network()
    carrier=nodes['carrier']; coordinator=nodes['coordinator']; receiver=nodes['receiver']
    old_freight=digest(packets[3]); authorization=digest(packets[1])
    revoke=issue('carrier',keys['carrier'][0],{'kind':'revoke','workflow':'w',
        'target':old_freight,'original':carrier.claims[old_freight]})
    carrier.receive(revoke); coordinator.receive(revoke); receiver.receive(revoke)
    proposal=[{'id':'invoice','operation':'approve_invoice','order':'A',
               'claims':[authorization,digest(old_total)]}]
    effects=[]
    blocked=run_batch(receiver,proposal,lambda owner,query:authority_status(nodes[owner],query),
                      lambda item:effects.append(item['id']))
    assert blocked['body']['outputs'][0]['action']=='REQUEST_EVIDENCE'
    new_fact={'predicate':'charge/freight','value':{'order':'A','currency':'CNY',
        'component':'freight','cents':900}}
    new_source=issue('carrier',keys['carrier'][0],{'kind':'claim','workflow':'w',
        'parents':[],'fact':new_fact})
    carrier.receive(new_source)
    offer=replacement_offer(carrier,old_freight,new_source)
    envelope=prepare_recovery(receiver,blocked,[offer])
    task=envelope['body']['tasks'][0]
    registration=coordinator.receive(new_source)
    evidence=build_recovery_evidence(coordinator,envelope,task,offer,
                                     registration,new_source)
    tampered=copy.deepcopy(evidence)
    tampered['signed_artifacts']['coordinator_registration']['body']['target']='wrong'
    with pytest.raises(ValueError):
        rebuild_derived_claim(coordinator,envelope,task,
            {'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':10900}},
            'sum_charges',tampered)
    worker_dir=tmp_path/'coordinator'
    worker_dir.mkdir(mode=0o700)
    (worker_dir/'config.json').write_text(json.dumps({
        'owner':'coordinator','public_keys':coordinator.public,'workflow':'w',
        'authorities':coordinator.authorities}))
    (worker_dir/'private.md').write_text('offline coordinator')
    (worker_dir/'signing.key').write_bytes(keys['coordinator'][0].private_bytes(
        Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
    (worker_dir/'channel_state.json').write_text(json.dumps({
        'claims':coordinator.claims,'revoked':coordinator.revoked,
        'events':coordinator.events}))
    worker_response=handle(worker_dir,{
        'operation':'reliability_rebuild_derived','envelope':envelope,'task':task,
        'fact':{'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':10900}},
        'rule':'sum_charges','evidence':evidence},tmp_path/'unused.env')
    rebuilt=worker_response['packet']
    saved=json.loads((worker_dir/'channel_state.json').read_text())
    coordinator.claims=saved['claims']; coordinator.revoked=saved['revoked']; coordinator.events=saved['events']
    new_total=digest(rebuilt)
    assert task['rebuild_required'][0]['replacement_parents']==[
        digest(packets[0]),digest(packets[2]),digest(new_source)]
    assert digest(old_total) in coordinator.claims
    assert coordinator.blockers(digest(old_total))==[old_freight]
    assert coordinator.blockers(new_total)==[]
    assert any(e['body']['action']=='derived_claim_rebuilt' for e in coordinator.events)
    assert receiver.receive(rebuilt)['body']['action']=='received'
    recovered=[{'id':'invoice','operation':'approve_invoice','order':'A',
                'claims':[authorization,new_total]}]
    result=run_batch(receiver,recovered,lambda owner,query:authority_status(nodes[owner],query),
                     lambda item:effects.append('recovered'))
    assert result['body']['outputs'][0]['action']=='COMPLETED'
    assert effects==['recovered']


def test_recovery_rebuild_rejects_bad_fact_without_partial_write():
    nodes,keys,packets,old_total=derived_network()
    carrier=nodes['carrier']; coordinator=nodes['coordinator']; receiver=nodes['receiver']
    old_freight=digest(packets[3]); authorization=digest(packets[1])
    revoke=issue('carrier',keys['carrier'][0],{'kind':'revoke','workflow':'w',
        'target':old_freight,'original':carrier.claims[old_freight]})
    carrier.receive(revoke); coordinator.receive(revoke); receiver.receive(revoke)
    proposal=[{'id':'invoice','operation':'approve_invoice','order':'A',
               'claims':[authorization,digest(old_total)]}]
    blocked=run_batch(receiver,proposal,lambda owner,query:authority_status(nodes[owner],query),
                      lambda item:None)
    new_source=issue('carrier',keys['carrier'][0],{'kind':'claim','workflow':'w',
        'parents':[],'fact':{'predicate':'charge/freight','value':{
            'order':'A','currency':'CNY','component':'freight','cents':900}}})
    carrier.receive(new_source)
    offer=replacement_offer(carrier,old_freight,new_source)
    envelope=prepare_recovery(receiver,blocked,[offer])
    registration=coordinator.receive(new_source)
    evidence=build_recovery_evidence(coordinator,envelope,envelope['body']['tasks'][0],
                                     offer,registration,new_source)
    before_claims=copy.deepcopy(coordinator.claims); before_events=len(coordinator.events)
    with pytest.raises(ValueError,match='violates rule'):
        rebuild_derived_claim(coordinator,envelope,envelope['body']['tasks'][0],
            {'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':10901}},
            'sum_charges',evidence)
    assert coordinator.claims==before_claims
    assert len(coordinator.events)==before_events
