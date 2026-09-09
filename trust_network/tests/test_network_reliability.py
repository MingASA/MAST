import pytest
from trust_network.demo.claim_channel import ClaimGateway, issue
from trust_network.demo.documents import keypair, digest
from trust_network.demo.network_reliability import ReliabilityConfig, plan, run_batch, authority_status
from trust_network.demo.reliability_audit import audit_with_authorities


def network():
    keys = {o:keypair() for o in ('buyer','billing','receiver')}
    public = {o:k[1] for o,k in keys.items()}
    authorities = {'invoice_authorization':'buyer','total_charge':'billing'}
    nodes = {o:ClaimGateway(o,k[0],public,'w',authorities) for o,k in keys.items()}
    targets = []
    for owner,predicate,value in (
        ('buyer','invoice_authorization',{'order':'A','operation':'approve_invoice','currency':'CNY','maximum_cents':200,'approved':True}),
        ('billing','total_charge',{'order':'A','currency':'CNY','cents':100})):
        packet=issue(owner,keys[owner][0],{'kind':'claim','workflow':'w','parents':[],
                                         'fact':{'predicate':predicate,'value':value}})
        nodes[owner].receive(packet); nodes['receiver'].receive(packet); targets.append(digest(packet))
    return nodes, targets, authorities


def test_shared_checks_and_public_audit():
    nodes, claims, authorities = network()
    proposals = [{'id':'approve','operation':'approve_invoice','order':'A','claims':claims},
                 {'id':'notify','operation':'forward','claims':[claims[1]]}]
    report = run_batch(nodes['receiver'],proposals,lambda o,q:authority_status(nodes[o],q),
                       lambda p:{'simulation':p['id']})
    assert report['body']['verification_calls']==2
    assert all(o['action']=='COMPLETED' for o in report['body']['outputs'])
    audit=audit_with_authorities(report,nodes['receiver'].public,authorities)
    assert audit['policy_replay_valid'] and not audit['effect_proven']


def test_unseen_revocation_freezes_only_related_branch_and_overrides_approval():
    nodes, claims, authorities = network()
    buyer=nodes['buyer']; original=buyer.claims[claims[0]]
    buyer.receive(issue('buyer',buyer.key,{'kind':'revoke','workflow':'w','target':claims[0],'original':original}))
    proposals=[{'id':'approve','operation':'approve_invoice','order':'A','claims':claims,'downstream_loss':100},
               {'id':'independent','operation':'forward','claims':[claims[1]],'downstream_loss':0}]
    effects=[]
    result=run_batch(nodes['receiver'],proposals,lambda o,q:authority_status(nodes[o],q),lambda p:effects.append(p['id']),
                     ReliabilityConfig(operation_loss={'forward':0,'approve_invoice':100}))
    assert result['body']['outputs'][0]['action']=='REQUEST_EVIDENCE'
    assert effects==['independent']
    audit_with_authorities(result,nodes['receiver'].public,authorities)


def test_budget_never_bypasses_action_checks_and_wrong_reply_cannot_authorize():
    nodes, claims, _ = network()
    p=[{'id':'approve','operation':'approve_invoice','order':'A','claims':claims}]
    effects=[]
    result=run_batch(nodes['receiver'],p,lambda o,q:authority_status(nodes[o],q),lambda p:effects.append(1),verification_budget=0)
    assert result['body']['outputs'][0]['action']=='ESCALATE' and not effects
    def wrong(owner, query):
        query=dict(query,batch='another-batch')
        return authority_status(nodes[owner],query)
    result=run_batch(nodes['receiver'],p,wrong,lambda p:effects.append(1))
    assert result['body']['outputs'][0]['action']=='ESCALATE' and not effects


