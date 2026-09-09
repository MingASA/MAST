"""Post-run paired trace replay; no new model calls or online truth access."""
from pathlib import Path
from hashlib import sha256
import json
from trust_network.demo.documents import digest
from trust_network.demo.negotiation import OWNERS, projection, owner_check
from trust_network.demo.negotiation_audit import validate


def analyze(root,cases):
    records=json.loads((root/'records.json').read_text())
    manifest=json.loads((root/'manifest.json').read_text())
    expected={(rep,case,mode) for rep in range(manifest['repeats']) for case in manifest['cases']
              for mode in ('full','dependency')}
    actual=[(r['repeat'],r['case'],r['binding_mode']) for r in records]
    if len(actual)!=len(expected) or set(actual)!=expected: raise ValueError('missing or repeated cells')
    traces=[]; audited=0
    for row in records:
        folder=root/f"repeat_{row['repeat']}"/row['case']/row['binding_mode']
        checked=validate(folder,json.loads((folder/'public_keys.json').read_text())); audited+=checked['events']
        events=json.loads((folder/'events.json').read_text())
        proposals=[e['response']['message']['body']['content']['plan'] for e in events
            if e['kind']=='response' and e['owner']=='buyer' and 'message' in e['response']
            and e['response']['message']['body']['content']['action']=='propose']
        private={o:json.loads((cases/row['case']/o/'state.json').read_text()) for o in OWNERS}
        counts={}
        for mode in ('full','dependency'):
            cache={}; queries=0
            for plan in proposals:
                for owner in OWNERS:
                    key=(owner,digest(projection(owner,plan,mode)))
                    if cache.get(key)!='approved':
                        queries+=1
                        cache[key]='denied' if owner_check(owner,private[owner],plan) else 'approved'
            counts[mode]=queries
        # In this short static-state batch no commitment expiry occurred; exact
        # observed-mode reproduction is required before reporting paired replay.
        if counts[row['binding_mode']]!=row['commitment_queries']:
            raise ValueError('replay assumptions do not reproduce observed query count')
        traces.append({'repeat':row['repeat'],'case':row['case'],'observed_mode':row['binding_mode'],
                       'accepted_drafts':len(proposals),'replay_queries':counts,
                       'dependency_saving_on_same_trace':counts['full']-counts['dependency']})
    result={'audited_events':audited,'runs':len(records),'trace_replay':traces,
        'same_trace_totals':{mode:sum(t['replay_queries'][mode] for t in traces) for mode in ('full','dependency')},
        'replay_limit':'Fixed observed LLM trajectories and static private checks, no expiry; not a full counterfactual agent experiment.',
        'source_hashes_match_at_analysis':all(Path(p).exists() and sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest['sha256'].items())}
    (root/'analysis.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    print(json.dumps(analyze(Path('results/negotiation_v6_binding_comparison'),Path('examples/negotiation_v6')),indent=2))
