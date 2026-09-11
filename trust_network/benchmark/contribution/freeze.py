"""Same discovery and task tape, independently varied notice/freeze scope.

Coarse freeze is an explicit benchmark comparator, triggered only by a verified
local revocation. It is not implemented by relabeling successful effects.
"""
from trust_network.benchmark.containment import fixture, OWNERS, AUTHORITIES
from trust_network.benchmark.bus import MessageBus
from trust_network.demo.claim_channel import ClaimGateway, issue
from trust_network.demo.documents import digest, canonical
from trust_network.demo.propagation_notice import (
    prepare_handoff, accept_handoff, acknowledge_handoff,
    accept_notice, acknowledge_notice, pending_notifications,
)


def provision(seed=0):
    f = fixture('active', seed)
    nodes = {o: ClaimGateway(o, f['keys'][o], f['public'], f['workflow'], AUTHORITIES)
             for o in OWNERS}
    routes = []

    def send(sender, receiver, packet):
        nodes[sender].receive(packet)
        handoff = prepare_handoff(nodes[sender], receiver, [digest(packet)])
        receipt = accept_handoff(nodes[receiver], handoff)
        acknowledge_handoff(nodes[sender], receipt)
        routes.append({'handoff': handoff, 'receipt': receipt})

    for order in ('A', 'C'):
        send('source', 'coordinator', f['roots'][order])
        for branch in ('a', 'b'):
            middle, receiver = 'middle_' + branch, 'receiver_' + branch
            send('coordinator', middle, f['trace'][order]['coordinator'])
            send(middle, receiver, f['trace'][order][middle])
    return f, nodes, routes


def run(seed=0, fault='coordinator', notice_scope='routed', freeze_scope='dependency',
        delay=1, deadline=20, edge_delays=None, drop_receivers=()):
    if fault not in ('coordinator', 'middle_a'):
        raise ValueError('unknown fault location')
    if notice_scope not in ('routed', 'broadcast') or freeze_scope not in ('dependency', 'recipient_workload'):
        raise ValueError('unknown factor')
    if deadline < 10 or type(delay) is not int or delay < 0:
        raise ValueError('invalid timeline')
    f, nodes, routes = provision(seed)
    original = f['trace']['A'][fault]
    proof = issue(fault, f['keys'][fault], {'kind': 'revoke', 'workflow': f['workflow'],
                  'target': digest(original), 'original': original})
    tasks = [{'id': order + '_' + branch, 'owner': 'receiver_' + branch,
              'claim': digest(f['trace'][order]['middle_' + branch])}
             for order in ('A', 'C') for branch in ('a', 'b')]
    # Declared causal labels, independent of gate decisions or delivered notices.
    affected = ['A_a', 'A_b'] if fault == 'coordinator' else ['A_a']
    reference = {'tasks': tasks, 'fault': proof, 'discovery_tick': 10,
                 'deadline': deadline, 'routes': routes}
    bus = MessageBus()
    bus.until(10, lambda _: None)
    nodes[fault].receive(proof)
    notified = {fault: 10}
    sent = set()
    edge_delays = edge_delays or {}

    def transport(sender, receiver, packet):
        if receiver in drop_receivers:
            bus.record('drop', sender=sender, receiver=receiver, payload=packet)
            return
        bus.send(sender, receiver, packet, delay=edge_delays.get(sender + '->' + receiver, delay))

    def enqueue():
        for owner, g in nodes.items():
            for p in pending_notifications(g):
                if digest(p) not in sent:
                    sent.add(digest(p))
                    transport(owner, p['body']['recipient'], p)

    def deliver(item):
        g = nodes[item['receiver']]
        if notice_scope == 'routed':
            receipt = accept_notice(g, item['payload'])
            acknowledge_notice(nodes[item['sender']], receipt)
        else:
            receipt = g.receive(item['payload'])
        bus.record('signed_receipt', sender=item['receiver'], receiver=item['sender'], payload=receipt)
        notified.setdefault(g.owner, bus.tick)
        if notice_scope == 'routed':
            enqueue()

    if notice_scope == 'routed':
        enqueue()
    else:
        for owner in OWNERS:
            if owner != fault:
                transport(fault, owner, proof)
    bus.until(deadline, deliver)
    effects, outcomes = [], []
    for task in tasks:
        g = nodes[task['owner']]
        if freeze_scope == 'recipient_workload' and g.owner in notified:
            event = g.record('benchmark_coarse_freeze', task['claim'], [digest(proof)])
            action = 'BLOCKED'
        else:
            try:
                g.execute(task['claim'], 'forward', lambda: effects.append(task['id']))
                action = 'COMPLETED'
            except ValueError:
                action = 'BLOCKED'
            event = g.events[-1]
        outcomes.append({**task, 'action': action, 'event': event})
    unaffected = set(t['id'] for t in tasks) - set(affected)
    errors = set(effects) & set(affected)
    sends = [e for e in bus.events if e['kind'] in ('send', 'drop')]
    receipts = [e for e in bus.events if e['kind'] == 'signed_receipt']
    return {'reference_id': digest(reference), 'reference': reference,
            'factors': {'notice_scope': notice_scope, 'freeze_scope': freeze_scope},
            'truth': {'affected_tasks': affected, 'unaffected_tasks': sorted(unaffected)},
            'outcomes': outcomes, 'effects': effects, 'transport': bus.events,
            'notice_ticks': notified, 'metrics': {
                'unsafe_completion_count': len(errors), 'affected_task_count': len(affected),
                'unsafe_completion_rate': len(errors) / len(affected),
                'affected_tasks_blocked': len(set(affected) - set(effects)),
                'unaffected_tasks_completed': len(unaffected & set(effects)),
                'unaffected_task_count': len(unaffected),
                'unaffected_retention': len(unaffected & set(effects)) / len(unaffected),
                'overfrozen_tasks': len(unaffected - set(effects)),
                'notice_attempts': len(sends), 'notice_receipts': len(receipts),
                'notice_bytes': sum(len(canonical(e['payload'])) for e in sends),
                'receipt_bytes': sum(len(canonical(e['payload'])) for e in receipts),
                'pending_messages_at_deadline': len(bus.queue),
                'verification_calls': 0, 'model_calls': 0, 'tokens': 0},
            'limits': ['deterministic_forward_effects_not_live_model',
                       'coarse_freeze_is_benchmark_comparator',
                       'receipts_are_immediate_reliable_ack_control',
                       'no_recovery_comparison_in_this_axis']}
