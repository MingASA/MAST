"""Balanced comparison across unchanged, single-change and multi-change workflows."""
import argparse
import hashlib
import json
from pathlib import Path
from trust_network.demo.run_negotiation import run_case


def execute(out, case, env_file, repeats):
    out.mkdir(parents=True, exist_ok=False)
    policies = ('autonomous', 'full', 'frontier')
    conditions = ('unchanged', 'rate', 'multi')
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('trust_network/demo').glob('*.py')}
    manifest = {'policies': policies, 'conditions': conditions, 'repeats': repeats,
                'case': str(case), 'source_hashes': sources,
                'shared_repair_envelope': True, 'controlled_events': True,
                'cases': {str(p.relative_to(case)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in case.rglob('*') if p.is_file()},
                'max_buyer_turns': 3, 'note': 'exploratory balanced comparison; all failed runs retained'}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    records = []
    for repeat in range(repeats):
        for i, condition in enumerate(conditions):
            offset = (repeat+i) % len(policies)
            for policy in policies[offset:]+policies[:offset]:
                name = f'{repeat}-{condition}-{policy}'
                result = run_case(case, out/name, env_file, autonomous=policy=='autonomous',
                    binding_mode='full' if policy=='full' else 'dependency',
                    rate_update=condition!='unchanged', supply_update=condition=='multi',
                    repair_mode=True, frontier=policy=='frontier')
                record = {'run': name, 'repeat': repeat, 'condition': condition, 'policy': policy,
                          **{k: result[k] for k in ('outcome','tokens','commitment_queries','logged_api_requests')}}
                records.append(record)
                (out/'records.json').write_text(json.dumps(records, indent=2))
                print(json.dumps(record), flush=True)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', type=Path, default=Path('examples/negotiation_v6/economy'))
    parser.add_argument('--env-file', type=Path, default=Path('/home/cjy/cyberagent/.env'))
    parser.add_argument('--repeats', type=int, default=2); parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.repeats < 1: parser.error('positive repeats required')
    if args.execute: execute(args.out, args.case, args.env_file, args.repeats)
    else: print(json.dumps({'runs': args.repeats*9, 'real_api': False,
                           'comparison': 'same repair message, vary execution verification policy'}))
