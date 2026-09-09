import copy
import pytest

from trust_network.demo.claim_channel import ClaimGateway, issue
from trust_network.demo.documents import digest, keypair
from trust_network.demo.reliability_accountability import (append_event,
    audit_accountability,verify_event_chain)


def test_controller_event_chain_detects_tampering():
    events=[]
    append_event(events,{'kind':'start','workflow':'w'})
    append_event(events,{'kind':'claim_delivery','packet_digest':'x','receiver':'r'})
    assert verify_event_chain(events)=={
        'valid':True,'events':2,'root':events[-1]['event_hash']}
    tampered=copy.deepcopy(events); tampered[1]['receiver']='other'
    with pytest.raises(ValueError,match='event hash'):
        verify_event_chain(tampered)


def test_accountability_reports_provenance_and_use_without_notice():
    authority_key,authority_public=keypair()
    receiver_key,receiver_public=keypair()
    public={'authority':authority_public,'receiver':receiver_public}
    gateway=ClaimGateway('receiver',receiver_key,public,'w',{'price':'authority'})
    source=issue('authority',authority_key,{'kind':'claim','workflow':'w','parents':[],
        'fact':{'predicate':'price','value':{'order':'A','currency':'CNY','cents':100}}})
    source_id=digest(source)
    receive_event=gateway.receive(source)
    events=[]
    append_event(events,{'kind':'start','workflow':'w'})
    append_event(events,{'kind':'worker_exchange','owner':'receiver','sender':'authority',
        'operation':'receive','request':{'operation':'receive','packet':source},
        'response':{'event':receive_event}})
    append_event(events,{'kind':'claim_delivery','sender':'authority','receiver':'receiver',
        'packet_digest':source_id,'packet_kind':'claim','action':'received','path_length':1})
    append_event(events,{'kind':'controlled_event','target':source_id,
        'type':'controlled_revocation','delivered_to':[]})
    append_event(events,{'kind':'worker_exchange','owner':'receiver','sender':'runtime',
        'operation':'reliability_batch','request':{'stage':'initial'},'response':{}})
    run_record={'batches':[{'stage':'initial','proposals':[{'id':'invoice','claims':[source_id]}],
                            'outputs':[{'proposal':'invoice','action':'COMPLETED'}]}]}
    result=audit_accountability(run_record,events,
        {'public_keys':public},{'old_root':source_id})
    assert result['event_chain']['valid']
    assert result['source']['issuer']=='authority'
    assert result['source']['formal_delivery_orgs']==['receiver']
    assert result['action_uses']['completed_after_controlled_change_without_notice']
    assert result['findings'][0]['classification']=='used_after_controlled_change_without_recorded_notice'
    assert result['responsibility']['status']=='undetermined'


def test_authority_local_revocation_receipt_is_not_consumer_notice():
    authority_key,authority_public=keypair()
    carrier_key,carrier_public=keypair()
    receiver_key,receiver_public=keypair()
    public={'authority':authority_public,'carrier':carrier_public,'receiver':receiver_public}
    source=issue('authority',authority_key,{'kind':'claim','workflow':'w','parents':[],
        'fact':{'predicate':'price','value':{'order':'A','currency':'CNY','cents':100}}})
    source_id=digest(source)
    local_receipt=issue('carrier',carrier_key,{'kind':'gateway_event','workflow':'w',
        'action':'revocation_received','target':source_id})
    events=[]
    append_event(events,{'kind':'start','workflow':'w'})
    append_event(events,{'kind':'controlled_event','target':source_id,
        'type':'controlled_revocation','delivered_to':[]})
    append_event(events,{'kind':'worker_exchange','owner':'carrier','sender':'controlled-event',
        'operation':'reliability_revoke','request':{'target':source_id},
        'response':{'event':local_receipt}})
    append_event(events,{'kind':'worker_exchange','owner':'receiver','sender':'runtime',
        'operation':'reliability_batch','request':{'stage':'initial'},'response':{}})
    run_record={'batches':[{'stage':'initial','proposals':[{'id':'invoice','claims':[source_id]}],
                            'outputs':[{'proposal':'invoice','action':'COMPLETED'}]}]}
    result=audit_accountability(run_record,events,{'public_keys':public},
                                {'old_root':source_id})
    assert result['revocation']['gateway_receipt_owners']==['carrier']
    assert result['revocation']['consumer_gateway_receipt_owners']==[]
    assert result['revocation']['gateway_receipt_index'] is None
    assert result['findings'][0]['classification']=='used_after_controlled_change_without_recorded_notice'
