import copy
import pytest
from trust_network.tests.test_network_reliability import network
from trust_network.demo.claim_channel import issue
from trust_network.demo.network_reliability import run_batch,authority_status,ReliabilityConfig
from trust_network.demo.reliability_audit import audit_with_authorities
from trust_network.demo.reliability_stage import stage_status
from trust_network.benchmark.live import _parse_receiver,_apply_actions


def test_verify_cannot_execute_even_when_every_check_passes_and_approval_rechecks():
    nodes,claims,authorities=network();receiver=nodes['receiver'];effects=[]
    proposal={'id':'invoice-A','operation':'approve_invoice','order':'A','claims':claims,'intent':'verify'}
    query=lambda o,q:authority_status(nodes[o],q)
    result=run_batch(receiver,[proposal],query,lambda p:effects.append('effect'),ReliabilityConfig('autonomous'))
    assert result['body']['outputs'][0]['action']=='VERIFIED' and not effects
    assert result['body']['verification_calls']==2
    assert not any(e['body']['action'] in ('action_contract_allowed','action_effect_returned') for e in receiver.events)
    audit_with_authorities(result,receiver.public,authorities)
    fake=copy.deepcopy(result['body']);fake['outputs'][0]['action']='COMPLETED'
    findings=audit_with_authorities(issue(receiver.owner,receiver.key,fake),receiver.public,authorities)['findings']
    assert findings[0]['classification']=='execution_report_violates_evidence_duty'
    approve=dict(proposal,intent='execute')
    assert run_batch(receiver,[approve],query,lambda p:effects.append('effect'))['body']['outputs'][0]['action']=='COMPLETED'
    assert effects==['effect']
    original=nodes['buyer'].claims[claims[0]]
    nodes['buyer'].receive(issue('buyer',nodes['buyer'].key,{'kind':'revoke','workflow':'w','target':claims[0],'original':original}))
    assert run_batch(receiver,[approve],query,lambda p:effects.append('bad'))['body']['outputs'][0]['action']=='REQUEST_EVIDENCE'
    assert effects==['effect']


@pytest.mark.parametrize('budget,next_action,expected',[(1,'approve',['VERIFIED','COMPLETED']),(0,'approve',['VERIFIED']),(1,'hold',['VERIFIED'])])
def test_dispatch_requires_new_explicit_decision_and_respects_budget(budget,next_action,expected):
    nodes,claims,_=network();effects=[]
    class Controller:
        model_count=0
        max_model_decisions=budget
        events=[]
        def run_batch(self,proposals,stage,force_verify=False):
            if force_verify:proposals=[dict(p,intent='verify') for p in proposals]
            packet=run_batch(nodes['receiver'],proposals,lambda o,q:authority_status(nodes[o],q),lambda p:effects.append(1))
            return {'packet':packet,'proposals':proposals,'outputs':packet['body']['outputs']}
        def model(self,owner,model_input,stage):
            self.model_count+=1
            assert not effects and model_input['verification_evidence']
            return {'status':'success','draft':{'actions':[{'id':'invoice-A','action':next_action,'claims':claims}]}}
    initial={'status':'success','draft':{'actions':[{'id':'invoice-A','action':'verify','claims':claims}]}}
    parsed=_parse_receiver(initial,[('invoice-A',('approve','verify','hold'),claims)])
    assert parsed[0][0]['intent']=='verify'
    controller=Controller()
    batches,stats=_apply_actions(controller,parsed,'recovery')
    assert [o['action'] for b in batches for o in b['outputs']]==expected
    assert effects==([1] if next_action=='approve' and budget else [])
    if not budget:assert stats['awaiting_explicit_action']==1 and controller.model_count==0


def test_stage_local_rebuild_permission_is_not_execution_permission():
    nodes,claims,_=network();g=nodes['receiver']
    ready=stage_status(g,'derive',[claims[1]])['body']
    assert ready['may_propose_derivation'] and not ready['business_execution_authorized']
    assert ready['future_write_checks_required']
    assert not stage_status(g,'derive',['missing'])['body']['may_propose_derivation']
    original=nodes['billing'].claims[claims[1]]
    g.receive(issue('billing',nodes['billing'].key,{'kind':'revoke','workflow':'w','target':claims[1],'original':original}))
    assert not stage_status(g,'derive',[claims[1]])['body']['may_propose_derivation']


def test_worker_legacy_force_verify_cannot_invoke_simulated_action(tmp_path,monkeypatch):
    import io,json,sys
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
    from trust_network.demo.claim_worker import handle
    nodes,claims,authorities=network();g=nodes['receiver']
    (tmp_path/'config.json').write_text(json.dumps({'owner':'receiver','workflow':'w',
        'public_keys':g.public,'authorities':authorities}))
    (tmp_path/'signing.key').write_bytes(g.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
    (tmp_path/'channel_state.json').write_text(json.dumps({'claims':g.claims,'revoked':g.revoked,'events':g.events}))
    stdout=io.StringIO()
    class Replies:
        def readline(self):
            sent=json.loads(stdout.getvalue().splitlines()[-1])
            reply=authority_status(nodes[sent['authority']],sent['authority_query'])
            return json.dumps({'reply':reply})+'\n'
    monkeypatch.setattr(sys,'stdout',stdout);monkeypatch.setattr(sys,'stdin',Replies())
    result=handle(tmp_path,{'operation':'reliability_batch','force_verify':True,
        'proposals':[{'id':'invoice-A','operation':'approve_invoice','order':'A','claims':claims}]},tmp_path/'unused.env')
    output=result['batch']['body']['outputs'][0]
    assert output['action']=='VERIFIED' and output['result'] is None
    assert not any(e['body']['action']=='action_effect_returned' for e in result['events'])
