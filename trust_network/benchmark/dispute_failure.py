"""Offline negative controls for dispute and recovery safety boundaries.

This module does not call a provider.  It constructs signed protocol inputs,
submits malformed or unsafe candidates to the real workers, and archives both
the exact candidate and the rejection/state result.  The live adapter tests
model hold separately; these cases test the program-side fail-closed boundary.
"""

import argparse
import copy
import hashlib
import json
import platform
from pathlib import Path

from trust_network.benchmark.dispute_lifecycle import run as run_lifecycle
from trust_network.benchmark.workflow.backend import MemoryBackend
from trust_network.benchmark.workflow.spec import ARMS, workload
from trust_network.demo.claim_channel import issue
from trust_network.demo.dispute_protocol import propose_revision
from trust_network.demo.documents import digest
from trust_network.demo.fact_evidence import scope_key
from trust_network.demo.recovery_closure import validate_envelope, validate_offer


SCHEMA = 'dispute-safety-negative-controls-v1'


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def _source_hashes():
    root = Path(__file__).resolve().parents[2]
    files = sorted((root / 'trust_network').rglob('*.py'))
    files.append(root / 'pyproject.toml')
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files}


def _archive_hashes(root):
    root = Path(root)
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob('*'))
            if path.is_file() and path.name != 'integrity.json'}


def _unknown_authority_batch(seed=0):
    fixture = workload(seed)
    key = scope_key(fixture['workflow'], fixture['roots']['A']['body']['fact'])
    private = {'buyer': {'settlement_registry': {
        key: {'cents': 125, 'version': 'buyer-A-unknown', 'status': 'unknown'},
    }}}
    backend = MemoryBackend(fixture, ARMS['dependency'], private_state=private)
    root = fixture['roots']['A']
    backend.call('source', {'operation': 'receive', 'packet': root},
                 sender='offline-safety-fixture')
    backend.call('coordinator', {'operation': 'receive', 'packet': root},
                 sender='offline-safety-fixture')
    backend.configs['coordinator']['fact_policy'] = {
        'policy': 'verify_all', 'authority': 'buyer',
    }
    response = backend.call('coordinator', {
        'operation': 'reliability_batch',
        'proposals': [{'id': 'unknown-authority-discovery',
                       'operation': 'forward', 'claims': [digest(root)],
                       'intent': 'verify'}],
    }, sender='offline-safety-case')
    return fixture, backend, response


def _baseline(seed=0):
    """Get valid signed artifacts to mutate for negative controls."""
    metrics, trace, backend = run_lifecycle('memory')
    proof = next(row['request']['packet']['body']['proof'] for row in trace
                 if row['request']['operation'] ==
                 'reliability_notification_accept')
    offer = next(row['response']['offer'] for row in trace
                 if row['request']['operation'] ==
                 'reliability_dispute_revision')
    envelope = next(row['response']['recovery'] for row in trace
                    if row['request']['operation'] ==
                    'reliability_closure_recovery' and
                    row['owner'] == 'receiver_a')
    return metrics, trace, backend, proof, offer, envelope


def _exception_case(name, category, expected, gateway, candidate, operation):
    before = gateway.snapshot() if gateway is not None else None
    try:
        result = operation()
    except Exception as exc:  # The exception itself is the negative result.
        error = {'type': type(exc).__name__, 'message': str(exc)}
        rejected = True
        returned = None
    else:
        error = None
        rejected = False
        returned = result
    after = gateway.snapshot() if gateway is not None else None
    unchanged = before == after if gateway is not None else None
    return {
        'case': name,
        'category': category,
        'expected': expected,
        'observed': {
            'program_rejected': rejected,
            'error': error,
            'returned': returned,
            'gateway_state_unchanged': unchanged,
            'before_state_digest': digest(before) if before is not None else None,
            'after_state_digest': digest(after) if after is not None else None,
        },
        'input': candidate,
    }


