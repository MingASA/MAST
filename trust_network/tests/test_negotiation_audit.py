import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from trust_network.demo.negotiation_scenario import generate, PRIVATE
from trust_network.demo.negotiation_worker import handle
from trust_network.demo.run_negotiation import run_case
from trust_network.demo.negotiation_audit import validate
from trust_network.tests.test_negotiation import split_plan


@pytest.mark.parametrize('binding_mode,queries',[('dependency',5),('full',6)])
def test_same_corrected_trajectory_is_sealed_and_reconstructible(tmp_path,monkeypatch,binding_mode,queries):
    from trust_network.demo import negotiation_worker, run_negotiation
    generate(tmp_path/'cases'); buyer_calls=[]
    def model(config,system,payload):
        if '你代表供应商' in system: raw={'lots':PRIVATE['supplier']['lots']}
        elif '你代表物流商' in system: raw={'services':PRIVATE['carrier']['services']}
        else:
            plan=split_plan()
            if not buyer_calls: plan['shipments'][1]['cost']=0
            buyer_calls.append(1); raw={'action':'propose','plan':plan}
        return raw,{'attempts':1,'total_tokens':37}
    def process(command,**kwargs):
        directory=Path(command[command.index('--organization-dir')+1])
        response=handle(directory,json.loads(kwargs['input']),tmp_path/'dummy.env')
        return SimpleNamespace(returncode=0,stdout=json.dumps(response))
    monkeypatch.setattr(negotiation_worker,'complete',model)
    monkeypatch.setattr(negotiation_worker.ProviderConfig,'load',lambda p:None)
    monkeypatch.setattr(run_negotiation.subprocess,'run',process)
    out=tmp_path/'run'
    result=run_case(tmp_path/'cases/urgent',out,tmp_path/'dummy.env',binding_mode=binding_mode)
    assert result['outcome']=='completed' and result['commitment_queries']==queries
    public=json.loads((out/'public_keys.json').read_text())
    assert validate(out,public)['commitments_received']==queries
    original=(out/'result.json').read_text()
    tampered=json.loads(original); tampered['tokens']=0
    (out/'result.json').write_text(json.dumps(tampered))
    with pytest.raises(ValueError,match='seal'): validate(out,public)
    (out/'result.json').write_text(original)
    events=json.loads((out/'events.json').read_text()); events.pop()
    (out/'events.json').write_text(json.dumps(events))
    with pytest.raises(ValueError,match='audit changed'): validate(out,public)


@pytest.mark.parametrize('requests_verification,expected_queries,feasible',[(False,0,False),(True,3,True)])
def test_autonomous_control_can_use_same_verification_tool(tmp_path,monkeypatch,requests_verification,expected_queries,feasible):
    from trust_network.demo import negotiation_worker, run_negotiation
    from trust_network.demo.negotiation import owner_check
    generate(tmp_path/'cases'); calls=[]
    def model(config,system,payload):
        if '你代表供应商' in system: raw={'lots':PRIVATE['supplier']['lots']}
        elif '你代表物流商' in system: raw={'services':PRIVATE['carrier']['services']}
        else:
            plan=split_plan()
            if not calls: plan['shipments'][1]['cost']=0
            raw={'action':'verify' if requests_verification and not calls else 'propose','plan':plan}
            calls.append(1)
        return raw,{'attempts':1,'total_tokens':37}
    def process(command,**kwargs):
        directory=Path(command[command.index('--organization-dir')+1])
        return SimpleNamespace(returncode=0,stdout=json.dumps(handle(directory,json.loads(kwargs['input']),tmp_path/'dummy.env')))
    monkeypatch.setattr(negotiation_worker,'complete',model)
    monkeypatch.setattr(negotiation_worker.ProviderConfig,'load',lambda p:None)
    monkeypatch.setattr(run_negotiation.subprocess,'run',process)
    out=tmp_path/'run'; result=run_case(tmp_path/'cases/urgent',out,tmp_path/'dummy.env',autonomous=True)
    assert result['outcome']=='completed' and result['commitment_queries']==expected_queries
    assert (not owner_check('carrier',PRIVATE['carrier'],result['final_plan']))==feasible
    validate(out,json.loads((out/'public_keys.json').read_text()))
