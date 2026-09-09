import copy
import pytest
from trust_network.demo.contract_protocol import (
    check_contract, expected_intent, issue_proposal, receive_proposal, receive_history)
from trust_network.demo.documents import keypair, digest


def bundle():
    return {'transaction':'T1','document_version':1,
            'invoice':{'model':'MX-40B','quantity':10}}


def proposal():
    return {'action':'pass','intent':expected_intent('export_bank',bundle()),
            'claims':{'model':'MX-40B','quantity':10,'formal_authorization':True},
            'draft_explanation':'This text is a draft, not a peer assertion.'}


def test_full_draft_signature_binds_sender_input_nonce_and_message():
    key,public=keypair()
    request={'request_id':'nonce1','documents':bundle()}
    envelope=issue_proposal('export_bank',key,request,proposal())
    assert receive_proposal('export_bank',public,request,envelope)==proposal()
    tampered=copy.deepcopy(envelope)
    tampered['body']['proposal']['draft_explanation']='Changed after signing'
    with pytest.raises(ValueError): receive_proposal('export_bank',public,request,tampered)
    with pytest.raises(ValueError):
        receive_proposal('export_bank',public,dict(request,request_id='nonce2'),envelope)
    with pytest.raises(ValueError): receive_proposal('issuing_bank',public,request,envelope)


def test_false_claim_is_repaired_before_propagation_and_approved_draft_can_continue():
    draft=proposal(); draft['claims']['quantity']=999
    assert check_contract('export_bank',bundle(),draft,'approved','a'*64).action=='repair'
    result=check_contract('export_bank',bundle(),proposal(),'approved','a'*64)
    assert result.action=='allow'
    assert 'draft_explanation' not in result.accepted_message
    assert result.accepted_message['claims']['quantity']['basis']=='public_document'
    assert result.accepted_message['claims']['formal_authorization']['basis']=='formal_model_authorization'


@pytest.mark.parametrize('status,action',[
    ('missing','request_evidence'),('stale_approved','request_evidence'),
    ('denied','stop'),('stale_denied','stop'),('unknown','stop')])
def test_hard_authorization_requirement_does_not_disappear_in_low_risk_cases(status,action):
    assert check_contract('export_bank',bundle(),proposal(),status).action==action


def test_agent_cannot_authorize_another_organizations_operation():
    draft=proposal(); draft['intent']['operation']='release_shipment'
    assert check_contract('export_bank',bundle(),draft,'approved','a'*64).action=='repair'


def test_receiving_organization_requires_complete_ordered_receipt_chain():
    keys={org:keypair() for org in ('export_bank','issuing_bank','fulfillment')}
    public={org:pair[1] for org,pair in keys.items()}
    request={'request_id':'n1'}
    def packet(org,previous):
        finalized={'packet_version':2,'predecessor_hashes':[digest(e) for e in previous],
            'workflow_id':'w1','policy':'autonomous','evidence':None,
            'accepted_message':{'from':org,'document_hash':digest(bundle()),
                'intent':expected_intent(org,bundle()),'claims':proposal()['claims']}}
        return issue_proposal(org,keys[org][0],request,finalized)
    first=packet('export_bank',[]); second=packet('issuing_bank',[first])
    assert len(receive_history('fulfillment',public,bundle(),'w1','autonomous',[first,second],1000.))==2
    for invalid in ([],[first],[first,first],[second,first],[first,packet('issuing_bank',[])]):
        with pytest.raises(ValueError):
            receive_history('fulfillment',public,bundle(),'w1','autonomous',invalid,1000.)
    with pytest.raises(ValueError):
        receive_history('fulfillment',public,bundle(),'another-run','autonomous',[first,second],1000.)
