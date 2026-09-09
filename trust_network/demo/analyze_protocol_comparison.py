"""Outcome, intervention and evidence-trace diagnostics for a completed batch."""
from collections import Counter
from pathlib import Path
from hashlib import sha256
import argparse
import json
from trust_network.demo.negotiation import OWNERS, owner_check
from trust_network.demo.negotiation_audit import validate
from trust_network.demo.documents import digest
from trust_network.demo.evaluate_negotiation import candidate_oracle, score


def analyze(root,cases):
    manifest=json.loads((root/'manifest.json').read_text())
    rows=json.loads((root/'records.json').read_text())
    expected={(rep,case,protocol) for rep in range(manifest['repeats']) for case in manifest['cases'] for protocol in manifest['protocols']}
    cells=[(r['repeat'],r['case'],r['protocol']) for r in rows]
    if len(cells)!=len(expected) or set(cells)!=expected: raise ValueError('incomplete or duplicate experiment cells')
    diagnostics=[]; audits=0
    for row in rows:
        folder=root/f"repeat_{row['repeat']}"/row['case']/row['protocol']
        audits+=validate(folder,json.loads((folder/'public_keys.json').read_text()))['events']
        private={o:json.loads((cases/row['case']/o/'state.json').read_text()) for o in OWNERS}
        public=json.loads((cases/row['case']/'public.json').read_text())
        events=json.loads((folder/'events.json').read_text()); counts=Counter(); evidence_trace=[]
        current=None
        for event in events:
            if event['kind']!='response': continue
            response=event['response']
            if event['owner']=='buyer' and 'message' in response:
                body=response['message']['body']; content=body['content']; action=content['action']
                counts['buyer_'+action]+=1
                if action not in ('propose','verify'): continue
                errors={o:list(owner_check(o,private[o],content['plan'])) for o in OWNERS}
                current={'request_id':body['request_id'],'source_organization':'buyer',
                         'signed_message_hash':digest(response['message']),'action':action,
                         'constraint_violations':{o:v for o,v in errors.items() if v},'signed_denials':[]}
                if any(errors.values()): counts['invalid_'+action]+=1
                evidence_trace.append(current)
            elif 'commitment' in response and response['commitment']['body']['status']=='denied' and current is not None:
                current['signed_denials'].append({'organization':event['owner'],
                    'commitment_hash':digest(response['commitment']),
                    'reasons':response['commitment']['body']['reasons']})
        oracle=candidate_oracle(public,private)
        best=min(oracle,key=lambda p:score(p,private['buyer'])) if oracle else None
        final=row['final_plan'] if row['outcome']=='completed' else None
        diagnostics.append({'case':row['case'],'repeat':row['repeat'],'protocol':row['protocol'],
            'counts':dict(counts),'evidence_trace':evidence_trace,
            'final_score':score(final,private['buyer']) if final else None,
            'oracle_score':score(best,private['buyer']) if best else None,
            'attribution_limit':'Locates signed erroneous proposals and owner refusals; not general causal or legal liability.'})
    output={'runs':len(rows),'audited_events':audits,'diagnostics':diagnostics,
            'source_hashes_match_at_analysis':all(Path(p).exists() and sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest['sha256'].items())}
    (root/'analysis.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--cases',type=Path,default=Path('examples/negotiation_v6')); args=parser.parse_args()
    result=analyze(args.out,args.cases)
    print(json.dumps({k:v for k,v in result.items() if k!='diagnostics'},indent=2))
