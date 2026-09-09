"""Descriptive intervention-opportunity audit; no counterfactual LLM claims."""
from collections import Counter
from pathlib import Path
import json
from trust_network.demo.contract_protocol import check_contract


def diagnose_v5(root):
    rows=json.loads((root/'records.json').read_text()); output={}
    for row in rows:
        events=[json.loads(line) for line in (root/row['case']/row['policy']/'audit.jsonl').read_text().splitlines()]
        counts=output.setdefault(row['policy'],Counter())
        counts['runs']+=1; request=None
        for event in events:
            if event['kind']=='actor_request': request=event['request']
            if event['kind']!='proposal': continue
            proposal=event['envelope']['body']['proposal']
            counts['proposals']+=1
            counts['action_'+str(proposal.get('action'))]+=1
            if proposal.get('action')!='pass': continue
            evidence=request['evidence_verification']['status']
            counts['pass_with_'+evidence]+=1
            structural=check_contract(event['organization'],request['documents'],proposal,'approved','a'*64)
            if structural.action=='repair': counts['structurally_invalid_pass']+=1
            if evidence!='approved' or structural.action!='allow': counts['gate_opportunity_on_observed_proposal']+=1
        counts['observed_repairs']+=row['repairs']
    return {key:dict(value) for key,value in output.items()}


if __name__=='__main__':
    root=Path('results/contract_v5_minimax_pilot')
    result={'source':str(root),'label':'Observed proposal opportunities, not policy causal effect',
            'policies':diagnose_v5(root)}
    out=Path('results/research'); out.mkdir(exist_ok=True)
    (out/'v5_opportunities.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
