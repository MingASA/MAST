"""Optional postmortem adapter to existing attribution and settlement modules.

This explicitly simplified, single-origin authorization model is not a model of
arbitrary LLM factual errors. It is never called by the online gate.
"""
from dataclasses import asdict
import json
from trust_network.core.graph import Graph,Node,Edge
from trust_network.sim.simulator import Discovery
from trust_network.solve.attribution import Check,Observation,ResponsibilityContext,decode
from trust_network.solve.settlement import CostEvent,ProportionalWithOmission,settle


def postmortem(out,evaluation):
    events=[json.loads(line) for line in (out/'audit.jsonl').read_text().splitlines()]
    config=events[0]['config']; change=events[0]['intake_class']=='change_order'
    prior=config['change_prior'] if change else config['routine_prior']
    loss=config['change_loss'] if change else config['routine_loss']
    visited=list(dict.fromkeys(e['organization'] for e in events if e['kind']=='proposal'))
    receipts={}; costs={o:0. for o in visited}; counts={o:0 for o in visited}; cached=None
    for event in events:
        if event['kind']=='evidence_invalidated': cached=None
        if event['kind']=='proposal' and cached is not None:
            receipts[event['organization']]=cached
        if event['kind']=='evidence_received':
            cached=event['status']; receipts[event['organization']]=cached
        if event['kind']=='evidence_request':
            costs[event['organization']]+=event['charged_cost']; counts[event['organization']]+=1
    if evaluation['status']!='finished' or any(n>1 for n in counts.values()) or 'unknown' in receipts.values():
        return {'supported':False,'reason':'error, repeated measurement or unknown authority response outside binary adapter'}
    source='submitted_claim'; terminal='realized_outcome'
    nodes=[Node(source,'process','seller',alpha=prior)]
    nodes.extend(Node(o,'verify',o,
                      c=0. if o in receipts and not counts[o] else config['verification_cost'],
                      delta=1.,epsilon=0.,mu=0.) for o in visited)
    nodes.append(Node(terminal,'process','fulfillment',L=loss))
    path=[source,*visited,terminal]
    graph=Graph(tuple(nodes),tuple(Edge(a,b) for a,b in zip(path,path[1:])),source)
    checks=[Check(source)]
    checks.extend(Check(o,o in receipts,{'approved':'clear','denied':'flag'}.get(receipts.get(o))) for o in visited)
    checks.append(Check(terminal))
    # Perfect final discovery is a synthetic POST-RUN oracle, not online truth.
    obs=Observation(tuple(checks),'clear' if evaluation['authorized_truth'] else 'flag')
    discovery=Discovery(1.,0.); posterior=decode(graph,obs,discovery)
    context=ResponsibilityContext(obs,config['budget'],discovery)
    forwarded=frozenset(e['organization'] for e in events if e['kind']=='forward')
    rule=ProportionalWithOmission(w_omit=config['omission_weight'],eligible_checks=forwarded)
    cost_events=tuple(CostEvent(o,costs[o],0.,posterior,context) for o in visited)
    cost_events+=(CostEvent(terminal,0.,loss if evaluation['unsafe_completion'] else 0.,posterior,context),)
    result=settle(graph,cost_events,rule)
    return {'supported':True,'model':'single seller-origin authorization error; ideal post-run discovery; only forwarded omissions eligible',
            'scope':'synthetic accounting units, no actual transfer or legal attribution',
            'settlement':asdict(result),'posterior_origin':[{'node':s.origin,'probability':p} for s,p in posterior.mass],
            'forwarded_without_authority_evidence':sorted(forwarded-set(receipts)),
            'note':'Receiving a cached valid certificate is also verification evidence; cached recipients must not be charged omission.'}
