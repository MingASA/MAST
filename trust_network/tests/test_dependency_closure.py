"""Mechanism counterexamples, not an empirical benchmark or provider pilot."""
import pytest
from trust_network.demo.claim_channel import ClaimGateway, issue
from trust_network.demo.documents import keypair, digest
from trust_network.demo.network_reliability import ReliabilityConfig, run_batch, authority_status
from trust_network.demo.reliability_audit import audit_with_authorities


def setup_chain():
    keys={o:keypair() for o in ('source','middle','left','right','receiver')}
    public={o:k[1] for o,k in keys.items()}; authorities={'amount':'source'}
    nodes={o:ClaimGateway(o,k[0],public,'w',authorities) for o,k in keys.items()}
    def publish(owner,parents,value=1):
        packet=issue(owner,nodes[owner].key,{'kind':'claim','workflow':'w',
            'parents':parents,'rule':'relay','fact':{'predicate':'amount','value':value}})
        for g in nodes.values(): assert g.receive(packet)['body']['action']=='received'
        return digest(packet)
    root=publish('source',[]); middle=publish('middle',[root])
    left=publish('left',[middle]); right=publish('right',[middle])
    independent=publish('source',[],2)
    return nodes,authorities,root,middle,left,right,independent


def revoke_local(nodes,owner,target):
    g=nodes[owner]
    g.receive(issue(owner,g.key,{'kind':'revoke','workflow':'w','target':target,'original':g.claims[target]}))


def test_hidden_middle_retraction_blocks_both_descendants_but_not_independent_branch():
    nodes,authorities,root,middle,left,right,independent=setup_chain()
    revoke_local(nodes,'middle',middle)
    proposals=[{'id':name,'operation':'forward','claims':[claim]} for name,claim in
               [('left',left),('right',right),('independent',independent)]]
    query=lambda owner,q:authority_status(nodes[owner],q)
    old_effects=[]
    old=run_batch(nodes['receiver'],proposals,query,lambda p:old_effects.append(p['id']))
    assert old_effects==['left','right','independent']  # All source roots remain active.
    effects=[]
    report=run_batch(nodes['receiver'],proposals,query,lambda p:effects.append(p['id']),ReliabilityConfig('dependency_closure'))
    assert effects==['independent']
    assert [o['action'] for o in report['body']['outputs']]==['REQUEST_EVIDENCE','REQUEST_EVIDENCE','COMPLETED']
    assert sum(q['query']['root']==middle for q in report['body']['queries'])==1
    assert nodes['receiver'].blockers(left)==[middle]
    assert nodes['receiver'].blockers(right)==[middle]
    assert not nodes['receiver'].blockers(independent)
    assert audit_with_authorities(report,nodes['receiver'].public,authorities)['policy_replay_valid']
    # Issuer-owned status, not someone else's view, is the source of this finding.
    assert authority_status(nodes['source'],{'kind':'reliability_query','workflow':'w','root':middle})['body']['status']=='unknown'
    body=report['body']; body['outputs'][0]['action']='COMPLETED'
    forged=issue('receiver',nodes['receiver'].key,body)
    findings=audit_with_authorities(forged,nodes['receiver'].public,authorities)['findings']
    assert findings[0]['classification']=='execution_report_violates_evidence_duty'


@pytest.mark.parametrize('failure',['budget','wrong_binding','unavailable'])
def test_missing_middle_confirmation_cannot_be_replaced_by_active_roots(failure):
    nodes,_,root,middle,left,_,_=setup_chain(); effects=[]
    def query(owner,q):
        if owner=='middle':
            if failure=='unavailable': raise TimeoutError()
            if failure=='wrong_binding': q=dict(q,batch='other')
        return authority_status(nodes[owner],q)
    packet=run_batch(nodes['receiver'],[{'id':'x','operation':'forward','claims':[left]}],query,
        lambda p:effects.append(p),ReliabilityConfig('dependency_closure'),
        verification_budget=0 if failure=='budget' else None)
    assert not effects and packet['body']['outputs'][0]['action']=='ESCALATE'


def test_closure_selection_and_verify_intent_preserve_semantics():
    nodes,authorities,root,middle,left,_,_=setup_chain(); effects=[]
    proposal={'id':'x','operation':'forward','claims':[left]}
    query=lambda owner,q:authority_status(nodes[owner],q)
    selected=run_batch(nodes['receiver'],[proposal],query,lambda p:effects.append(p),
        ReliabilityConfig('dependency_closure',operation_loss={'forward':0,'approve_invoice':100}))
    assert selected['body']['verification_calls']==0
    checked=run_batch(nodes['receiver'],[dict(proposal,intent='verify')],query,
        lambda p:pytest.fail('verification must never execute'),ReliabilityConfig('verify_all_closure'))
    assert checked['body']['verification_calls']==3
    assert checked['body']['outputs'][0]['action']=='VERIFIED'
    assert audit_with_authorities(checked,nodes['receiver'].public,authorities)['policy_replay_valid']


def test_issuer_with_revoked_parent_returns_negative_without_fabricated_revocation():
    nodes,_,root,middle,*_=setup_chain()
    revoke_local(nodes,'source',root)
    nodes['middle'].receive(nodes['source'].revoked[root])
    reply=authority_status(nodes['middle'],{'kind':'reliability_query','workflow':'w','root':middle})
    assert reply['body']['status']=='revoked'
    assert reply['body']['reason']=='local_dependency_not_active'
    assert 'revocation' not in reply['body']
