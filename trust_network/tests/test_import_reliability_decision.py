import json
import pytest
from trust_network.demo.documents import digest
from trust_network.demo.import_reliability_decision import import_decision


def test_external_decisions_preserved_without_repair(tmp_path):
    source={'claims':['expected'],'task':'invoice'}
    sourcepath=tmp_path/'input.json'; sourcepath.write_text(json.dumps(source))
    for i,(status,decision,expected) in enumerate([
        ('success',{'action':'approve','claims':['wrong-reference']},'model_approve'),
        ('success',{'action':'hold'},'model_hold'),
        ('provider_error',None,'provider_error'),
        ('success',{'action':'approve','claims':[]},'invalid_model_decision')]):
        data={'input_hash':digest(source),'model':'external-test-double','status':status,'decision':decision,'usage':None}
        record=tmp_path/f'record{i}.json'; record.write_text(json.dumps(data))
        output=tmp_path/f'out{i}'
        result=import_decision(sourcepath,record,output)
        assert result['classification']==expected and result['usage_unknown']
        proposals=json.loads((output/'proposals.json').read_text())
        assert proposals==([{'id':'invoice-A','operation':'approve_invoice','order':'A','claims':['wrong-reference']}] if i==0 else [])
    data['input_hash']='other-input'; record.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='hash mismatch'):
        import_decision(sourcepath,record,tmp_path/'bad')


def test_hold_stays_hold_in_all_policy_arms(tmp_path):
    from trust_network.demo.prepare_reliability_demo import prepare
    from trust_network.demo.compare_reliability_policies import compare
    fixture=tmp_path/'fixture'; prepare(fixture)
    source=json.loads((fixture/'model_input.json').read_text())
    record=tmp_path/'record.json'
    record.write_text(json.dumps({'input_hash':digest(source),'model':'test-double',
        'status':'success','decision':{'action':'hold'},'usage':None}))
    imported=tmp_path/'imported'
    import_decision(fixture/'model_input.json',record,imported)
    result=compare(fixture,imported/'proposals.json',tmp_path/'comparison',imported/'provenance.json')
    for row in result['rows']:
        assert row['model_hold_count']==1 and row['model_failure_count']==0
        assert row['outcomes']=={} and row['verification_calls']==0
