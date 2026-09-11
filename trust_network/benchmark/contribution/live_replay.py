"""Evidence replay of archived workflow traces; no provider, signing, or execution.

Registration logs define fixed archival route labels, NOT external physical
truth. There are no independent duty labels in these historical traces.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from .forensics import audit, project, route_label, signed_artifacts, batch_question, VIEWS, FAULTS
from trust_network.demo.claim_channel import read
from trust_network.demo.documents import digest, canonical


def import_trace(raw):
    if raw.get('mode') != 'live':
        raise ValueError('expected archived live workflow')
    for i, event in enumerate(raw['events']):
        if event['sequence'] != i or event['previous'] != (digest(raw['events'][i-1]) if i else None):
            raise ValueError('broken controller archive chain')
    for cid, packet in raw['packets'].items():
        if digest(packet) != cid:
            raise ValueError('packet digest mismatch')
    # Validate original signatures, including nested evidence, before projection.
    signed = {digest(p): p for p in signed_artifacts(
        {'packets': raw['packets'], 'batches': raw['batches'], 'events': raw['events']})}
    workflows = set()
    for packet in signed.values():
        _, body = read(packet, raw['public_keys'])
        if 'workflow' in body:
            workflows.add(body['workflow'])
    if len(workflows) != 1:
        raise ValueError('mixed or missing workflow scope')
    registered = [e for e in raw['events'] if e['kind'] == 'handoff_registered'
                  and e['receipt']['body']['status'] == 'accepted']
    select = lambda kind: [p for p in signed.values() if p['body'].get('kind') == kind]
    observation = {'workflow': workflows.pop(), 'public_keys': copy.deepcopy(raw['public_keys']),
                   'claims': select('claim'), 'handoffs': select('dependency_handoff'),
                   'receipts': select('handoff_receipt'), 'events': select('gateway_event'),
                   'batches': copy.deepcopy(raw['batches']), 'uses': [],
                   'questions': [batch_question(p, i) for p in raw['batches']
                                 for i, out in enumerate(p['body']['outputs']) if out['action'] == 'COMPLETED'],
                   'ordinary_logs': [route_label(e['packet']) for e in registered]}
    # Fixed archival reference is separate from the public auditor input.
    reference = {'routes': [route_label(e['packet']) for e in registered],
                 'sources': {cid: p['signature']['issuer'] for cid, p in raw['packets'].items()
                             if p['body'].get('kind') == 'claim' and not p['body']['parents']},
                 'duty_labels': None, 'basis': 'controller_registration_and_archived_root_signatures'}
    return {'execution_id': digest(raw), 'observation': observation, 'reference': reference,
            'provenance': {'mode': raw['mode'], 'arm': raw['arm'], 'case': raw['case'],
                           'historical_model_calls': raw.get('model_calls'),
                           'effects_are_simulated': raw.get('effects_are_simulated'),
                           'original_signed_packets': len(signed)}}


def score_reference(execution, observation, assessment):
    def compare(expected, predicted):
        expected, predicted = set(expected), set(predicted)
        n = len(expected & predicted)
        return {'matched': n, 'expected': len(expected), 'predicted': len(predicted),
                'false_positive': len(predicted - expected),
                'recall': n / len(expected) if expected else None,
                'precision': n / len(predicted) if predicted else None}
    reference = execution['reference']
    return {'verified_routes': compare(map(digest, reference['routes']), map(digest, assessment['verified_routes'])),
            'estimated_routes': compare(map(digest, reference['routes']), map(digest, assessment['unverified_route_estimates'])),
            'source_identity': compare(reference['sources'].items(), assessment['sources'].items()),
            'completed_action_questions': len(observation['questions']),
            'proven_notice_then_use': sum(v == 'violation' for v in assessment['findings'].values()),
            'undetermined': sum(v == 'undetermined' for v in assessment['findings'].values()),
            'duty_accuracy': None, 'duty_accuracy_reason': 'no_independent_historical_duty_labels',
            'rejected_evidence': len(assessment['rejected_evidence']),
            'observation_bytes': len(canonical(observation)), 'new_model_calls': 0, 'new_tokens': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows, manifest, provenance = [], {}, []
    def write(name, data):
        path = args.output / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for n, path in enumerate(args.trace):
        data = path.read_bytes()
        execution = import_trace(json.loads(data))
        provenance.append({'source_path': str(path), 'source_sha256': hashlib.sha256(data).hexdigest(),
                           'execution_id': execution['execution_id'], **execution['provenance']})
        write(f'{n}_reference.json', {'execution_id': execution['execution_id'], 'reference': execution['reference']})
        for view in VIEWS:
            for fault in FAULTS:
                o = project(execution, view, fault)
                a = audit(o)
                stem = f'{n}_{view}_{fault}'
                write(stem + '_observation.json', o)
                write(stem + '_audit.json', a)
                rows.append({'trace_index': n, 'view': view, 'fault': fault,
                             'execution_id': execution['execution_id'],
                             'observation_changed_by_fault': o != project(execution, view),
                             **score_reference(execution, o, a)})
    write('metrics.json', rows)
    write('provenance.json', provenance)
    write('manifest.json', dict(manifest))
    lines = ['# 真实模型历史轨迹：固定证据消融\n',
             '只重放公开证据，没有重新执行 Agent、没有新模型调用，也没有重签历史证据。',
             '路线分母是控制器归档的已接受交接，来源分母是归档根签名身份；不是外部独立物理真值。',
             '历史归档没有独立责任标签，因此责任准确率、误指控率和正确 abstention 率均不计算。\n',
             '|轨迹|视图|可证路线|日志估计|来源身份|可证先收到再使用|待定动作|',
             '|---|---|---|---|---|---|---|']
    for r in rows:
        if r['fault'] != 'none':
            continue
        count = lambda k: str(r[k]['matched']) + '/' + str(r[k]['expected'])
        lines.append(f"|{r['trace_index']}|{r['view']}|{count('verified_routes')}|{count('estimated_routes')}|{count('source_identity')}|{r['proven_notice_then_use']}|{r['undetermined']}|")
    lines += ['\n这些视图共享执行轨迹，不是独立样本，也不是策略间因果比较。',
              'undetermined 不等于无责。可证先收到再使用仅针对本地签收撤销义务，不覆盖事实争议或法律责任。',
              '完整批次可能嵌套其他证据；消融必要时删除整批，不能修改签名包字段。',
              '来源文件 SHA256 记录于 provenance.json；导入校验控制器链及原始嵌套签名。']
    (args.output / 'report.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'traces': len(args.trace), 'projections': len(rows), 'new_model_calls': 0}))


if __name__ == '__main__':
    main()
