"""Offline only: python -m trust_network.benchmark.contribution --output NEW_DIR."""
import argparse
import itertools
import json
from pathlib import Path
from trust_network.demo.documents import digest
from .freeze import run
from .forensics import build_execution, project, audit, score, VIEWS, FAULTS, CASES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--audit-observation', type=Path,
                        help='Audit a public observation JSON only; no truth or model required')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.audit_observation:
        observation = json.loads(args.audit_observation.read_text())
        assessment = audit(observation)
        (args.output / 'assessment.json').write_text(json.dumps(assessment, indent=2) + '\n')
        return
    manifest, freeze_rows, audit_rows = {}, [], []
    def write(name, value):
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        manifest[name] = digest(value)
    for fault, notice, scope in itertools.product(
            ('coordinator', 'middle_a'), ('routed', 'broadcast'), ('dependency', 'recipient_workload')):
        result = run(args.seed, fault, notice, scope)
        name = f'freeze_{fault}_{notice}_{scope}.json'
        write(name, result)
        freeze_rows.append({'file': name, 'fault': fault, **result['factors'],
                            'reference_id': result['reference_id'], **result['metrics']})
    for case in CASES:
        execution = build_execution(args.seed, case)
        write(f'execution_{case}.json', execution)
        for view, fault in itertools.product(VIEWS, FAULTS):
            observation = project(execution, view, fault)
            assessment = audit(observation)
            metrics = score(execution, observation, assessment)
            stem = f'audit_{case}_{view}_{fault}'
            write(stem + '_observation.json', observation)
            write(stem + '_assessment.json', assessment)
            audit_rows.append({'case': case, 'view': view, 'fault': fault,
                               'execution_id': execution['execution_id'],
                               'observation_changed_by_fault': observation != project(execution, view), **metrics})
    write('metrics.json', {'freeze': freeze_rows, 'forensics': audit_rows,
                          'model_calls': 0, 'tokens': 0})
    write('manifest.json', dict(manifest))
    (args.output / 'README.md').write_text(
        '# Contribution infrastructure smoke run\n\n'
        '8 freeze conditions; 140 evidence projections of 5 fixed synthetic executions. '
        'These are deterministic controls, not independent statistical samples or live outcomes.\n\n'
        'Freeze reference IDs must match within fault location. Forensic execution IDs must '
        'match within case. Observation files alone go to the auditor; execution files contain '
        'evaluator-only truth. Manifest hashes are canonical JSON digests.\n\n'
        'No paid calls. Unsigned route estimates and signed route proof are scored separately. '
        'Undetermined never counts as detected violation. Source identity is not factual or legal blame.\n')
    print(json.dumps({'output': str(args.output), 'freeze_conditions': len(freeze_rows),
                      'evidence_conditions': len(audit_rows), 'model_calls': 0}))


if __name__ == '__main__':
    main()
