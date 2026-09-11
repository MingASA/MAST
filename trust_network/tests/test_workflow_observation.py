"""Keep post-notice holds in trial observations, with no invented causation."""
from trust_network.benchmark.workflow.evaluate import decision_citations,audit,score
from trust_network.benchmark.workflow.engine import Workflow
from trust_network.benchmark.workflow.spec import workload,ARMS
from trust_network.benchmark.workflow.backend import MemoryBackend


def test_archived_reference_citations_are_not_dropped():
    view={'claim_id_index':{'task[0]':'signed-id'}}
    assert decision_citations({'claim_refs':['task[0]']},view)==['signed-id']
    assert decision_citations({'claim_refs':['task[9]']},view)==[]
    assert decision_citations({'claim_refs':['task[0]'],'claims':['other']},view)==[]
    assert decision_citations({'claim_refs':[['bad']]},view)==[]
    assert decision_citations({'claims':['legacy']},{})==['legacy']


def test_notice_hold_remains_a_fault_trial_without_gate_opportunity():
    f=workload();arm='dependency_push'
    base,_=Workflow(MemoryBackend(f,ARMS[arm]),'intermediate_retraction',arm).run()
    tape={d['stage']:d['draft'] for d in base['decisions']}
    for stage in ['forward:middle_a:A','forward:middle_b:A','invoice:A:a','invoice:A:b']:
        tape[stage]={'action':'hold','claim_refs':['task[0]'],'reason':'hold is explicit'}
    raw,truth=Workflow(MemoryBackend(f,ARMS[arm]),'intermediate_retraction',arm,tape=tape).run()
    result=score(raw,truth,audit(raw))
    assert result['fault_trial_evaluable']
    assert not result['hard_gate_evaluable']
    assert result['holds_after_visible_negative_evidence']>=2
    assert result['agents']['middle_a']['error_citations']>=1