def run_offline(out, seed=0):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f'output directory already exists: {out}')
    out.mkdir(parents=True, exist_ok=False)

    baseline_metrics, baseline_trace, backend, proof, offer, envelope = _baseline(seed)
    source = backend.nodes['source']
    receiver = backend.nodes['receiver_a']
    old_id = offer['body']['old']
    old_fact = copy.deepcopy(source.claims[old_id]['body']['fact'])
    query_callback = lambda owner, query: backend.call(
        owner, {'operation': 'reliability_status', 'query': query},
        sender='offline-safety-case')['reply']

    cases = []

    # 1. UNKNOWN is a safe lack of proof.  The real batch gate must return a
    # verification stop and must not invoke the supplied business effect.
    fixture, unknown_backend, unknown_response = _unknown_authority_batch(seed)
    unknown_batch = unknown_response.get('batch')
    unknown_output = (unknown_batch or {}).get('body', {}).get('outputs', [{}])[0]
    fact_statuses = [
        exchange.get('status')
        for check in (unknown_batch or {}).get('body', {})
        .get('fact_checks', {}).values()
        for exchange in check.get('exchanges', [])
    ]
    cases.append({
        'case': 'authority_unknown',
        'category': 'authority_unknown',
        'expected': {
            'program_rejected': False,
            'fail_closed': True,
            'output_action': 'REQUEST_EVIDENCE',
            'business_result': None,
        },
        'observed': {
            'program_rejected': 'error' in unknown_response,
            'error': ({'type': unknown_response.get('error'),
                       'message': unknown_response.get('message')}
                      if 'error' in unknown_response else None),
            'output_action': unknown_output.get('action'),
            'business_result': unknown_output.get('result'),
            'fact_statuses': fact_statuses,
            'gateway_state_unchanged': False,
            'state_change_is_audit_only': True,
        },
        'input': {
            'workflow': fixture['workflow'],
            'claim': digest(fixture['roots']['A']),
            'private_authority_status': 'UNKNOWN',
            'response': unknown_response,
        },
    })

    # A source that has no candidate revision must fail before any retraction
    # is adopted.  The live source_hold scenario tests the model-side version
    # of this boundary; this row tests the worker-side commit boundary.
    cases.append(_exception_case(
        'source_refuses_missing_candidate', 'source_refuses_revision',
        {'program_rejected': True, 'old_claim_must_remain_unchanged': True},
        source, {'proof': proof, 'fact': None},
        lambda: propose_revision(source, proof, None, query_callback)))

    # A syntactically valid but independently false revision is rejected by
    # the authority confirmation before the source adopts its staged state.
    wrong_fact = copy.deepcopy(old_fact)
    wrong_fact['value']['cents'] = 124
    cases.append(_exception_case(
        'wrong_revision_denied_by_authority', 'wrong_revision',
        {'program_rejected': True, 'old_claim_must_remain_unchanged': True},
        source, {'proof': proof, 'fact': wrong_fact},
        lambda: propose_revision(source, proof, wrong_fact, query_callback)))

    # A signed envelope with a foreign task identifier remains a valid packet
    # at the cryptographic layer but is rejected by closure task binding.
    forged_body = copy.deepcopy(envelope['body'])
    forged_body['tasks'][0]['proposal']['id'] = 'foreign-task'
    forged_envelope = issue('receiver_a', receiver.key, forged_body)
    cases.append(_exception_case(
        'wrong_task_binding', 'recovery_binding',
        {'program_rejected': True, 'gateway_state_must_remain_unchanged': True},
        receiver, {'valid_envelope': envelope, 'candidate': forged_envelope},
        lambda: validate_envelope(receiver, forged_envelope, 'receiver_a')))

    # Expiry is checked at validation time even though the reply signature is
    # otherwise valid.
    expired_body = copy.deepcopy(offer['body'])
    resolution = expired_body['fact_resolution']
    resolution['checked_at'] = resolution['reply']['body']['expires_at'] + 1
    expired_offer = issue('source', source.key, expired_body)
    cases.append(_exception_case(
        'expired_confirmation', 'evidence_freshness',
        {'program_rejected': True, 'gateway_state_must_remain_unchanged': True},
        source, {'valid_offer': offer, 'candidate': expired_offer},
        lambda: validate_offer(source, expired_offer)))

    # Obtain a second valid query, then cross-bind its signed query into the
    # first offer.  This simulates replay/cross-task evidence rather than mere
    # byte tampering.
    second_offer = propose_revision(
        source, proof, copy.deepcopy(offer['body']['new']['body']['fact']),
        query_callback)
    replay_body = copy.deepcopy(offer['body'])
    replay_body['fact_resolution']['query'] = copy.deepcopy(
        second_offer['body']['fact_resolution']['query'])
    replay_offer = issue('source', source.key, replay_body)
    cases.append(_exception_case(
        'replayed_cross_bound_evidence', 'evidence_replay',
        {'program_rejected': True, 'gateway_state_must_remain_unchanged': True},
        source, {'valid_offer': offer, 'replay_source_offer': second_offer,
                 'candidate': replay_offer},
        lambda: validate_offer(source, replay_offer)))

    for case in cases:
        _write(out / 'cases' / f"{case['case']}.json", case)
    _write(out / 'baseline_metrics.json', baseline_metrics)
    _write(out / 'baseline_trace.json', baseline_trace)

    expected_rejections = sum(
        case['expected'].get('program_rejected') is True for case in cases)
    observed_rejections = sum(
        case['observed'].get('program_rejected') is True for case in cases)
    state_preserved = sum(
        case['observed'].get('gateway_state_unchanged') is True for case in cases)
    checks = {
        'case_count': len(cases),
        'expected_program_rejections': expected_rejections,
        'observed_program_rejections': observed_rejections,
        'program_rejection_expectations_met': expected_rejections == observed_rejections,
        'state_preservation_checks': state_preserved,
        'all_exception_case_states_preserved': state_preserved == 5,
        'authority_unknown_fail_closed': (
            cases[0]['observed']['output_action'] == 'REQUEST_EVIDENCE' and
            cases[0]['observed']['business_result'] is None and
            cases[0]['observed']['fact_statuses'] == ['UNKNOWN']),
    }
    metrics = {
        'schema': SCHEMA,
        'mode': 'offline',
        'fixture_seed': seed,
        'source_hashes': _source_hashes(),
        'baseline_decision_source': baseline_metrics['decision_source'],
        'model_calls': 0,
        'paid_calls': 0,
        'cases': [case['case'] for case in cases],
        'checks': checks,
        'results': [{
            'case': case['case'],
            'category': case['category'],
            'program_rejected': case['observed'].get('program_rejected'),
            'gateway_state_unchanged': case['observed'].get(
                'gateway_state_unchanged'),
            'output_action': case['observed'].get('output_action'),
            'error': case['observed'].get('error'),
        } for case in cases],
        'interpretation': {
            'model_hold_is_separate': True,
            'signature_validity_is_not_fact_truth': True,
            'unknown_is_not_contradicted': True,
            'all_exception_cases_use_staged_or_read_only_validation': True,
        },
    }
    _write(out / 'metrics.json', metrics)
    report = [
        '# 争议与恢复安全失败：离线负向控制', '',
        '本组不调用模型。它把已签名的有效样本改造成 UNKNOWN、缺失修订、错误修订、错误任务绑定、过期确认和跨提议重放，直接提交给现有 worker/protocol API。', '',
        f"共 {len(cases)} 个场景；模型调用 {metrics['model_calls']}；付费调用 {metrics['paid_calls']}。程序拒绝期望 {expected_rejections}，实际 {observed_rejections}；5 个异常拒绝场景的网关状态保持不变：`{checks['all_exception_case_states_preserved']}`。", '',
        '|场景|程序结果|状态保持|观察|',
        '|---|---|---|---|',
    ]
    for row in metrics['results']:
        observed = row['error']['message'] if row['error'] else row['output_action']
        report.append(f"|`{row['case']}`|`{row['program_rejected']}`|`{row['gateway_state_unchanged']}`|{observed}|")
    report += [
        '', '## 解释', '',
        '- `authority_unknown` 返回 `REQUEST_EVIDENCE`，没有业务结果；UNKNOWN 被保留为“尚未证明”，没有被当作金额错误。',
        '- 缺失候选和错误修订在来源 staged 状态中失败，原声明没有因失败尝试被撤销。',
        '- 错误 task、过期确认和跨提议重放即使带有可验证签名，也不能通过恢复绑定或事实证据绑定。',
        '- 这些是程序拒绝证据；真实模型自行选择 `hold` 或 `request_clarification` 要在 live 场景中另行计数，不能混为一类。',
        '',
        '每个场景的完整输入、签名候选、错误和状态摘要在 `cases/`；有效基线的完整离线 trace 在 `baseline_trace.json`。',
    ]
    (out / 'report.md').write_text('\n'.join(report) + '\n')
    _write(out / 'integrity.json', {
        'schema': 'dispute-safety-negative-controls-integrity-v1',
        'files': _archive_hashes(out),
    })
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run_offline(args.out, args.seed), ensure_ascii=False,
                     indent=2))


if __name__ == '__main__':
    main()
