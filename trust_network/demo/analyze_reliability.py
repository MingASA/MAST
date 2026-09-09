"""Offline audit and stratified analysis of the completed 36-run batch."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from trust_network.demo.approval_evaluation import validate_audit


def analyze(out):
    records = json.loads((out / 'records.json').read_text())
    manifest = json.loads((out / 'manifest.json').read_text())
    expected = {(r, f'case_{c:02}', p) for r in range(3) for c in range(1, 5)
                for p in ('autonomous', 'verify_all', 'risk_aware')}
    cells = [(r['repeat'], r['case'], r['policy']) for r in records]
    if len(cells) != 36 or set(cells) != expected:
        raise ValueError('Batch incomplete or duplicate cells')
    details = []
    first_inputs = {}
    audit_events = 0
    for record in records:
        folder = out / f"repeat_{record['repeat']}" / record['case'] / record['policy']
        audit_events += validate_audit(folder, manifest['public_keys'])
        events = [json.loads(line) for line in (folder / 'audit.jsonl').read_text().splitlines()]
        requests = Counter(e['source'] for e in events if e['kind'] == 'evidence_request')
        proposals = [e for e in events if e['kind'] == 'proposal']
        first = next(e['visible_input'] for e in events if e['kind'] == 'actor_request')
        first_inputs.setdefault((record['repeat'], record['case']), []).append(first)
        vetoes = [e for e in events if e['kind'] in ('gate', 'gate_after_evidence')
                  and e['gate']['action'] != 'allow']
        details.append({key: record[key] for key in (
            'repeat', 'temperature', 'case', 'policy', 'status', 'outcome',
            'authorized_truth', 'unsafe_completion', 'safe_completion',
            'approved_but_blocked', 'verification_count', 'verification_cost',
            'evidence_requests', 'logged_api_requests', 'tokens')} | {
                'agent_authority_queries': requests['agent'],
                'policy_authority_queries': requests['policy'],
                'first_action': proposals[0]['decision']['action'] if proposals else 'no_response',
                'non_allow_gate_events': len(vetoes)})
    identical = all(all(item == items[0] for item in items) for items in first_inputs.values())
    if not identical:
        raise ValueError('First visible inputs differ across policies')
    with (out / 'runs.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)
    diagnostics = {}
    for policy in ('autonomous', 'verify_all', 'risk_aware'):
        rows = [r for r in details if r['policy'] == policy]
        diagnostics[policy] = {
            'first_actions': dict(Counter(r['first_action'] for r in rows)),
            **{key: sum(r[key] for r in rows) for key in (
                'agent_authority_queries', 'policy_authority_queries', 'non_allow_gate_events')},
            'case_outcomes': {case: dict(Counter(r['outcome'] for r in rows if r['case'] == case))
                              for case in sorted({r['case'] for r in rows})}}
    result = {'runs': len(records), 'audited_events': audit_events,
              'same_first_visible_input_across_policies': identical,
              'diagnostics': diagnostics}
    (out / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('out', type=Path)
    print(json.dumps(analyze(parser.parse_args().out), ensure_ascii=False, indent=2))
