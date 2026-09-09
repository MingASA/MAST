"""Evidence-limited claim provenance; not causal settlement or blame scores."""
import argparse
import json
from pathlib import Path
from trust_network.demo.documents import digest
from trust_network.demo.negotiation_worker import verify
from trust_network.demo.negotiation_audit import validate


def trace(directory):
    keys=json.loads((directory/'public_keys.json').read_text()); validate(directory,keys)
    events=json.loads((directory/'events.json').read_text())
    result=json.loads((directory/'result.json').read_text())
    workflow=events[0]['workflow_id']; findings=[]; carrier_offer=None; pending_plan=None
    for index,event in enumerate(events):
        if event['kind']=='request' and event['request']['operation']=='plan':
            # What was actually available at this decision, not later evidence.
            carrier_offer=next((m for m in reversed(event['request'].get('messages',[]))
                                if m['body']['organization']=='carrier'),None)
        if event['kind']!='response': continue
        response=event['response']
        if event['owner']=='buyer' and 'message' in response:
            intent=verify(response['message'],'buyer',keys['buyer'],workflow)
            content=intent['content']; pending_plan=content.get('plan')
            if pending_plan is None or carrier_offer is None: continue
            offer=verify(carrier_offer,'carrier',keys['carrier'],workflow)
            totals={}
            for shipment in pending_plan['shipments']:
                service=shipment['service']; totals[service]=totals.get(service,0)+shipment['cost']
            for service,amount in totals.items():
                quote=offer['content']['services'].get(service)
                if quote is None: classification='unsupported_service_claim'
                elif amount!=quote['price']: classification='buyer_transformation_disagrees_with_received_quote'
                else: classification='consistent_with_received_quote'
                findings.append({'event_index':index,'owner':'buyer','service':service,'claimed_price':amount,
                    'received_price':quote['price'] if quote else None,'classification':classification,
                    'buyer_message_hash':digest(response['message']),'carrier_offer_hash':digest(carrier_offer),
                    'plan_hash':digest(pending_plan),'decision_action':content['action'],
                    'later_owner_denial':False})
        receipt=response.get('commitment')
        if receipt and receipt['body']['owner']=='carrier' and receipt['body']['status']=='denied':
            if pending_plan is not None:
                for finding in findings:
                    if finding['plan_hash']==digest(pending_plan):
                        finding['later_owner_denial']=True
                        finding['denial_hash']=digest(receipt)
                        finding['denial_reasons']=receipt['body']['reasons']
    for finding in findings:
        finding['executed_final_plan']=(result['outcome']=='completed' and result['final_plan'] is not None
                                      and digest(result['final_plan'])==finding['plan_hash'])
        if finding['classification']=='consistent_with_received_quote' and finding['later_owner_denial']:
            finding['responsibility_limit']='later denial alone cannot establish who caused the change or a duty violation'
        else:
            finding['responsibility_limit']='provenance evidence does not establish intent, financial liability or causal loss'
    return {'run':directory.name,'findings':findings,
            'unobservable':['unlogged private updates','notification duties absent an agreed contract','mental intent'],
            'settlement':'no numeric responsibility assigned; existing mathematical model requires explicit likelihoods and duty assumptions'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('root',type=Path); args=parser.parse_args()
    rows=[trace(p.parent) for p in sorted(args.root.glob('*/result.json'))]
    (args.root/'claim_responsibility.json').write_text(json.dumps(rows,indent=2))
    counts={}
    for row in rows:
        for finding in row['findings']:
            k=finding['classification']; counts[k]=counts.get(k,0)+1
    print(json.dumps({'runs':len(rows),'claim_instances':counts}))
