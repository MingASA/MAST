"""Reconstruct completed resource executions from public signed evidence only."""
import argparse
import json
from pathlib import Path
from trust_network.demo.documents import digest
from trust_network.demo.negotiation import projection, inspect
from trust_network.demo.negotiation_worker import verify
from trust_network.demo.resource_protocol import verified, RESOURCE_OWNERS


def audit(directory):
    envelope = json.loads((directory/'report.json').read_text())
    public = envelope['body']['public_keys']
    report = verified(envelope, 'coordinator', public['coordinator'])
    events = json.loads((directory/'events.json').read_text())
    if digest(events) != report['events_hash']: raise ValueError('event digest mismatch')
    if report['status'] != 'completed': raise ValueError('this auditor requires a completed execution')
    decision = report['result']['decision']
    body = verified(decision, 'coordinator', public['coordinator'])
    if body['action'] != 'commit' or body['kind'] != 'decision': raise ValueError('not a commit decision')
    intent = verify(body['buyer_decision'], 'buyer', public['buyer'], body['workflow_id'])
    plan = intent['content']['plan']
    if (intent['content']['action'] != 'propose' or digest(plan) != body['plan_hash'] or
            plan['transaction'] != body['transaction']): raise ValueError('execution intent mismatch')
    receipt = body['buyer_receipt']
    # Legacy events contain no receipt/decision time. Verify scope/signature at
    # issuance, but do not invent proof that authorization was current at commit.
    if inspect('buyer', public['buyer'], plan, body['workflow_id'], receipt,
               body.get('decided_at', receipt['body']['issued_at'])) != 'approved': raise ValueError('buyer denial')
    if set(body['votes']) != set(RESOURCE_OWNERS): raise ValueError('missing participant vote')
    for owner in RESOURCE_OWNERS:
        vote = verified(body['votes'][owner], owner, public[owner])
        if vote != {'kind': 'prepared', 'transaction': plan['transaction'],
                    'scope_hash': digest(projection(owner, plan))}: raise ValueError('vote scope mismatch')
    observed_votes = set(); acknowledgments = set(); observed_intent = False; observed_approval = False
    for event in events:
        owner, request, response = event['owner'], event['request'], event['response']
        if request['workflow_id'] != body['workflow_id']: raise ValueError('workflow mismatch')
        if 'message' in response:
            message = verify(response['message'], owner, public[owner], body['workflow_id'])
            if message['input_hash'] != digest(request) or message['request_id'] != request['request_id']:
                raise ValueError('model response request binding mismatch')
            if digest(response['message']) == digest(body['buyer_decision']): observed_intent = True
        if response.get('commitment') == receipt:
            if not observed_intent: raise ValueError('approval precedes execution proposal')
            if digest(request['plan']) != digest(plan): raise ValueError('approval request mismatch')
            observed_approval = True
        if request['operation'] == 'resource_prepare':
            if not observed_approval: raise ValueError('preparation precedes approval')
            if digest(request['plan']) != digest(plan): raise ValueError('prepare request mismatch')
            if response['resource'] != body['votes'].get(owner): raise ValueError('vote not in decision')
            observed_votes.add(owner)
        if request['operation'] == 'resource_decide':
            if observed_votes != set(RESOURCE_OWNERS): raise ValueError('commit precedes full preparation')
            if request['decision'] != decision or digest(request['plan']) != digest(plan):
                raise ValueError('execution request mismatch')
            ack = verified(response['resource'], owner, public[owner])
            if ack != {'kind': 'ack', 'transaction': plan['transaction'],
                       'decision_hash': digest(decision), 'status': 'committed'}:
                raise ValueError('execution acknowledgment mismatch')
            acknowledgments.add(owner)
    if acknowledgments != set(RESOURCE_OWNERS): raise ValueError('missing execution acknowledgment')
    calls = sum(e['response'].get('usage', {}).get('attempts', 0) for e in events)
    tokens = sum(e['response'].get('usage', {}).get('total_tokens', 0) for e in events)
    if (calls, tokens, len(events)) != (report['model_api_calls'], report['tokens'], report['http_calls']):
        raise ValueError('usage mismatch')
    return {'signed_execution_chain_valid': True, 'events': len(events), 'model_calls': calls, 'tokens': tokens,
            'authorization_current_at_decision_proven': 'decided_at' in body,
            'limitations': ['decision time relies on trusted coordinator clock', 'public keys require external trusted provisioning',
                            'signatures do not independently prove owner inventory or honest physical execution']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('directory', type=Path)
    args = parser.parse_args(); result = audit(args.directory)
    (args.directory/'independent_audit.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
