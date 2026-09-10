"""Causal boundaries of the unified workflow, without provider calls."""
import copy
import pytest
from trust_network.benchmark.workflow.spec import ARMS,workload
from trust_network.benchmark.workflow.backend import MemoryBackend,ProcessBackend
from trust_network.benchmark.workflow.engine import Workflow,Decisions
from trust_network.benchmark.workflow.evaluate import audit,score
from trust_network.benchmark.workflow.__main__ import execute
from trust_network.demo.documents import digest


def run(case,arm,backend=None,tape=None):
    raw,truth=Workflow(backend or MemoryBackend(workload(),ARMS[arm]),case,arm,tape=tape).run()
    return raw,truth,score(raw,truth,audit(raw))


def test_closure_increment_and_strong_gate_equivalence():
    rows={arm:run('intermediate_retraction',arm)[2] for arm in
          ('root_gate','simple_dependency_gate','dependency','verify_all','dependency_push')}
    assert rows['root_gate']['unsafe_completed']==2
    assert rows['dependency']==rows['simple_dependency_gate']==rows['verify_all']
    assert rows['dependency']['unsafe_completed']==0
    assert rows['dependency']['safe_completed']==4
    assert rows['dependency']['unrelated_overfreeze']==0
    push=rows['dependency_push'];pull=rows['dependency']
    assert push['verification_queries']<pull['verification_queries']
    assert push['fault_detection'][0]['first_consumer_detection_delay']<pull['fault_detection'][0]['first_consumer_detection_delay']


def test_late_notices_are_not_forced_before_action():
    raw,_,m=run('late_notice','dependency_push')
    notices=[e['tick'] for e in raw['events'] if e['kind']=='worker_exchange' and e['operation']=='reliability_notification_accept']
    assert min(notices)>14
    assert m['unsafe_completed']==0  # Pull check, not an early push.
    assert m['fault_detection'][0]['first_consumer_detection_delay']==2


@pytest.mark.parametrize('case',['signed_false','conflicting_sources'])
def test_current_truth_detection_boundary_is_preserved(case):
    raw,truth,m=run(case,'verify_all')
    assert m['unsafe_completed']==2
    assert m['max_error_propagation_distance']==3
    assert m['error_accepting_organizations']==5
    assert m['error_route_recall']==1
    assert audit(raw)['truth_accessed'] is False
    for d in raw['decisions']:
        assert 'private_facts' not in d['public_input']
        assert 'actual_cents' not in str(d['public_input'])
        assert 'case' not in d['public_input']


def test_recovery_binding_is_not_mislabeled_as_wrong_amount():
    bound=run('bad_recovery_binding','dependency_push')[2]
    absent=run('bad_recovery_binding','recovery_ablation')[2]
    assert bound['invalid_binding_completed']==0
    assert absent['invalid_binding_completed']==1
    assert bound['unsafe_completed']==absent['unsafe_completed']==0
    assert bound['safe_completed']==3 and absent['safe_completed']==4
    assert bound['recovery_stops']==['completion_evidence_rejected']


def test_literal_tape_does_not_invent_post_verify_approval():
    raw,_,_=run('active','dependency')
    tape={d['stage']:d['draft'] for d in raw['decisions']}
    tape['invoice:A:a']={**tape['invoice:A:a'],'action':'verify'}
    replay,_,metrics=run('active','dependency',tape=tape)
    assert metrics['safe_completed']==3
    follow=next(d for d in replay['decisions'] if d['stage']=='invoice:A:a:after_verify:1')
    assert follow['draft']=={'action':'hold','reason':'tape_entry_missing'}


def test_live_path_never_uses_unregistered_fixture_claims():
    backend=MemoryBackend(workload(),ARMS['dependency'])
    raw,truth=Workflow(backend,'intermediate_retraction','dependency',mode='live').run()
    metrics=score(raw,truth,audit(raw))
    fixture_id=digest(workload()['trace']['A']['coordinator'])
    assert truth['faults']==[]
    assert not any(e['kind']=='fault_injection' for e in raw['events'])
    assert any(e['kind']=='fault_not_realized' for e in raw['events'])
    assert fixture_id not in raw['packets']
    assert metrics['faults_realized']==0
    assert metrics['upstream_unrealized_tasks']==4


def test_derive_prompt_exposes_exact_relay_contract():
    raw,_,_=run('active','dependency')
    prompt=next(d['public_input'] for d in raw['decisions'] if d['stage']=='derive:coordinator:A')
    assert prompt['derivation_rule']=='relay'
    assert 'exact JSON copy' in prompt['derivation_contract']
    assert prompt['output_schema']['claim_refs']==['task[0]']


def test_action_prompt_uses_typed_claim_references():
    raw,_,_=run('active','dependency')
    decision=next(d for d in raw['decisions'] if d['stage']=='invoice:A:a')
    prompt=decision['public_input']
    assert list(prompt['claim_id_index'])==['task[0]','task[1]']
    assert [prompt['claim_id_index'][key] for key in prompt['claim_id_index']]==prompt['candidate_claims']['task']
    assert 'claim_refs' in prompt['output_schema']


def test_route_receipt_tampering_is_rejected():
    raw,_,_=run('active','autonomous')
    event=next(e for e in raw['events'] if e['kind']=='handoff_registered')
    event['receipt']['body']['status']='blocked'
    # Even if an observer rewrites its own hash chain, it cannot forge the peer receipt.
    from trust_network.demo.documents import digest
    for i,e in enumerate(raw['events']):e['previous']=digest(raw['events'][i-1]) if i else None
    with pytest.raises(ValueError):audit(raw)


def test_real_worker_replay_parity_and_private_view(tmp_path):
    process=ProcessBackend(workload(),ARMS['autonomous'],tmp_path/'orgs',private_state={'source':{'actual_cents':125}})
    view=process.call('source',{'operation':'reliability_public_view'})
    assert 'error' not in view and 'actual_cents' not in str(view)
    _,_,actual=run('active','autonomous',process)
    expected=run('active','autonomous')[2]
    for metric in ('safe_completed','unsafe_completed','verification_queries','worker_errors','model_calls'):
        assert actual[metric]==expected[metric]


def test_paid_calls_require_explicit_guard_and_small_matrix(tmp_path):
    with pytest.raises(ValueError):execute(tmp_path/'no','active'.split(),['dependency'],mode='live')
    assert not (tmp_path/'no').exists()
    with pytest.raises(ValueError):execute(tmp_path/'large',['active'],list(ARMS),backend='process',mode='live',allow_paid=True,env_file='unused.env')
    assert not (tmp_path/'large').exists()


def test_integrity_manifest_excludes_runtime_secrets_and_state(tmp_path):
    out=tmp_path/'archive'
    execute(out,['active'],['dependency'],backend='process',mode='replay')
    manifest=__import__('json').loads((out/'integrity.json').read_text())
    assert not any(path.endswith(('/signing.key','/channel_state.json')) for path in manifest)