def test_policy_cost_difference_and_repair_does_not_resurrect_old_claims():
    nodes, claims, _=network(); receiver=nodes['receiver']
    p=[{'id':'low','operation':'forward','claims':[claims[1]],'downstream_loss':0}]
    assert len(plan(receiver,p,ReliabilityConfig('verify_all'))['checks'])==1
    assert len(plan(receiver,p,ReliabilityConfig(operation_loss={'forward':0,'approve_invoice':100}))['checks'])==0
    # An untrusted model cannot waive checks by declaring zero downstream loss.
    assert len(plan(receiver,p)['checks'])==1
    owner=nodes['billing']; original=owner.claims[claims[1]]
    revoke=issue('billing',owner.key,{'kind':'revoke','workflow':'w','target':claims[1],'original':original})
    receiver.receive(revoke)
    value=dict(original['body']); value['fact']={'predicate':'total_charge','value':{'order':'A','currency':'CNY','cents':120}}
    receiver.receive(issue('billing',owner.key,value))
    result=plan(receiver,p)
    assert result['decisions'][0]['action']=='REQUEST_EVIDENCE'
    assert result['decisions'][0]['revoked']==[claims[1]]


def test_signed_bad_plan_and_false_completion_are_distinguished():
    nodes, claims, authorities=network(); receiver=nodes['receiver']
    p=[{'id':'approve','operation':'approve_invoice','order':'A','claims':claims}]
    report=run_batch(receiver,p,lambda o,q:authority_status(nodes[o],q),lambda p:None,verification_budget=0)
    body=report['body']; body['outputs'][0]['action']='COMPLETED'
    false_report=issue('receiver',receiver.key,body)
    audit=audit_with_authorities(false_report,receiver.public,authorities)
    assert audit['findings'][0]['classification']=='execution_report_violates_evidence_duty'
    body['plan']['body']['plan']['decisions'][0]['action']='PASS'
    body['plan']=issue('receiver',receiver.key,body['plan']['body'])
    with pytest.raises(ValueError,match='declared policy'):
        audit_with_authorities(issue('receiver',receiver.key,body),receiver.public,authorities)


def test_serial_process_entrypoint_without_provider(tmp_path):
    import json
    from trust_network.demo.prepare_reliability_demo import prepare
    from trust_network.demo.reliability_runner import run
    fixture=tmp_path/'fixture'; prepare(fixture,'hidden_revoke')
    result=run(fixture/'manifest.json',fixture/'scripted_proposals.json',tmp_path/'result')
    assert [o['action'] for o in result['batch']['body']['outputs']]==['REQUEST_EVIDENCE','COMPLETED']
    assert json.loads((tmp_path/'result'/'audit.json').read_text())['policy_replay_valid']


def test_negative_query_blocks_low_risk_sibling_and_survives_next_batch():
    nodes, claims, authorities=network(); buyer=nodes['buyer']; receiver=nodes['receiver']
    original=buyer.claims[claims[0]]
    buyer.receive(issue('buyer',buyer.key,{'kind':'revoke','workflow':'w',
                                         'target':claims[0],'original':original}))
    policy=ReliabilityConfig(operation_loss={'forward':0,'approve_invoice':100})
    proposals=[{'id':'approve','operation':'approve_invoice','order':'A','claims':claims},
               {'id':'relay','operation':'forward','claims':[claims[0]]}]
    effects=[]
    report=run_batch(receiver,proposals,lambda o,q:authority_status(nodes[o],q),
                     lambda p:effects.append(p['id']),policy)
    assert not effects and all(o['action']=='REQUEST_EVIDENCE' for o in report['body']['outputs'])
    assert claims[0] in receiver.revoked
    assert audit_with_authorities(report,receiver.public,authorities)['policy_replay_valid']
    # A later low-risk-only batch must not forget the delivered signed revocation.
    later=run_batch(receiver,[proposals[1]],lambda o,q:pytest.fail('no query needed'),
                    lambda p:effects.append(p['id']),policy)
    assert later['body']['outputs'][0]['action']=='REQUEST_EVIDENCE' and not effects
