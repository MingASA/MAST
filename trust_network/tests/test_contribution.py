import copy
import pytest
from trust_network.benchmark.contribution.freeze import run
from trust_network.benchmark.contribution.forensics import build_execution, project, audit, score


def test_factorized_freeze_same_tape_and_real_effects():
    rows = [run(notice_scope=n, freeze_scope=s)
            for n in ('routed', 'broadcast') for s in ('dependency', 'recipient_workload')]
    assert len({r['reference_id'] for r in rows}) == 1
    for r in rows:
        assert r['metrics']['unsafe_completion_count'] == 0
        assert r['metrics']['affected_tasks_blocked'] == 2
        if r['factors']['freeze_scope'] == 'dependency':
            assert set(r['effects']) == {'C_a', 'C_b'}
            assert r['metrics']['overfrozen_tasks'] == 0
        else:
            assert r['effects'] == []
            assert r['metrics']['overfrozen_tasks'] == 2
    assert rows[2]['metrics']['notice_attempts'] > rows[0]['metrics']['notice_attempts']


def test_branch_fault_and_broadcast_are_separate_factors():
    routed = run(fault='middle_a', freeze_scope='recipient_workload')
    broad = run(fault='middle_a', notice_scope='broadcast', freeze_scope='recipient_workload')
    selective = run(fault='middle_a', notice_scope='broadcast')
    assert set(routed['effects']) == {'A_b', 'C_b'}
    assert broad['effects'] == []
    assert set(selective['effects']) == {'A_b', 'C_a', 'C_b'}
    assert selective['metrics']['unaffected_task_count'] == 3


def test_late_or_lost_notice_not_relabelled_as_containment():
    for kwargs in ({'delay': 50}, {'drop_receivers': ('receiver_a', 'receiver_b')}):
        result = run(**kwargs)
        assert result['metrics']['unsafe_completion_count'] == 2
        assert result['metrics']['unaffected_retention'] == 1
    result = run(edge_delays={'middle_a->receiver_a': 20})
    assert result['metrics']['unsafe_completion_count'] == 1
    assert 'A_a' in result['effects'] and 'A_b' not in result['effects']


def test_fixed_evidence_denominators_and_honest_unsigned_baseline():
    execution = build_execution()
    results = {}
    for view in ('full', 'ordinary_logs', 'no_receipts', 'opaque_relay'):
        o = project(execution, view)
        results[view] = score(execution, o, audit(o))
    assert {r['routes_verified']['expected'] for r in results.values()} == {10}
    assert results['full']['routes_verified']['recall'] == 1
    assert results['no_receipts']['routes_verified']['recall'] == 0
    assert results['ordinary_logs']['routes_unsigned_estimate']['recall'] == 1
    assert results['ordinary_logs']['routes_verified']['recall'] == 0
    assert results['full']['duty_violations']['recall'] == 1
    assert results['opaque_relay']['duty_violations']['recall'] == 0
    assert results['opaque_relay']['warranted_undetermined']['recall'] == 1


@pytest.mark.parametrize('fault', ['missing_notice', 'missing_link'])
def test_missing_proof_abstains_without_accusation(fault):
    execution = build_execution()
    o = project(execution, fault=fault)
    a = audit(o)
    assert a['findings'] == {'action-0': 'undetermined'}
    assert score(execution, o, a)['duty_violations']['recall'] == 0


@pytest.mark.parametrize('case', ['other_notice', 'late_notice', 'unrelated_notice', 'no_notice'])
def test_negative_duties_not_invented(case):
    e = build_execution(case=case)
    a = audit(project(e))
    assert a['findings'] == {'action-0': 'undetermined'}
    assert score(e, project(e), a)['false_accusations'] == 0


def test_reordering_does_not_change_signed_order():
    e = build_execution()
    normal, reordered = project(e), project(e, fault='reorder')
    assert score(e, normal, audit(normal)) == score(e, reordered, audit(reordered))


def test_corruption_and_ambiguous_unsigned_routes():
    e = build_execution()
    o = project(e, fault='tampered_receipt')
    result = score(e, o, audit(o))
    assert result['rejected_evidence_count'] >= 1
    assert result['routes_verified']['recall'] == .9
    o = project(e, fault='ambiguous_route')
    result = score(e, o, audit(o))
    assert result['routes_unsigned_estimate']['false_positive'] == 1
    assert result['routes_verified']['false_positive'] == 0


def test_projection_no_nested_signed_evidence_leak_or_mutation():
    e = build_execution()
    before = copy.deepcopy(e)
    for view in ('ordinary_logs', 'opaque_relay'):
        o = project(e, view)
        assert all(o[k] == [] for k in ('claims', 'handoffs', 'receipts', 'events', 'uses'))
        assert 'truth' not in o and 'case' not in o and 'keys' not in o
    assert e == before
