import json
import pytest
from trust_network.demo.prepare_reliability_demo import prepare
from trust_network.demo.compare_reliability_policies import compare
from trust_network.demo.evaluate_reliability_comparison import evaluate


@pytest.mark.parametrize('condition', ['active','hidden_revoke'])
def test_static_truth_is_post_run_and_denominators_explicit(tmp_path,condition):
    fixture=tmp_path/'fixture'; prepare(fixture,condition)
    comparison=tmp_path/'comparison'
    compare(fixture,fixture/'scripted_proposals.json',comparison)
    scored=evaluate(comparison,fixture/'evaluation_truth.json')
    a,v,d=scored['rows']
    assert all(r['submitted']==2 and r['effect_unknown']==0 for r in scored['rows'])
    if condition=='hidden_revoke':
        assert a['unsafe_completed']==1 and a['unsafe_completion_rate_per_submitted']==0.5
        assert v['unsafe_completed']==d['unsafe_completed']==0
        assert v['error_blocked']==d['error_blocked']==1
        assert v['safe_completion_rate_per_allowed_submitted']==d['safe_completion_rate_per_allowed_submitted']==1
    else:
        assert all(r['safe_completed']==2 and r['unsafe_completed']==0 for r in scored['rows'])
    truth=json.loads((fixture/'evaluation_truth.json').read_text()); truth['model_input_hash']='wrong'
    (fixture/'wrong_truth.json').write_text(json.dumps(truth))
    with pytest.raises(ValueError,match='mismatch'):
        evaluate(comparison,fixture/'wrong_truth.json')
