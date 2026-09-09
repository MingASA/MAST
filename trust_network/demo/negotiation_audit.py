"""Reconstruct a sealed negotiation from public messages and commitments only."""
from pathlib import Path
import json
from trust_network.demo.documents import Certificate, digest
from trust_network.demo.negotiation import CommitmentBook, OWNERS
from trust_network.demo.negotiation_worker import verify


def validate(out,public_keys):
    result=json.loads((out/'result.json').read_text()); unsigned=dict(result)
    try: seal=Certificate(**unsigned.pop('seal'))
    except (KeyError,TypeError): raise ValueError('unsealed pilot result; not independently certified') from None
    if (seal.issuer!='runtime' or tuple(seal.checks)!=('negotiation_audit_result',) or
            not seal.verify(public_keys['runtime'],unsigned,1)):
        raise ValueError('invalid result seal')
    events=json.loads((out/'events.json').read_text())
    if digest(events)!=result['audit_root']: raise ValueError('audit changed or truncated')
    start=events[0]; workflow=start['workflow_id']; public=start['public_request']
    if result['binding_mode']!=start['binding_mode']: raise ValueError('binding mode changed')
    protocol=start.get('protocol',start['binding_mode'])
    if result.get('protocol',result['binding_mode'])!=protocol: raise ValueError('protocol changed')
    book=CommitmentBook(public_keys,workflow,start['binding_mode'])
    pending=None; calls=0; api=0; tokens=0; queries=0; last_plan=None; buyer_decision=None
    offered={}; rejected=False; failed=False
    for event in events[1:]:
        if event['kind']=='request':
            if pending is not None: raise ValueError('request without prior response or failure')
            pending=event; request=event['request']; owner=event['owner']
            if request['workflow_id']!=workflow or request['public_request']!=public:
                raise ValueError('request crossed workflow or order')
            if request['operation']=='offer':
                if owner not in ('supplier','carrier'): raise ValueError('invalid offer owner')
                if owner=='carrier' and 'supplier' not in offered: raise ValueError('carrier before supplier')
            elif request['operation']=='plan':
                if owner!='buyer' or set(offered)!= {'supplier','carrier'}:
                    raise ValueError('buyer plan without required offers')
            elif request['operation']=='attest':
                if owner not in OWNERS or buyer_decision is None or digest(request['plan'])!=digest(last_plan):
                    raise ValueError('commitment request lacks current buyer proposal')
                if request['buyer_decision']!=buyer_decision: raise ValueError('wrong buyer decision')
            else: raise ValueError('unknown operation')
            if request['operation']!='attest':
                calls+=1
                for message in request.get('messages',[]):
                    sender=message['body']['organization']
                    if message!=offered.get(sender): raise ValueError('unrecorded offer in model context')
        elif event['kind']=='response':
            if pending is None or event['owner']!=pending['owner']: raise ValueError('response without matching request')
            owner=event['owner']; request=pending['request']; response=event['response']
            api+=response.get('usage',{}).get('attempts',0); tokens+=response.get('usage',{}).get('total_tokens',0)
            if request['operation']=='attest':
                book.add(owner,last_plan,response['commitment'],event['received_at']); queries+=1
            elif 'message' in response:
                body=verify(response['message'],owner,public_keys[owner],workflow)
                if body['request_id']!=request['request_id'] or body['input_hash']!=digest(request):
                    raise ValueError('signed response input mismatch')
                if request['operation']=='offer': offered[owner]=response['message']
                else:
                    content=body['content']; rejected=content['action']=='reject'
                    if content['action'] in ('propose','verify'):
                        last_plan=content['plan']; buyer_decision=response['message']
            elif 'rejected_draft' not in response: raise ValueError('response has no business outcome')
            pending=None
        elif event['kind']=='error': failed=True; pending=None
        else: raise ValueError('unknown audit event')
    if pending is not None: raise ValueError('unfinished request without recorded error')
    for field,value in {'actor_call_attempts':calls,'logged_api_requests':api,'tokens':tokens,
                        'commitment_queries':queries,'final_plan':last_plan}.items():
        if result[field]!=value: raise ValueError('result counters or plan differ from audit')
    execution=out/'execution.json'
    if result['outcome']=='completed':
        if failed or rejected or not execution.exists(): raise ValueError('completion inconsistent with trace')
        saved=json.loads(execution.read_text())
        if digest(saved)!=result['execution_hash']: raise ValueError('execution receipt changed')
        receipt=saved['receipt']
        if receipt['workflow_id']!=workflow or receipt['plan_hash']!=digest(last_plan) or receipt['plan']!=last_plan:
            raise ValueError('execution uses another plan')
        if buyer_decision['body']['content']['action']!='propose': raise ValueError('execution without buyer instruction')
        if protocol=='autonomous':
            if receipt.get('assurance')!='autonomous' or receipt['commitments']:
                raise ValueError('incorrect autonomous execution record')
        else:
            state=book.required(last_plan,receipt['committed_at'])
            if state['missing'] or state['denied'] or receipt['commitments']!=state['receipts']:
                raise ValueError('execution lacks current commitments')
    elif execution.exists() or result['execution_hash'] is not None:
        raise ValueError('noncompleted run has execution receipt')
    if result['outcome']=='buyer_rejected' and not rejected: raise ValueError('rejection not observed')
    if (result['outcome']=='runtime_error')!=failed: raise ValueError('error status mismatch')
    return {'events':len(events),'verified_messages':len(offered)+int(buyer_decision is not None),
            'commitments_received':queries,'outcome':result['outcome']}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('out',type=Path); args=parser.parse_args()
    print(json.dumps(validate(args.out,json.loads((args.out/'public_keys.json').read_text())),indent=2))
