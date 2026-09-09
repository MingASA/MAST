"""Signed, recoverable resource decision protocol over owner service methods.

Prepared resources intentionally block during coordinator loss. This prototype
assumes one trusted durable decision service, not Byzantine consensus.
"""
from dataclasses import asdict
import json
import sqlite3
from trust_network.demo.documents import Certificate, Decision, digest
from trust_network.demo.negotiation import projection, inspect

RESOURCE_OWNERS = ('supplier', 'carrier')


def signed(owner, body, key):
    return {'body': body, 'signature': asdict(Certificate.issue(
        owner, 1, body, Decision('pass', ('resource_protocol',), (), ''), key))}


def verified(message, owner, public):
    cert = Certificate(**message['signature'])
    if (cert.issuer != owner or cert.action != 'pass' or
            tuple(cert.checks) != ('resource_protocol',) or
            not cert.verify(public, message['body'], 1)):
        raise ValueError('invalid resource protocol signature')
    return message['body']


class ResourceParticipant:
    def __init__(self, store, key, coordinator_public):
        self.store, self.key, self.coordinator_public = store, key, coordinator_public

    def prepare(self, plan, now):
        result = self.store.prepare(plan, now)
        if result['status'] == 'denied': return result
        scope = digest(projection(self.store.owner, plan))
        if result['status'] == 'committed':
            raise ValueError('transaction already committed')
        self.store.transition(plan['transaction'], scope, 'prepare', now)
        return signed(self.store.owner, {'kind': 'prepared', 'transaction': plan['transaction'],
                      'scope_hash': scope}, self.key)

    def decide(self, plan, decision, now):
        body = verified(decision, 'coordinator', self.coordinator_public)
        if (body['kind'] != 'decision' or body['transaction'] != plan['transaction'] or
                body['plan_hash'] != digest(plan) or body['action'] not in ('commit', 'abort')):
            raise ValueError('decision scope mismatch')
        scope = digest(projection(self.store.owner, plan))
        status = self.store.transition(plan['transaction'], scope, body['action'], now)
        return signed(self.store.owner, {'kind': 'ack', 'transaction': plan['transaction'],
                      'decision_hash': digest(decision), 'status': status}, self.key)


class ResourceCoordinator:
    """Public evidence only. No participant private registry or signing key."""
    def __init__(self, path, key, public_keys):
        self.path, self.key, self.public_keys = path, key, public_keys
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS decisions (tx TEXT PRIMARY KEY, message TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS acknowledgments (tx TEXT, owner TEXT, message TEXT, PRIMARY KEY(tx, owner))')

    def decide(self, plan, votes, buyer_receipt, workflow_id, now, action='commit', *, buyer_decision=None):
        if action not in ('commit', 'abort'): raise ValueError('invalid decision')
        if action == 'commit':
            from trust_network.demo.negotiation_worker import verify
            if buyer_decision is None: raise ValueError('signed buyer execution request required')
            intent = verify(buyer_decision, 'buyer', self.public_keys['buyer'], workflow_id)
            if intent['content']['action'] != 'propose' or digest(intent['content']['plan']) != digest(plan):
                raise ValueError('buyer did not request this execution')
            if inspect('buyer', self.public_keys['buyer'], plan, workflow_id, buyer_receipt, now) != 'approved':
                raise ValueError('buyer has not authorized plan')
            if set(votes) != set(RESOURCE_OWNERS): raise ValueError('missing prepared participant')
            for owner in RESOURCE_OWNERS:
                vote = verified(votes[owner], owner, self.public_keys[owner])
                if vote != {'kind': 'prepared', 'transaction': plan['transaction'],
                            'scope_hash': digest(projection(owner, plan))}:
                    raise ValueError('prepared vote scope mismatch')
        body = {'kind': 'decision', 'transaction': plan['transaction'], 'plan_hash': digest(plan),
                'action': action, 'votes': votes, 'buyer_receipt': buyer_receipt, 'workflow_id': workflow_id,
                'buyer_decision': buyer_decision, 'decided_at': now}
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT message FROM decisions WHERE tx=?', (plan['transaction'],)).fetchone()
            if old:
                message = json.loads(old[0])
                comparable = dict(body, decided_at=message['body'].get('decided_at', now))
                if message['body'] != comparable: raise ValueError('durable decision cannot change')
                return message
            message = signed('coordinator', body, self.key)
            db.execute('INSERT INTO decisions VALUES (?, ?)', (plan['transaction'], json.dumps(message)))
            return message

    def recover(self, transaction):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT message FROM decisions WHERE tx=?', (transaction,)).fetchone()
        if row is None: raise ValueError('no durable decision')
        return json.loads(row[0])

    def acknowledge(self, transaction, owner, message):
        if owner not in RESOURCE_OWNERS: raise ValueError('unknown participant')
        decision = self.recover(transaction)
        body = verified(message, owner, self.public_keys[owner])
        expected = 'committed' if decision['body']['action'] == 'commit' else 'released'
        if body != {'kind': 'ack', 'transaction': transaction,
                    'decision_hash': digest(decision), 'status': expected}:
            raise ValueError('acknowledgment mismatch')
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT OR REPLACE INTO acknowledgments VALUES (?, ?, ?)',
                       (transaction, owner, json.dumps(message)))

    def status(self, transaction):
        decision = self.recover(transaction)
        with sqlite3.connect(self.path) as db:
            acknowledged = {r[0] for r in db.execute('SELECT owner FROM acknowledgments WHERE tx=?', (transaction,))}
        required = set(RESOURCE_OWNERS) if decision['body']['action'] == 'commit' else set(decision['body']['votes'])
        if not required.issubset(acknowledged): return 'recovery_pending'
        return 'completed' if decision['body']['action'] == 'commit' else 'aborted'


def execute_resource_plan(coordinator, call, plan, buyer_decision, workflow_id, now):
    """Runtime gate for a signed Agent proposal; call targets organization services.

    Transport errors propagate: the caller must preserve the coordinator journal
    and report recovery_pending, never substitute a successful execution.
    """
    from trust_network.demo.negotiation_worker import verify
    intent = verify(buyer_decision, 'buyer', coordinator.public_keys['buyer'], workflow_id)
    if intent['content']['action'] != 'propose' or digest(intent['content']['plan']) != digest(plan):
        raise ValueError('buyer did not request this execution')
    buyer = call('buyer', 'attest', plan=plan, buyer_decision=buyer_decision)['commitment']
    if inspect('buyer', coordinator.public_keys['buyer'], plan, workflow_id, buyer, now()) != 'approved':
        return {'status': 'buyer_denied', 'buyer_receipt': buyer}
    votes = {}
    denied = None
    for owner in RESOURCE_OWNERS:
        response = call(owner, 'resource_prepare', plan=plan)['resource']
        if response.get('status') == 'denied':
            denied = {'owner': owner, 'response': response}
            break
        votes[owner] = response
    decision = coordinator.decide(plan, votes, buyer, workflow_id, now(),
                                  action='abort' if denied else 'commit',
                                  buyer_decision=buyer_decision)
    for owner in votes:
        acknowledgment = call(owner, 'resource_decide', plan=plan, decision=decision)['resource']
        coordinator.acknowledge(plan['transaction'], owner, acknowledgment)
    return {'status': coordinator.status(plan['transaction']), 'decision': decision, 'denial': denied}
