"""Condition-stratified results with completion denominators kept explicit."""
import argparse
import hashlib
import json
from pathlib import Path
from trust_network.demo.analyze_selective import analyze


def summarize(root):
    manifest = json.loads((root/'manifest.json').read_text())
    analyze(root, Path(manifest['case']))
    detailed = json.loads((root/'analysis.json').read_text())['records']
    cells = {}
    for record in detailed:
        repeat, condition, policy = record['run'].split('-', 2)
        key = condition+':'+policy
        cell = cells.setdefault(key, {'runs': 0, 'safe_completed': 0, 'unsafe_completed': 0,
            'rejected': 0, 'runtime_errors': 0, 'queries': 0, 'api_calls': 0, 'tokens': 0,
            'buyer_turns': 0, 'denials': 0})
        cell['runs'] += 1
        for name in ('safe_completed','queries','api_calls','tokens','buyer_turns','denials'):
            cell[name] += record[name]
        cell['unsafe_completed'] += record['unsafe_completion']
        cell['rejected'] += record['outcome'] == 'buyer_rejected'
        cell['runtime_errors'] += record['outcome'] == 'runtime_error'
    for cell in cells.values():
        cell['safe_completion_rate'] = cell['safe_completed']/cell['runs']
        cell['unsafe_completion_rate'] = cell['unsafe_completed']/cell['runs']
        cell['tokens_per_safe_completion'] = cell['tokens']/cell['safe_completed'] if cell['safe_completed'] else None
    expected = {f'{r}-{c}-{p}' for r in range(manifest['repeats'])
                for c in manifest['conditions'] for p in manifest['policies']}
    observed = {r['run'] for r in detailed}
    source_changes = [name for name, checksum in manifest['source_hashes'].items()
                      if not Path(name).exists() or hashlib.sha256(Path(name).read_bytes()).hexdigest()!=checksum]
    result = {'completed_runs': len(observed), 'expected_runs': len(expected),
              'batch_complete': observed == expected, 'pending_cells': sorted(expected-observed),
              'source_changes': source_changes, 'cells': cells,
              'interpretation': 'partial results are provisional; never drop rejected or failed runs'}
    (root/'comparison.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('root', type=Path)
    args = parser.parse_args(); print(json.dumps(summarize(args.root)))
