from trust_network.benchmark.dispute_live import (
    LiveController, _claim_refs, _fact_ref, _recovery_request_refs, preflight)
from trust_network.benchmark.dispute_lifecycle import run as run_dispute
from trust_network.benchmark.workflow.spec import workload
from trust_network.demo.documents import digest


def test_live_adapter_requires_exact_claim_reference_selection():
    claims = ['claim-a', 'claim-b']
    assert _claim_refs(
        {'action': 'approve', 'claim_refs': ['task[0]', 'task[1]']},
        claims) == claims
    assert _claim_refs(
        {'action': 'approve', 'claim_refs': ['task[1]', 'task[0]']},
        claims) is None
    assert _claim_refs(
        {'action': 'approve', 'claims': claims}, claims) is None
    assert _claim_refs(
        {'action': 'approve', 'claim_refs': ['task[0]']}, claims) is None


def test_live_adapter_never_accepts_model_supplied_fact_for_relay():
    claims = ['claim-a']
    assert _fact_ref({'action': 'proceed', 'fact_ref': 'task[0]'}, claims) == 'claim-a'
    assert _fact_ref({'action': 'proceed', 'fact': {'cents': 125}}, claims) is None
    assert _fact_ref({'action': 'proceed', 'fact_ref': 'task[1]'}, claims) is None


def test_recovery_request_requires_exact_task_and_claim_binding():
    claims = ['claim-a', 'claim-b']
    valid = {
        'action': 'request_recovery', 'task_id': 'invoice:A:a',
        'claim_refs': ['task[0]', 'task[1]'], 'reason': 'repair the held task'}
    assert _recovery_request_refs(valid, claims, 'invoice:A:a') == claims
    assert _recovery_request_refs(
        {**valid, 'task_id': 'invoice:A:b'}, claims, 'invoice:A:a') is None
    assert _recovery_request_refs(
        {**valid, 'claim_refs': ['task[1]', 'task[0]']},
        claims, 'invoice:A:a') is None
    assert _recovery_request_refs(
        {**valid, 'claims': claims}, claims, 'invoice:A:a') is None


def test_explicit_recovery_request_uses_verify_batch_without_business_effect(tmp_path):
    # Reuse the completed in-memory dispute fixture so the receiver has the
    # signed dispute/revocation state needed for a real REQUEST_EVIDENCE basis.
    _, _, backend = run_dispute()
    fixture = workload()
    controller = LiveController(backend, fixture, tmp_path, 28, 56)
    controller.choose = lambda *args, **kwargs: {
        'action': 'request_recovery', 'task_id': 'invoice:A:a',
        'claim_refs': ['task[0]', 'task[1]'],
        'reason': 'repair the held order A task',
    }
    task = {
        'owner': 'receiver_a', 'order': 'A', 'branch': 'a',
        'stage': 'invoice:A:a',
        'claims': [digest(fixture['trace']['A']['middle_a']),
                   digest(fixture['auth']['A'])],
        'status': 'model_hold',
    }
    result = controller.request_recovery(task, digest(fixture['roots']['A']))

    assert result['status'] == 'submitted'
    assert result['runtime_action'] == 'REQUEST_EVIDENCE'
    proposal = result['batch']['proposal']
    assert proposal['intent'] == 'verify'
    assert proposal['recovery_request']['task_id'] == task['stage']
    assert proposal['recovery_request']['claim_refs'] == task['claims']
    assert proposal['recovery_request']['no_business_effect'] is True
    output = result['batch']['packet']['body']['outputs'][0]
    assert output['action'] == 'REQUEST_EVIDENCE'
    assert output['result'] is None
    assert not any(event.get('kind') == 'invoice_approved'
                   for event in backend.nodes['receiver_a'].events)


def test_live_preflight_is_bounded_and_variant_is_recorded(tmp_path):
    env = tmp_path / 'provider.env'
    env.write_text(
        'CAI_MODEL=MiniMax-M3\n'
        'OPENAI_BASE_URL=https://example.invalid/v1\n'
        'OPENAI_API_KEY=test-only\n'
    )
    result = preflight(tmp_path / 'out', env, decision_variant='runtime_gate_probe')
    assert result['decision_variant'] == 'runtime_gate_probe'
    assert result['max_model_decisions'] == 28
    assert result['max_provider_attempts'] == 56
    assert result['paid_calls_started'] is False
