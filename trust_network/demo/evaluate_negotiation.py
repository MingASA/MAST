"""Post-run scientific diagnostics; private-state oracle never feeds the runtime."""
from itertools import product
from pathlib import Path
import argparse
import json
from trust_network.demo.negotiation import OWNERS, owner_check, inspect


def candidate_oracle(public,private):
    """Enumerate this fixture's two indivisible lots, not arbitrary logistics."""
    lots=list(private['supplier']['lots'].items())
    services=private['carrier']['services']
    candidates=[]
    for assignments in product(services,repeat=len(lots)):
        rows=[]; charged=set()
        for (lot,stock),name in zip(lots,assignments):
            service=services[name]
            rows.append({'lot':lot,'quantity':stock['quantity'],'dispatch_day':service['dispatch_day'],
                'service':name,'arrival_day':service['arrival_day'],
                'cost':0 if name in charged else service['price']})
            charged.add(name)
        plan={k:public[k] for k in ('transaction','model','quantity')}; plan['shipments']=rows
        if all(not owner_check(org,private[org],plan) for org in OWNERS): candidates.append(plan)
    return candidates


def score(plan,buyer):
    preferences=buyer['preferences']; price=sum(row['cost'] for row in plan['shipments'])
    early=sum(row['quantity'] for row in plan['shipments'] if row['arrival_day']<=preferences['early_day'])
    priority=min(early,preferences['early_quantity'])
    return (price,-priority) if preferences['priority']=='minimize_freight' else (-priority,price)


def evaluate(root,cases):
    rows=json.loads((root/'results.json').read_text()); diagnostics=[]
    for row in rows:
        folder=root/row['case']; case=cases/row['case']
        private={org:json.loads((case/org/'state.json').read_text()) for org in OWNERS}
        public=json.loads((case/'public.json').read_text())
        events=json.loads((folder/'events.json').read_text())
        buyer_drafts=[e['response']['message']['body']['content']['plan'] for e in events
            if e['kind']=='response' and e['owner']=='buyer' and 'message' in e['response']
            and e['response']['message']['body']['content']['action']=='propose']
        errors=[{org:list(owner_check(org,private[org],plan)) for org in OWNERS} for plan in buyer_drafts]
        denials=[e['response']['commitment']['body'] for e in events if e['kind']=='response'
                 and 'commitment' in e['response'] and e['response']['commitment']['body']['status']=='denied']
        candidates=candidate_oracle(public,private)
        best=min(candidates,key=lambda plan:score(plan,private['buyer'])) if candidates else None
        final=row['final_plan']; safe=False
        if row['outcome']=='completed':
            receipt=json.loads((folder/'execution.json').read_text())['receipt']
            keys=json.loads((folder/'public_keys.json').read_text())
            for commitment in receipt['commitments']:
                owner=commitment['body']['owner']
                assert inspect(owner,keys[owner],final,receipt['workflow_id'],commitment,receipt['committed_at'])=='approved'
            assert {c['body']['owner'] for c in receipt['commitments']}==set(OWNERS)
            safe=all(not owner_check(org,private[org],final) for org in OWNERS)
        diagnostics.append({'case':row['case'],'outcome':row['outcome'],
            'proposed_plans':len(buyer_drafts),'proposal_constraint_errors':errors,
            'denials':denials,'final_feasible':safe if row['outcome']=='completed' else None,
            'final_score':score(final,private['buyer']) if row['outcome']=='completed' else None,
            'oracle_score':score(best,private['buyer']) if best else None,
            'oracle_note':'Post-run full-private-state enumeration, two indivisible lots only; not visible to agents',
            'final_freight':sum(s['cost'] for s in final['shipments']) if row['outcome']=='completed' else None})
    (root/'diagnostics.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2))
    return diagnostics


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--cases',type=Path,default=Path('examples/negotiation_v6')); args=parser.parse_args()
    print(json.dumps(evaluate(args.out,args.cases),ensure_ascii=False,indent=2))
