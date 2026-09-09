"""Count intervention opportunities, costs and final constraints without filtering failures."""
import argparse
import json
from pathlib import Path
from trust_network.demo.negotiation import owner_check, OWNERS
from trust_network.demo.negotiation_audit import validate


def analyze(root, case):
    records = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or not (directory/'result.json').exists(): continue
        result = json.loads((directory/'result.json').read_text())
        events = json.loads((directory/'events.json').read_text())
        keys = json.loads((directory/'public_keys.json').read_text())
        validate(directory, keys)
        denies = [e['response']['commitment']['body'] for e in events if e['kind'] == 'response'
                  and e.get('response', {}).get('commitment', {}).get('body', {}).get('status') == 'denied']
        plans = [e for e in events if e['kind'] == 'request' and e['request']['operation'] == 'plan']
        reasons = {}
        if result['final_plan'] is not None:
            for owner in OWNERS:
                private = json.loads((case/owner/'state.json').read_text())
                if owner == 'carrier' and result.get('controlled_event') == 'carrier_rates_plus_100_after_offers':
                    for service in private['services'].values(): service['price'] += 100
                if owner == 'supplier' and result.get('supply_update'):
                    private['lots'] = {name+'_replacement': value for name,value in private['lots'].items()}
                reasons[owner] = list(owner_check(owner, private, result['final_plan']))
        completed = result['outcome'] == 'completed'
        group = result.get('protocol', result['binding_mode']) + ':' + result['verification_schedule']
        records.append({'run': directory.name, 'schedule': group,
            'outcome': result['outcome'], 'unsafe_completion': completed and any(reasons.values()),
            'safe_completed': completed and not any(reasons.values()), 'denials': len(denies),
            'denial_details': denies, 'buyer_turns': len(plans), 'queries': result['commitment_queries'],
            'api_calls': result['logged_api_requests'], 'tokens': result['tokens'], 'final_violations': reasons})
    aggregate = {}
    for schedule in sorted({r['schedule'] for r in records}):
        rows = [r for r in records if r['schedule'] == schedule]
        aggregate[schedule] = {'runs': len(rows), **{k: sum(r[k] for r in rows) for k in
            ('unsafe_completion', 'safe_completed', 'denials', 'buyer_turns', 'queries', 'api_calls', 'tokens')}}
    report = {'records': records, 'aggregate': aggregate,
              'interpretation': 'unpaired natural trajectories; cost differences are not automatically causal'}
    (root/'analysis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return aggregate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('root', type=Path)
    parser.add_argument('--case', type=Path, default=Path('examples/negotiation_v6/economy'))
    args = parser.parse_args(); print(json.dumps(analyze(args.root, args.case)))
