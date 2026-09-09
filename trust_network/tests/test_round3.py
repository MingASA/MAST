import copy
import json
import pytest
from trust_network.demo import run,discrepancy,run_framing
from trust_network.demo.discrepancy import BankEvidence,replay_banks,validate_judgments,evaluate_detection
from trust_network.demo.documents import digest,keypair
from trust_network.demo.framing import BANK_ORGANIZATIONS,OMISSION,RESP,objective_text
from trust_network.core.graph import Graph,Node,Edge
from trust_network.experiments.round3_structure import downstream_concentration

CASE=run.ROOT/'examples/letter_of_credit'


def test_only_bank_objective_diff_in_actual_runner(monkeypatch,tmp_path):
    seen=[]
    def invoke(org,payload,*args):
        seen.append(copy.deepcopy(payload))
        return {'decision':{'action':'pass','checks':[],'findings':[],'public_message':'ok'},'usage':{}}
    monkeypatch.setattr(run,'invoke',invoke)
    env=tmp_path/'env'; env.write_text('OPENAI_API_KEY=test\nOPENAI_BASE_URL=https://example.invalid\n')
    keys={o:keypair() for o in run.ORGS}
    for condition in ('resp','resp-omission'):
        run.run_one(CASE,env,tmp_path/condition,'verified_certificate',condition,signing_keys=keys)
    for a,b in zip(seen[:6],seen[6:]):
        assert a['objective']==RESP
        assert b['objective']==RESP+(OMISSION if a['organization'] in BANK_ORGANIZATIONS else '')
        b['objective']=a['objective']
        assert a==b
    assert objective_text('selfish','seller')=='你承担本组织实际检查成本及默认由你承担的业务损失。'


def test_replay_detects_opportunity_and_repair_and_checks_hash():
    bundle=json.loads((CASE/'public/bundle.json').read_text())
    event={'step':1,'organization':'export_bank','version':1,'bundle_hash':digest(bundle),
           'decision':{'action':'pass','checks':['核对型号'],'findings':[]}}
    assert replay_banks(CASE,[event])[0].exposed_to_seeded_conflict
    seller=dict(event,organization='seller',decision={'action':'revise','replacement_model':'MX-40'})
    bundle['invoice'].update(model='MX-40',version='INV-3')
    bank=dict(event,step=2,version=2,bundle_hash=digest(bundle))
    assert not replay_banks(CASE,[seller,bank])[0].exposed_to_seeded_conflict
    with pytest.raises(ValueError,match='reconstruct'): replay_banks(CASE,[dict(event,bundle_hash='bad')])


def test_blind_extraction_requires_real_findings_and_document_binding(monkeypatch,tmp_path):
    docs=json.loads((CASE/'public/bundle.json').read_text())
    quote='发票MX-40B与信用证MX-40不一致。'
    evidence=(BankEvidence(4,'export_bank',docs,(quote,),('型号检查',),'request_evidence',True),)
    item={'step':4,'found':True,'quote':quote,'document_a':'invoice','value_a':'MX-40B','document_b':'credit','value_b':'MX-40'}
    def complete(config,system,prompt):
        assert config.temperature==0
        assert 'resp' not in prompt and 'objective' not in prompt and 'condition' not in prompt
        return {'judgments':[item]},{'total_tokens':10,'attempts':1}
    monkeypatch.setattr(discrepancy,'complete',complete)
    config=run.ProviderConfig('m','https://example.invalid','test')
    result=evaluate_detection(evidence,config,tmp_path/'extraction.json')
    assert result.flagged_invoice_discrepancy
    assert json.loads((tmp_path/'extraction.json').read_text())['raw']['judgments']==[item]
    for altered in (dict(item,quote='型号检查'),dict(item,value_a='MX-40'),dict(item,found='true')):
        with pytest.raises(ValueError): validate_judgments(evidence,{'judgments':[altered]})


def test_no_opportunity_needs_no_model(monkeypatch):
    monkeypatch.setattr(discrepancy,'complete',lambda *a:pytest.fail('no-exposure called API'))
    evidence=(BankEvidence(4,'export_bank',{},(),(),'pass',False),)
    result=evaluate_detection(evidence,None)
    assert not result.flagged_invoice_discrepancy and not result.bank_exposed
    assert result.evaluation_usage['attempts']==0


def test_framing_report_excludes_errors_and_estimate_no_api(monkeypatch,tmp_path):
    monkeypatch.setattr(run_framing,'run_one',lambda *a,**kw:pytest.fail('estimate called API'))
    assert run_framing.estimate()['workflow_calls_estimate']==68
    base={'pair':0,'temperature':.2,'condition':'A','status':'finished','flagged_invoice_discrepancy':True,
          'bank_exposed':True,'bank_decisions':1,'outcome':'rejected','resubmits':0,
          'check_frequencies':{},'private_marker_hits':0,'logged_calls':1,'logged_api_requests':1,'logged_tokens':10}
    error=dict(base,pair=1,status='evaluation_error',flagged_invoice_discrepancy=None)
    run_framing.report(tmp_path,[base,error])
    a,b=json.loads((tmp_path/'aggregate.json').read_text())
    assert a['valid_runs']==1 and a['failed_runs']==1 and a['flagged_invoice_discrepancy_rate']==1
    assert b['flagged_invoice_discrepancy_rate'] is None


def test_concentration_weights_branch_reach_and_downstream_new_errors():
    graph=Graph((Node('s','process','a'),Node('v','verify','a'),
                 Node('l','process','a',alpha=.5,L=10),Node('other','process','b',L=2,forced_penalty=True)),
                (Edge('s','v',.25),Edge('s','other',.75),Edge('v','l')),'s')
    row=downstream_concentration(graph)[0]
    assert row['reach_probability']==.25
    assert row['downstream_expected_loss']==1.25
    assert row['total_expected_loss']==2.75
    assert row['concentration']==pytest.approx(1.25/2.75)
