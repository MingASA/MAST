from trust_network.demo.claim_channel import issue
from trust_network.demo.documents import digest, keypair
from trust_network.demo.run_reliability_multiround import (_find_blocked_invoice,
    _coordinator_input, _packet_view, _parse_coordinator, _parse_receiver)


def test_public_packet_view_is_idempotent_and_keeps_signed_digest():
    key,_=keypair()
    packet=issue('owner',key,{'kind':'claim','workflow':'w','parents':[],
                             'fact':{'predicate':'x','value':{'order':'A','currency':'CNY'}}})
    first=_packet_view(packet)
    second=_packet_view(first)
    assert first==second
    assert first['claim_id']==digest(packet)


def test_multiround_receiver_rejects_incomplete_invoice_claims():
    summary = {
        'status': 'success',
        'draft': {'actions': [{'id': 'invoice-A', 'action': 'approve',
                               'claims': ['authorization'], 'reason': 'missing total'}]},
    }

    proposals, forced, stats = _parse_receiver(
        summary, [('invoice-A', ('approve', 'verify', 'hold'), ['authorization', 'total'])])

    assert proposals == []
    assert forced == []
    assert stats == {'holds': 0, 'invalid': 1}


def test_multiround_recovery_requires_the_controlled_revoked_root():
    root = 'revoked-root'
    malformed = {'outputs': [{'proposal': 'invoice-A', 'action': 'BLOCKED', 'failed_roots': []}]}
    valid = {'outputs': [{'proposal': 'invoice-A', 'action': 'REQUEST_EVIDENCE',
                          'failed_roots': [root]}]}

    assert _find_blocked_invoice([malformed], root) is None
    assert _find_blocked_invoice([valid], root) is valid


def test_recovery_coordinator_contract_separates_rebuild_from_business_action():
    key,_=keypair()
    packets=[issue('owner',key,{'kind':'claim','workflow':'w','parents':[],
                                'fact':{'predicate':name,'value':{'order':'A'}}})
             for name in ('first','second')]
    parent_ids=[digest(packet) for packet in packets]
    value = _coordinator_input(packets,parent_ids,
        {'old_root':'old-root','new_root':'new-root','old_derived':'old-total',
         'recovery_envelope_digest':'envelope-digest',
         'action_authorized':False,'fresh_status_check_still_required':True})

    contract=value['recovery_contract']
    assert contract['mode']=='rebuild_derived_claim'
    assert contract['proposal_is_not_business_authorization'] is True
    assert contract['all_required_parent_claims_present_in_public_claims'] is True
    assert contract['excluded_historical_claims']==['old-root']
    assert contract['replacement_offer_validated_by_runtime'] is True
    assert '不阻止本轮重建证据' in contract['fresh_status_check_scope']
    assert contract['signed_recovery_evidence']=={
        'replacement_offer':None,'coordinator_registration':None}
    assert 'approve_invoice' in contract['purpose']


def test_coordinator_proceed_requires_exact_parent_claim_binding():
    summary={'status':'success','draft':{
        'action':'proceed','claims':['parent-1'],
        'fact':{'predicate':'total_charge','value':{'cents':10700}}}}
    fact,action=_parse_coordinator(summary,['parent-1','parent-2'])
    assert fact is None and action=='model_invalid'
