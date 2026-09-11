import copy

import pytest

from trust_network.benchmark.contribution.forensics import audit as audit_public
from trust_network.benchmark.contribution.generalization import (
    FAULTS,
    FREEZE_SCOPES,
    NOTICE_SCOPES,
    RESPONSIBILITY_ACTORS,
    RESPONSIBILITY_CASES,
    RESPONSIBILITY_PROJECTIONS,
    TIMINGS,
    TOPOLOGIES,
    build_responsibility_execution,
    project_responsibility,
    run_freeze,
    run_freeze_matrix,
    run_responsibility_matrix,
    score_responsibility,
    _responsibility_keypair,
)
from trust_network.demo.claim_channel import issue


def test_non_original_topology_runs_the_four_freeze_cells():
    rows = [run_freeze('converge_then_fork', 'shared_upstream',
                       'all_before_deadline', notice, scope)
            for notice in NOTICE_SCOPES for scope in FREEZE_SCOPES]
    assert len({row['reference_id'] for row in rows}) == 1
    assert all(row['metrics']['unsafe_completion_count'] == 0 for row in rows)
    assert rows[0]['metrics']['unaffected_retention'] == 1
    assert rows[1]['metrics']['overfrozen_tasks'] > 0
    assert rows[0]['metrics']['duplicate_notice_receipts'] > 0


def test_complete_freeze_matrix_has_fixed_paired_references_and_late_boundary():
    rows = run_freeze_matrix()
    assert len(rows) == 48
    for topology in TOPOLOGIES:
        for fault in FAULTS:
            for timing in TIMINGS:
                group = [row for row in rows
                         if row['topology'] == topology and row['fault'] == fault
                         and row['timing'] == timing]
                assert len(group) == 4
                assert len({row['reference_id'] for row in group}) == 1
                if timing == 'all_before_deadline':
                    assert all(row['unsafe_completion_count'] == 0 for row in group)
                else:
                    assert all(row['critical_edge_late_at_action'] for row in group)


def test_reused_organization_keeps_independent_task_under_dependency_freeze():
    selective = run_freeze('reused_org_independent', 'branch_middle',
                           'all_before_deadline', 'routed', 'dependency')
    coarse = run_freeze('reused_org_independent', 'branch_middle',
                        'all_before_deadline', 'routed', 'recipient_workload')
    assert set(selective['effects']) == {'A_b', 'C_a', 'C_b'}
    assert selective['metrics']['overfrozen_tasks'] == 0
    assert coarse['metrics']['overfrozen_tasks'] == 2


def test_responsibility_matrix_uses_three_actors_and_independent_labels():
    executions, rows = run_responsibility_matrix()
    assert len(executions) == 15
    assert len(rows) == 120
    assert {execution['truth']['actor'] for execution in executions} == set(RESPONSIBILITY_ACTORS)
    assert {execution['truth']['case'] for execution in executions} == set(RESPONSIBILITY_CASES)
    positives = [row for row in rows if row['case'] == 'own_notice'
                 and row['view'] == 'full' and row['fault'] == 'none']
    assert len(positives) == 3
    assert all(row['duty_violations']['recall'] == 1 for row in positives)
    assert all(row['false_accusations'] == 0 for row in rows)


def test_responsibility_faults_abstain_and_conflict_is_not_a_legal_second_action():
    execution = build_responsibility_execution('receiver_c', 'own_notice')
    for fault in ('missing_relevant_notice', 'missing_order_node', 'conflicting_action'):
        observation = project_responsibility(execution, 'full', fault)
        assessment = audit_public(observation)
        score = score_responsibility(execution, observation, assessment, 'full', fault)
        assert assessment['findings'] == {'action-0': 'undetermined'}
        assert score['undetermined_when_insufficient'] is True

    legal = copy.deepcopy(execution['observation'])
    private, _ = _responsibility_keypair(0, 'receiver_c', 'own_notice', 'receiver_c')
    action_one = issue('receiver_c', private, {
        'kind': 'benchmark_use', 'workflow': legal['workflow'],
        'proposal': {'id': 'action-1', 'operation': 'forward',
                     'claims': legal['uses'][0]['body']['proposal']['claims']},
        'action': 'COMPLETED', 'local_head': legal['uses'][0]['body']['local_head'],
    })
    legal['uses'].append(action_one)
    assessment = audit_public(legal)
    assert assessment['findings']['action-0'] == 'violation'


@pytest.mark.parametrize('case', RESPONSIBILITY_CASES)
def test_public_responsibility_observation_has_no_evaluator_fields(case):
    execution = build_responsibility_execution('receiver_a', case)
    for view, fault in RESPONSIBILITY_PROJECTIONS:
        observation = project_responsibility(execution, view, fault)
        assert 'truth' not in observation
        assert 'case' not in observation
        assert 'actor' not in observation
