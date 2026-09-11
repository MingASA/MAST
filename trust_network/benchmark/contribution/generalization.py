"""Topology and responsibility generalization benchmark.

The benchmark keeps the production protocol unchanged.  It builds deterministic
signed claim graphs, runs the real ClaimGateway/notification path, and gives the
auditor only projected public observations.  Evaluator labels are kept in the
execution files and are never passed to ``audit``.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from trust_network.benchmark.bus import MessageBus
from trust_network.demo.claim_channel import ClaimGateway, issue
from trust_network.demo.documents import canonical, digest
from trust_network.demo.evidence_order import local_index
from trust_network.demo.propagation_notice import (
    acknowledge_handoff,
    acknowledge_notice,
    accept_handoff,
    accept_notice,
    pending_notifications,
    prepare_handoff,
)
from .forensics import audit as audit_public
from .forensics import route_label


AUTHORITY = {'total_charge': 'source'}
TOPOLOGIES = ('long_chain_fork', 'converge_then_fork', 'reused_org_independent')
FAULTS = ('shared_upstream', 'branch_middle')
TIMINGS = ('all_before_deadline', 'critical_edge_late')
NOTICE_SCOPES = ('routed', 'broadcast')
FREEZE_SCOPES = ('dependency', 'recipient_workload')

RESPONSIBILITY_ACTORS = ('receiver_a', 'receiver_b', 'receiver_c')
RESPONSIBILITY_CASES = (
    'own_notice', 'other_notice', 'late_notice', 'unrelated_notice', 'hold',
)
RESPONSIBILITY_PROJECTIONS = (
    ('full', 'none'),
    ('no_receipts', 'none'),
    ('ordinary_logs', 'none'),
    ('opaque_relay', 'none'),
    ('full', 'missing_relevant_notice'),
    ('full', 'missing_order_node'),
    ('full', 'reorder'),
    ('full', 'conflicting_action'),
)


def _keypair(seed: int, topology: str, owner: str):
    raw = hashlib.sha256(
        f'contribution-generalization-v2:{seed}:{topology}:{owner}'.encode()
    ).digest()
    private = Ed25519PrivateKey.from_private_bytes(raw)
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return private, public


class _TopologyBuilder:
    def __init__(self, topology: str, seed: int):
        self.topology = topology
        self.seed = seed
        self.workflow = f'contribution-generalization-v2:{topology}:{seed}'
        self.organizations = []
        self.keys = {}
        self.public = {}
        self.claims = {}
        self.routes = []
        self.tasks = []
        self.task_paths = {}
        self.fault_claims = {}

    def owner(self, name: str):
        if name not in self.keys:
            private, public = _keypair(self.seed, self.topology, name)
            self.organizations.append(name)
            self.keys[name] = private
            self.public[name] = public
        return name

    def claim(self, name: str, owner: str, parents=(), order: str | None = None):
        self.owner(owner)
        parents = tuple(parents)
        if parents:
            fact = copy.deepcopy(self.claims[parents[0]]['body']['fact'])
            parent_ids = [digest(self.claims[parent]) for parent in parents]
        else:
            if order is None:
                raise ValueError(f'root {name} needs an order')
            fact = {'predicate': 'total_charge',
                    'value': {'order': order, 'currency': 'CNY', 'cents': 100}}
            parent_ids = []
        packet = issue(owner, self.keys[owner], {
            'kind': 'claim', 'workflow': self.workflow, 'parents': parent_ids,
            'rule': 'relay', 'fact': fact,
        })
        self.claims[name] = packet
        return name

    def route(self, sender: str, receiver: str, claims, label: str):
        self.owner(sender)
        self.owner(receiver)
        self.routes.append({'sender': sender, 'receiver': receiver,
                            'claims': list(claims), 'label': label})

    def task(self, task_id: str, owner: str, claim: str, branch: str, paths):
        self.owner(owner)
        self.tasks.append({'id': task_id, 'owner': owner,
                           'claim': digest(self.claims[claim]), 'claim_key': claim,
                           'branch': branch})
        self.task_paths[task_id] = paths

    def finish(self):
        return {
            'topology': self.topology,
            'workflow': self.workflow,
            'organizations': list(self.organizations),
            'public': copy.deepcopy(self.public),
            'claims': copy.deepcopy(self.claims),
            'routes': copy.deepcopy(self.routes),
            'tasks': copy.deepcopy(self.tasks),
            'task_paths': copy.deepcopy(self.task_paths),
            'fault_claims': copy.deepcopy(self.fault_claims),
            'critical_edges': copy.deepcopy(self.critical_edges),
            'keys': self.keys,
        }


def _build_long_chain(seed: int):
    b = _TopologyBuilder('long_chain_fork', seed)
    for owner in ('source', 'chain_1', 'chain_2', 'branch_a', 'branch_b',
                  'receiver_a', 'receiver_b'):
        b.owner(owner)
    b.claim('root_A', 'source', order='A')
    b.claim('root_C', 'source', order='C')
    b.claim('shared_A', 'chain_1', ('root_A',))
    b.claim('shared_C', 'chain_1', ('root_C',))
    b.claim('common_A', 'chain_2', ('shared_A',))
    b.claim('common_C', 'chain_2', ('shared_C',))
    b.claim('branch_A_a', 'branch_a', ('common_A',))
    b.claim('branch_C_a', 'branch_a', ('common_C',))
    b.claim('branch_A_b', 'branch_b', ('common_A',))
    b.claim('branch_C_b', 'branch_b', ('common_C',))
    b.route('source', 'chain_1', ('root_A', 'root_C'), 'source_to_chain_1')
    b.route('chain_1', 'chain_2', ('shared_A', 'shared_C'), 'chain_1_to_chain_2')
    b.route('chain_2', 'branch_a', ('common_A', 'common_C'), 'chain_2_to_branch_a')
    b.route('chain_2', 'branch_b', ('common_A', 'common_C'), 'chain_2_to_branch_b')
    b.route('branch_a', 'receiver_a', ('branch_A_a', 'branch_C_a'), 'branch_a_to_receiver_a')
    b.route('branch_b', 'receiver_b', ('branch_A_b', 'branch_C_b'), 'branch_b_to_receiver_b')
    b.task('A_a', 'receiver_a', 'branch_A_a', 'a',
           {'shared_upstream': ['chain_1', 'chain_2', 'branch_a', 'receiver_a'],
            'branch_middle': ['branch_a', 'receiver_a']})
    b.task('A_b', 'receiver_b', 'branch_A_b', 'b',
           {'shared_upstream': ['chain_1', 'chain_2', 'branch_b', 'receiver_b'],
            'branch_middle': ['branch_b', 'receiver_b']})
    b.task('C_a', 'receiver_a', 'branch_C_a', 'a',
           {'shared_upstream': ['chain_1', 'chain_2', 'branch_a', 'receiver_a'],
            'branch_middle': ['branch_a', 'receiver_a']})
    b.task('C_b', 'receiver_b', 'branch_C_b', 'b',
           {'shared_upstream': ['chain_1', 'chain_2', 'branch_b', 'receiver_b'],
            'branch_middle': ['branch_b', 'receiver_b']})
    b.fault_claims = {'shared_upstream': 'shared_A', 'branch_middle': 'branch_A_a'}
    b.critical_edges = {
        ('shared_upstream', 'routed'): 'chain_1->chain_2',
        ('branch_middle', 'routed'): 'branch_a->receiver_a',
        ('shared_upstream', 'broadcast'): 'chain_1->receiver_a',
        ('branch_middle', 'broadcast'): 'branch_a->receiver_a',
    }
    return b.finish()


def _build_converge(seed: int):
    b = _TopologyBuilder('converge_then_fork', seed)
    for owner in ('source', 'shared_org', 'path_left', 'path_right', 'join',
                  'branch_a', 'branch_b', 'receiver_a', 'receiver_b'):
        b.owner(owner)
    b.claim('root_A', 'source', order='A')
    b.claim('root_C', 'source', order='C')
    b.claim('shared_A', 'shared_org', ('root_A',))
    b.claim('shared_C', 'shared_org', ('root_C',))
    b.claim('left_A', 'path_left', ('shared_A',))
    b.claim('left_C', 'path_left', ('shared_C',))
    b.claim('right_A', 'path_right', ('shared_A',))
    b.claim('right_C', 'path_right', ('shared_C',))
    b.claim('join_A', 'join', ('left_A', 'right_A'))
    b.claim('join_C', 'join', ('left_C', 'right_C'))
    b.claim('branch_A_a', 'branch_a', ('join_A',))
    b.claim('branch_C_a', 'branch_a', ('join_C',))
    b.claim('branch_A_b', 'branch_b', ('join_A',))
    b.claim('branch_C_b', 'branch_b', ('join_C',))
    b.route('source', 'shared_org', ('root_A', 'root_C'), 'source_to_shared')
    b.route('shared_org', 'path_left', ('shared_A', 'shared_C'), 'shared_to_left')
    b.route('shared_org', 'path_right', ('shared_A', 'shared_C'), 'shared_to_right')
    b.route('path_left', 'join', ('left_A', 'left_C'), 'left_to_join')
    b.route('path_right', 'join', ('right_A', 'right_C'), 'right_to_join')
    b.route('join', 'branch_a', ('join_A', 'join_C'), 'join_to_branch_a')
    b.route('join', 'branch_b', ('join_A', 'join_C'), 'join_to_branch_b')
    b.route('branch_a', 'receiver_a', ('branch_A_a', 'branch_C_a'), 'branch_a_to_receiver_a')
    b.route('branch_b', 'receiver_b', ('branch_A_b', 'branch_C_b'), 'branch_b_to_receiver_b')
    b.task('A_a', 'receiver_a', 'branch_A_a', 'a',
           {'shared_upstream': ['shared_org', 'path_left', 'join', 'branch_a', 'receiver_a'],
            'branch_middle': ['branch_a', 'receiver_a']})
    b.task('A_b', 'receiver_b', 'branch_A_b', 'b',
           {'shared_upstream': ['shared_org', 'path_right', 'join', 'branch_b', 'receiver_b'],
            'branch_middle': ['branch_b', 'receiver_b']})
    b.task('C_a', 'receiver_a', 'branch_C_a', 'a',
           {'shared_upstream': ['shared_org', 'path_left', 'join', 'branch_a', 'receiver_a'],
            'branch_middle': ['branch_a', 'receiver_a']})
    b.task('C_b', 'receiver_b', 'branch_C_b', 'b',
           {'shared_upstream': ['shared_org', 'path_right', 'join', 'branch_b', 'receiver_b'],
            'branch_middle': ['branch_b', 'receiver_b']})
    b.fault_claims = {'shared_upstream': 'shared_A', 'branch_middle': 'branch_A_a'}
    b.critical_edges = {
        ('shared_upstream', 'routed'): 'join->branch_a',
        ('branch_middle', 'routed'): 'branch_a->receiver_a',
        ('shared_upstream', 'broadcast'): 'shared_org->receiver_a',
        ('branch_middle', 'broadcast'): 'branch_a->receiver_a',
    }
    return b.finish()


def _build_reused(seed: int):
    b = _TopologyBuilder('reused_org_independent', seed)
    for owner in ('source', 'shared_org', 'branch_a', 'branch_b',
                  'independent_a', 'independent_b', 'reused_receiver',
                  'receiver_b'):
        b.owner(owner)
    b.claim('root_A', 'source', order='A')
    b.claim('root_C_a', 'source', order='C_a')
    b.claim('root_C_b', 'source', order='C_b')
    b.claim('shared_A', 'shared_org', ('root_A',))
    b.claim('branch_A_a', 'branch_a', ('shared_A',))
    b.claim('branch_A_b', 'branch_b', ('shared_A',))
    b.claim('independent_C_a', 'independent_a', ('root_C_a',))
    b.claim('independent_C_b', 'independent_b', ('root_C_b',))
    b.route('source', 'shared_org', ('root_A',), 'source_to_shared')
    b.route('shared_org', 'branch_a', ('shared_A',), 'shared_to_branch_a')
    b.route('shared_org', 'branch_b', ('shared_A',), 'shared_to_branch_b')
    b.route('branch_a', 'reused_receiver', ('branch_A_a',), 'branch_a_to_reused')
    b.route('branch_b', 'reused_receiver', ('branch_A_b',), 'branch_b_to_reused')
    b.route('source', 'independent_a', ('root_C_a',), 'source_to_independent_a')
    b.route('independent_a', 'reused_receiver', ('independent_C_a',), 'independent_a_to_reused')
    b.route('source', 'independent_b', ('root_C_b',), 'source_to_independent_b')
    b.route('independent_b', 'receiver_b', ('independent_C_b',), 'independent_b_to_receiver_b')
    b.task('A_a', 'reused_receiver', 'branch_A_a', 'a',
           {'shared_upstream': ['shared_org', 'branch_a', 'reused_receiver'],
            'branch_middle': ['branch_a', 'reused_receiver']})
    b.task('A_b', 'reused_receiver', 'branch_A_b', 'b',
           {'shared_upstream': ['shared_org', 'branch_b', 'reused_receiver'],
            'branch_middle': ['branch_b', 'reused_receiver']})
    b.task('C_a', 'reused_receiver', 'independent_C_a', 'a',
           {'shared_upstream': ['independent_a', 'reused_receiver'],
            'branch_middle': ['independent_a', 'reused_receiver']})
    b.task('C_b', 'receiver_b', 'independent_C_b', 'b',
           {'shared_upstream': ['independent_b', 'receiver_b'],
            'branch_middle': ['independent_b', 'receiver_b']})
    b.fault_claims = {'shared_upstream': 'shared_A', 'branch_middle': 'branch_A_a'}
    b.critical_edges = {
        ('shared_upstream', 'routed'): 'branch_a->reused_receiver',
        ('branch_middle', 'routed'): 'branch_a->reused_receiver',
        ('shared_upstream', 'broadcast'): 'shared_org->reused_receiver',
        ('branch_middle', 'broadcast'): 'branch_a->reused_receiver',
    }
    return b.finish()


def build_topology(topology: str, seed: int = 0):
    builders = {
        'long_chain_fork': _build_long_chain,
        'converge_then_fork': _build_converge,
        'reused_org_independent': _build_reused,
    }
    try:
        return builders[topology](seed)
    except KeyError as exc:
        raise ValueError(f'unknown topology: {topology}') from exc


def _provision_topology(spec):
    nodes = {owner: ClaimGateway(owner, spec['keys'][owner], spec['public'],
                                 spec['workflow'], AUTHORITY)
             for owner in spec['organizations']}
    routes = []
    for step in spec['routes']:
        sender = nodes[step['sender']]
        packets = [spec['claims'][name] for name in step['claims']]
        for packet in packets:
            sender.receive(packet)
        handoff = prepare_handoff(sender, step['receiver'],
                                  [digest(packet) for packet in packets])
        receipt = accept_handoff(nodes[step['receiver']], handoff)
        acknowledge_handoff(sender, receipt)
        routes.append({'label': step['label'], 'sender': step['sender'],
                       'receiver': step['receiver'], 'handoff': handoff,
                       'receipt': receipt})
    return nodes, routes


def _edge_key(sender, receiver):
    return f'{sender}->{receiver}'


def run_freeze(topology: str, fault: str = 'shared_upstream',
               timing: str = 'all_before_deadline', notice_scope: str = 'routed',
               freeze_scope: str = 'dependency', seed: int = 0,
               discovery_tick: int = 10, deadline: int = 20,
               default_delay: int = 1, late_delay: int = 20):
    if fault not in FAULTS or timing not in TIMINGS or notice_scope not in NOTICE_SCOPES:
        raise ValueError('unknown freeze condition')
    if freeze_scope not in FREEZE_SCOPES:
        raise ValueError('unknown freeze scope')
    if type(default_delay) is not int or default_delay < 0 or type(late_delay) is not int or late_delay < 0:
        raise ValueError('invalid delay')
    if deadline <= discovery_tick:
        raise ValueError('deadline must follow discovery')
    spec = build_topology(topology, seed)
    nodes, routes = _provision_topology(spec)
    fault_claim_key = spec['fault_claims'][fault]
    original = spec['claims'][fault_claim_key]
    fault_owner = original['signature']['issuer']
    proof = issue(fault_owner, spec['keys'][fault_owner], {
        'kind': 'revoke', 'workflow': spec['workflow'],
        'target': digest(original), 'original': original,
    })
    affected = ['A_a', 'A_b'] if fault == 'shared_upstream' else ['A_a']
    all_task_ids = [task['id'] for task in spec['tasks']]
    unaffected = [task_id for task_id in all_task_ids if task_id not in affected]
    critical_edge = spec['critical_edges'][(fault, notice_scope)]
    edge_delays = {}
    if timing == 'critical_edge_late':
        edge_delays[critical_edge] = late_delay
    reference = {
        'topology': topology, 'workflow': spec['workflow'],
        'tasks': spec['tasks'], 'task_paths': spec['task_paths'],
        'fault_claim': proof, 'fault_claim_key': fault_claim_key,
        'discovery_tick': discovery_tick, 'deadline': deadline,
        'routes': [r['handoff'] for r in routes],
    }
    bus = MessageBus()
    bus.until(discovery_tick, lambda _: None)
    nodes[fault_owner].receive(proof)
    bus.record('fault_discovered', owner=fault_owner, target=digest(original),
               fault=fault, topology=topology)
    notified = {fault_owner: discovery_tick}
    arrivals = []
    sent = set()

    def delay_for(sender, receiver):
        return edge_delays.get(_edge_key(sender, receiver), default_delay)

    def enqueue_routed():
        for owner in spec['organizations']:
            for packet in pending_notifications(nodes[owner]):
                notification_id = digest(packet)
                if notification_id in sent:
                    continue
                sent.add(notification_id)
                recipient = packet['body']['recipient']
                bus.send(owner, recipient, packet, delay_for(owner, recipient),
                         notification_kind='routed', target=packet['body']['target'])

    def deliver(item):
        receiver = item['receiver']
        sender = item['sender']
        gateway = nodes[receiver]
        if notice_scope == 'routed':
            receipt = accept_notice(gateway, item['payload'])
            acknowledge_notice(nodes[sender], receipt)
        else:
            receipt = gateway.receive(item['payload'])
        notified.setdefault(receiver, bus.tick)
        arrivals.append({'sender': sender, 'receiver': receiver,
                         'tick': bus.tick, 'target': item.get('target',
                         item['payload']['body'].get('target')),
                         'kind': item.get('notification_kind', notice_scope)})
        bus.record('signed_receipt', sender=receiver, receiver=sender,
                   payload=receipt, notification_kind=item.get('notification_kind', notice_scope),
                   target=item.get('target', item['payload']['body'].get('target')))
        if notice_scope == 'routed':
            enqueue_routed()

    if notice_scope == 'routed':
        enqueue_routed()
    else:
        for owner in spec['organizations']:
            if owner == fault_owner:
                continue
            bus.send(fault_owner, owner, proof, delay_for(fault_owner, owner),
                     notification_kind='broadcast', target=digest(original))
    bus.until(deadline, deliver)
    pending_at_action = len(bus.queue)
    effects = []
    outcomes = []
    for task in spec['tasks']:
        gateway = nodes[task['owner']]
        if freeze_scope == 'recipient_workload' and gateway.owner in notified:
            event = gateway.record('benchmark_coarse_freeze', task['claim'], [digest(proof)])
            action = 'BLOCKED'
        else:
            try:
                gateway.execute(task['claim'], 'forward', lambda task_id=task['id']:
                                effects.append(task_id))
                action = 'COMPLETED'
            except ValueError:
                action = 'BLOCKED'
            event = gateway.events[-1]
        outcomes.append({**task, 'action': action, 'event': event})
    action_tick = bus.tick
    while bus.queue:
        bus.until(max(item[0] for item in bus.queue), deliver)
    task_by_id = {task['id']: task for task in spec['tasks']}
    unsafe = set(effects).intersection(affected)
    unsafe_propagation = []
    for task_id in sorted(unsafe):
        task = task_by_id[task_id]
        path = spec['task_paths'][task_id][fault]
        unsafe_propagation.append({
            'task_id': task_id, 'organization': task['owner'], 'branch': task['branch'],
            'distance': len(path) - 1, 'path': path,
        })
    arrivals_by_edge = {}
    for arrival in arrivals:
        arrivals_by_edge.setdefault(_edge_key(arrival['sender'], arrival['receiver']), []).append(arrival['tick'])
    critical_arrival = (min(arrivals_by_edge[critical_edge])
                        if critical_edge in arrivals_by_edge else None)
    per_target_receiver = {}
    for arrival in arrivals:
        key = (arrival['receiver'], arrival['target'])
        per_target_receiver[key] = per_target_receiver.get(key, 0) + 1
    duplicate_notice_receipts = sum(max(0, count - 1)
                                    for count in per_target_receiver.values())
    sends = [event for event in bus.events if event['kind'] == 'send']
    receipts = [event for event in bus.events if event['kind'] == 'signed_receipt']
    relevant_arrival_by_task = {
        task['id']: notified.get(task['owner']) for task in spec['tasks']
    }
    return {
        'reference_id': digest(reference), 'reference': reference,
        'schedule': {'timing': timing, 'critical_edge': critical_edge,
                     'edge_delays': edge_delays},
        'factors': {'topology': topology, 'fault': fault, 'timing': timing,
                    'notice_scope': notice_scope, 'freeze_scope': freeze_scope},
        'topology': {'organizations': spec['organizations'], 'routes': [r['label'] for r in routes],
                     'task_paths': spec['task_paths']},
        'truth': {'affected_tasks': affected, 'unaffected_tasks': unaffected,
                  'fault_claim_key': fault_claim_key, 'unsafe_completion_is_error': True},
        'outcomes': outcomes, 'effects': effects, 'transport': bus.events,
        'notice_arrivals': arrivals, 'notice_ticks': notified,
        'unsafe_propagation': unsafe_propagation,
        'metrics': {
            'unsafe_completion_count': len(unsafe),
            'affected_task_count': len(affected),
            'unsafe_completion_rate': len(unsafe) / len(affected),
            'affected_tasks_blocked': len(set(affected) - set(effects)),
            'unaffected_tasks_completed': len(set(unaffected).intersection(effects)),
            'unaffected_task_count': len(unaffected),
            'unaffected_retention': len(set(unaffected).intersection(effects)) / len(unaffected),
            'overfrozen_tasks': len(set(unaffected) - set(effects)),
            'notice_attempts': len(sends), 'notice_receipts': len(receipts),
            'notice_bytes': sum(len(canonical(event['payload'])) for event in sends),
            'receipt_bytes': sum(len(canonical(event['payload'])) for event in receipts),
            'notice_arrival_tick_min': min((a['tick'] for a in arrivals), default=None),
            'notice_arrival_tick_max': max((a['tick'] for a in arrivals), default=None),
            'critical_edge': critical_edge, 'critical_edge_arrival_tick': critical_arrival,
            'critical_edge_late_at_action': (critical_arrival is not None and
                                             critical_arrival > deadline),
            'task_notice_ticks': relevant_arrival_by_task,
            'duplicate_notice_receipts': duplicate_notice_receipts,
            'pending_messages_at_action': pending_at_action,
            'action_tick': action_tick,
            'post_action_tick': bus.tick,
            'model_calls': 0, 'tokens': 0,
        },
        'limits': [
            'deterministic_claim_graph_and_action_effects',
            'coarse_freeze_is_benchmark_comparator',
            'broadcast_is_direct_revoke_delivery',
            'reliable_ack_control_channel',
            'no_recovery_comparison_in_this_axis',
            'no_seed_based_independence_claim',
        ],
    }


def _responsibility_keypair(seed: int, actor: str, case: str, owner: str):
    raw = hashlib.sha256(
        f'contribution-responsibility-v2:{seed}:{actor}:{case}:{owner}'.encode()
    ).digest()
    private = Ed25519PrivateKey.from_private_bytes(raw)
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return private, public


def build_responsibility_execution(actor: str, case: str, seed: int = 0):
    if actor not in RESPONSIBILITY_ACTORS or case not in RESPONSIBILITY_CASES:
        raise ValueError('unknown responsibility actor or case')
    owners = ('source', 'relay', *RESPONSIBILITY_ACTORS)
    keys = {}
    public = {}
    for owner in owners:
        keys[owner], public[owner] = _responsibility_keypair(seed, actor, case, owner)
    workflow = f'contribution-responsibility-v2:{actor}:{case}:{seed}'
    gateways = {owner: ClaimGateway(owner, keys[owner], public, workflow, AUTHORITY)
                for owner in owners}

    def claim(owner, order, parents=()):
        fact = ({'predicate': 'total_charge',
                 'value': {'order': order, 'currency': 'CNY', 'cents': 100}}
                if not parents else copy.deepcopy(claim_packets[parents[0]]['body']['fact']))
        packet = issue(owner, keys[owner], {
            'kind': 'claim', 'workflow': workflow,
            'parents': [digest(claim_packets[parent]) for parent in parents],
            'rule': 'relay', 'fact': fact,
        })
        claim_packets[f'{owner}:{order}'] = packet
        return packet

    claim_packets = {}
    root_a = claim('source', 'A')
    root_b = claim('source', 'B')
    derived_a = claim('relay', 'A', ('source:A',))
    derived_b = claim('relay', 'B', ('source:B',))
    routes = []

    def route(sender, receiver, packet):
        gateways[sender].receive(packet)
        handoff = prepare_handoff(gateways[sender], receiver, [digest(packet)])
        receipt = accept_handoff(gateways[receiver], handoff)
        acknowledge_handoff(gateways[sender], receipt)
        routes.append({'handoff': handoff, 'receipt': receipt})

    route('source', 'relay', root_a)
    route('source', 'relay', root_b)
    for receiver in RESPONSIBILITY_ACTORS:
        route('relay', receiver, derived_a)
        route('relay', receiver, derived_b)

    relevant_proof = issue('relay', keys['relay'], {
        'kind': 'revoke', 'workflow': workflow,
        'target': digest(derived_a), 'original': derived_a,
    })
    unrelated_proof = issue('relay', keys['relay'], {
        'kind': 'revoke', 'workflow': workflow,
        'target': digest(derived_b), 'original': derived_b,
    })
    actor_gateway = gateways[actor]
    other_actor = RESPONSIBILITY_ACTORS[(RESPONSIBILITY_ACTORS.index(actor) + 1) %
                                        len(RESPONSIBILITY_ACTORS)]
    if case in ('own_notice', 'hold'):
        actor_gateway.receive(relevant_proof)
    elif case == 'other_notice':
        gateways[other_actor].receive(relevant_proof)
    elif case == 'unrelated_notice':
        actor_gateway.receive(unrelated_proof)
    checkpoint = None
    use = None
    proposal = {'id': 'action-0', 'operation': 'forward',
                'claims': [digest(derived_a)]}
    if case == 'hold':
        hold = actor_gateway.record('benchmark_hold', 'action-0', [digest(relevant_proof)])
    else:
        checkpoint = actor_gateway.record('benchmark_checkpoint', 'action-0')
        use = issue(actor, keys[actor], {
            'kind': 'benchmark_use', 'workflow': workflow,
            'proposal': proposal, 'action': 'COMPLETED',
            'local_head': digest(checkpoint),
        })
    claims = {digest(packet): packet for gateway in gateways.values()
              for packet in gateway.claims.values()}
    observation = {
        'workflow': workflow, 'public_keys': public,
        'claims': list(claims.values()),
        'handoffs': [r['handoff'] for r in routes],
        'receipts': [r['receipt'] for r in routes],
        'events': [event for gateway in gateways.values() for event in gateway.events],
        'uses': [use] if use is not None else [],
        'questions': ['action-0'],
        'ordinary_logs': [route_label(r['handoff']) for r in routes],
    }
    conflicting_use = None
    if use is not None:
        conflicting_use = issue(actor, keys[actor], {
            'kind': 'benchmark_use', 'workflow': workflow,
            'proposal': proposal, 'action': 'BLOCKED',
            'local_head': digest(checkpoint),
        })
    truth = {
        'actor': actor, 'case': case,
        'routes': [route_label(r['handoff']) for r in routes],
        'sources': {digest(root_a): 'source', digest(root_b): 'source'},
        'actions': ['action-0'],
        'violations': ['action-0'] if case == 'own_notice' else [],
        'responsibility_label': {'action-0': 'violation' if case == 'own_notice' else 'non_violation'},
        'outcome_label': ('held' if case == 'hold' else 'completed'),
        'deliberate_gate_bypass': case != 'hold',
        'evidence_labels': {
            'full_none': {'action-0': 'sufficient_positive' if case == 'own_notice'
                          else 'not_scored_for_absence'},
            'missing_relevant_notice': {'action-0': 'insufficient_for_positive'},
            'missing_order_node': {'action-0': 'insufficient_for_positive'},
            'conflicting_action': {'action-0': 'insufficient_conflicting_records'},
        },
    }
    return {
        'execution_id': digest(observation), 'observation': observation,
        'truth': truth, 'latent_faults': {'conflicting_action_use': conflicting_use},
        'provenance': {'mode': 'synthetic_signed_execution',
                       'actor': actor, 'case': case,
                       'deliberate_gate_bypass': case != 'hold',
                       'route_count': len(routes), 'source_count': 2},
    }


def project_responsibility(execution, view='full', fault='none'):
    valid_views = {'full', 'ordinary_logs', 'no_receipts', 'opaque_relay'}
    valid_faults = {'none', 'missing_relevant_notice', 'missing_order_node',
                    'reorder', 'conflicting_action'}
    if view not in valid_views or fault not in valid_faults:
        raise ValueError('unknown responsibility projection')
    if view != 'full' and fault != 'none':
        raise ValueError('evidence faults are defined only for full view')
    observation = copy.deepcopy(execution['observation'])
    if view in ('ordinary_logs', 'opaque_relay'):
        for field in ('claims', 'handoffs', 'receipts', 'events', 'uses'):
            observation[field] = []
    if view == 'opaque_relay':
        observation['ordinary_logs'] = []
    if view == 'no_receipts':
        observation['receipts'] = []
        observation['events'] = [event for event in observation['events']
                                 if event['body']['action'] != 'handoff_received']
    if fault == 'missing_relevant_notice':
        observation['events'] = [event for event in observation['events']
                                 if event['body']['action'] != 'revocation_received']
    elif fault == 'missing_order_node':
        observation['events'] = [event for event in observation['events']
                                 if event['body']['action'] != 'benchmark_checkpoint']
    elif fault == 'reorder':
        for field in ('claims', 'handoffs', 'receipts', 'events', 'uses', 'ordinary_logs'):
            observation[field].reverse()
    elif fault == 'conflicting_action':
        packet = execution['latent_faults']['conflicting_action_use']
        if packet is not None:
            observation['uses'].append(copy.deepcopy(packet))
    return observation


def _accuracy(expected, predicted):
    expected, predicted = set(expected), set(predicted)
    true_positive = len(expected.intersection(predicted))
    return {
        'true_positive': true_positive, 'expected': len(expected),
        'predicted': len(predicted), 'false_positive': len(predicted - expected),
        'precision': true_positive / len(predicted) if predicted else None,
        'recall': true_positive / len(expected) if expected else None,
    }


def score_responsibility(execution, observation, assessment, view='full', fault='none'):
    truth = execution['truth']
    verified_routes = [digest(route) for route in assessment['verified_routes']]
    estimated_routes = [digest(route) for route in assessment['unverified_route_estimates']]
    expected_routes = [digest(route) for route in truth['routes']]
    expected_sources = set(truth['sources'].items())
    predicted_sources = set(assessment['sources'].items())
    predicted_violations = {question for question, finding in assessment['findings'].items()
                            if finding == 'violation'}
    expected_violations = set(truth['violations'])
    negative_actions = set(truth['actions']) - expected_violations
    expected_insufficient = (view == 'full' and fault in {
        'missing_relevant_notice', 'missing_order_node', 'conflicting_action'
    } and bool(expected_violations))
    actual_undetermined = {question for question, finding in assessment['findings'].items()
                           if finding == 'undetermined'}
    return {
        'actor': truth['actor'], 'case': truth['case'], 'view': view, 'fault': fault,
        'execution_id': execution['execution_id'],
        'routes_verified': _accuracy(expected_routes, verified_routes),
        'routes_unsigned_estimate': _accuracy(expected_routes, estimated_routes),
        'source_identity': _accuracy(expected_sources, predicted_sources),
        'duty_violations': _accuracy(expected_violations, predicted_violations),
        'false_accusations': len(predicted_violations.intersection(negative_actions)),
        'negative_action_count': len(negative_actions),
        'judgment_coverage': sum(value != 'undetermined'
                                 for value in assessment['findings'].values()) / len(truth['actions']),
        'undetermined_count': len(actual_undetermined),
        'evidence_insufficient_label': expected_insufficient,
        'undetermined_when_insufficient': (expected_insufficient and
                                           set(truth['actions']).issubset(actual_undetermined)),
        'rejected_evidence_count': len(assessment['rejected_evidence']),
        'observation_bytes': len(canonical(observation)),
        'top_level_signed_artifacts': sum(len(observation[field])
                                          for field in ('claims', 'handoffs', 'receipts', 'events', 'uses')),
        'model_calls': 0, 'tokens': 0,
    }


def run_responsibility_matrix(seed: int = 0):
    rows = []
    executions = []
    for actor in RESPONSIBILITY_ACTORS:
        for case in RESPONSIBILITY_CASES:
            execution = build_responsibility_execution(actor, case, seed)
            executions.append(execution)
            for view, fault in RESPONSIBILITY_PROJECTIONS:
                observation = project_responsibility(execution, view, fault)
                assessment = audit_public(observation)
                rows.append(score_responsibility(execution, observation, assessment, view, fault))
    return executions, rows


def run_freeze_matrix(seed: int = 0):
    rows = []
    for topology in TOPOLOGIES:
        for fault in FAULTS:
            for timing in TIMINGS:
                for notice_scope in NOTICE_SCOPES:
                    for freeze_scope in FREEZE_SCOPES:
                        result = run_freeze(topology, fault, timing, notice_scope,
                                            freeze_scope, seed)
                        rows.append({
                            'topology': topology, 'fault': fault, 'timing': timing,
                            'notice_scope': notice_scope, 'freeze_scope': freeze_scope,
                            'reference_id': result['reference_id'],
                            **result['metrics'],
                        })
    return rows


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {}

    def write(name, value):
        _write_json(args.output / name, value)
        manifest[name] = {'kind': 'canonical_json', 'sha256': digest(value)}

    freeze_rows = []
    for topology in TOPOLOGIES:
        for fault in FAULTS:
            for timing in TIMINGS:
                for notice_scope in NOTICE_SCOPES:
                    for freeze_scope in FREEZE_SCOPES:
                        result = run_freeze(topology, fault, timing, notice_scope,
                                            freeze_scope, args.seed)
                        stem = f'freeze_{topology}_{fault}_{timing}_{notice_scope}_{freeze_scope}.json'
                        write(stem, result)
                        freeze_rows.append({
                            'file': stem, 'topology': topology, 'fault': fault,
                            'timing': timing, 'notice_scope': notice_scope,
                            'freeze_scope': freeze_scope,
                            'reference_id': result['reference_id'], **result['metrics'],
                        })
    responsibility_rows = []
    executions, _ = run_responsibility_matrix(args.seed)
    for execution in executions:
        stem = execution['execution_id'][:16]
        write(f'execution_{stem}.json', execution)
        write(f'label_{stem}.json', execution['truth'])
        for view, fault in RESPONSIBILITY_PROJECTIONS:
            observation = project_responsibility(execution, view, fault)
            assessment = audit_public(observation)
            row = score_responsibility(execution, observation, assessment, view, fault)
            clean_observation = project_responsibility(execution, view, 'none')
            row['observation_changed_by_fault'] = (fault == 'none' or
                                                    observation != clean_observation)
            row['projection_applicable'] = row['observation_changed_by_fault']
            row['observation_file'] = f'observation_{stem}_{view}_{fault}.json'
            row['assessment_file'] = f'assessment_{stem}_{view}_{fault}.json'
            write(row['observation_file'], observation)
            write(row['assessment_file'], assessment)
            responsibility_rows.append(row)
    metrics = {
        'freeze': freeze_rows,
        'responsibility': responsibility_rows,
        'counts': {'freeze_runs': len(freeze_rows),
                   'responsibility_executions': len(executions),
                   'responsibility_projections': len(responsibility_rows)},
        'model_calls': 0, 'tokens': 0,
    }
    write('metrics.json', metrics)
    (args.output / 'README.md').write_text(
        '# Contribution generalization v2\n\n'
        'This directory contains deterministic signed executions only. '
        'Freeze runs vary topology, fault location, timing, notice scope and freeze scope; '
        'responsibility projections give the public observation to the auditor and keep '
        'labels in evaluator-only execution/label files.\n\n'
        'Reproduce with:\n\n'
        '`.venv/bin/python -m trust_network.benchmark.contribution.generalization '
        '--output results/contribution_generalization_v2`\n\n'
        'There are 48 freeze runs and 120 responsibility projections. These are '
        'controlled mechanism cases, not independent statistical samples. The manifest '
        'uses canonical JSON digests for JSON artifacts; the plots/report are generated '
        'after this command. No model or provider calls are made by this runner.\n')
    write('provenance.json', {
        'seed': args.seed, 'freeze_runs': len(freeze_rows),
        'responsibility_executions': len(executions),
        'responsibility_projections': len(responsibility_rows),
        'model_calls': 0, 'tokens': 0,
        'responsibility_actors': list(RESPONSIBILITY_ACTORS),
        'responsibility_cases': list(RESPONSIBILITY_CASES),
    })
    write('manifest.json', manifest)
    print(json.dumps({'output': str(args.output), 'freeze_runs': len(freeze_rows),
                      'responsibility_executions': len(executions),
                      'responsibility_projections': len(responsibility_rows),
                      'model_calls': 0}))


if __name__ == '__main__':
    main()
