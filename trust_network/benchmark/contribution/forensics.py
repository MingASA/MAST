"""Fixed execution, evidence-only ablations, and independently scored duty labels.

Auditor gets only public artifacts. Controller truth, projection names and keys
are never auditor inputs. A signed source identity is not factual/legal blame.
"""
import copy
from trust_network.benchmark.contribution.freeze import provision
from trust_network.benchmark.containment import AUTHORITIES
from trust_network.demo.claim_channel import ClaimGateway, issue, read
from trust_network.demo.documents import digest, keypair, canonical
from trust_network.demo.evidence_order import local_index, precedes
from trust_network.demo.propagation_notice import validate_handoff, acknowledge_handoff

VIEWS = ('full', 'ordinary_logs', 'no_receipts', 'opaque_relay')
FAULTS = ('none', 'reorder', 'missing_notice', 'missing_link', 'missing_receipt',
          'tampered_receipt', 'ambiguous_route')
CASES = ('own_notice', 'other_notice', 'late_notice', 'unrelated_notice', 'no_notice')


def build_execution(seed=0, case='own_notice'):
    if case not in CASES:
        raise ValueError('unknown duty case')
    f, nodes, routes = provision(seed)
    actor = nodes['receiver_a']
    original = f['trace']['A']['coordinator']
    if case == 'unrelated_notice':
        original = f['roots']['C']
    issuer = original['signature']['issuer']
    proof = issue(issuer, f['keys'][issuer], {'kind': 'revoke', 'workflow': f['workflow'],
                   'target': digest(original), 'original': original})
    if case in ('own_notice', 'unrelated_notice'):
        actor.receive(proof)
    elif case == 'other_notice':
        nodes['receiver_b'].receive(proof)
    bridge = actor.record('benchmark_checkpoint', 'action-0')
    # Deliberate violating actor fixture: not a call through the enforcing gate.
    # The experiment concerns attribution of a recorded action, not prevention.
    use = issue(actor.owner, actor.key, {'kind': 'benchmark_use', 'workflow': f['workflow'],
               'proposal': {'id': 'action-0', 'operation': 'forward',
                            'claims': [digest(f['trace']['A']['middle_a'])]},
               'action': 'COMPLETED', 'local_head': digest(bridge)})
    if case == 'late_notice':
        actor.receive(proof)
    claims = {digest(p): p for g in nodes.values() for p in g.claims.values()}
    observation = {'workflow': f['workflow'], 'public_keys': f['public'],
                   'claims': list(claims.values()),
                   'handoffs': [r['handoff'] for r in routes],
                   'receipts': [r['receipt'] for r in routes],
                   'events': [p for g in nodes.values() for p in g.events],
                   'uses': [use], 'questions': ['action-0'],
                   'ordinary_logs': [route_label(r['handoff']) for r in routes]}
    truth = {'routes': [route_label(r['handoff']) for r in routes],
             'sources': {cid: p['signature']['issuer'] for cid, p in claims.items()
                         if not p['body']['parents']},
             'violations': ['action-0'] if case == 'own_notice' else [],
             'actions': ['action-0']}
    return {'execution_id': digest(observation), 'observation': observation,
            'truth': truth, 'case': case}


def route_label(packet):
    return {'sender': packet['signature']['issuer'], 'recipient': packet['body']['recipient'],
            'claims': sorted(packet['body']['claims'])}


def signed_artifacts(value):
    """Walk nested signed packets without modifying or re-signing their bytes."""
    if isinstance(value, dict):
        if 'signature' in value and 'body' in value:
            yield value
        for child in value.values():
            yield from signed_artifacts(child)
    elif isinstance(value, list):
        for child in value:
            yield from signed_artifacts(child)


def batch_question(packet, index):
    return digest({'batch': digest(packet), 'output_index': index})


def project(execution, view='full', fault='none'):
    if view not in VIEWS or fault not in FAULTS:
        raise ValueError('unknown observation condition')
    o = copy.deepcopy(execution['observation'])
    original_events = {digest(p) for p in o['events']}
    if view in ('ordinary_logs', 'opaque_relay'):
        # Remove whole signed bundles, including nested lineage and receipt events.
        # Never strip parent fields inside signatures and call it valid evidence.
        for field in ('claims', 'handoffs', 'receipts', 'events', 'uses'):
            o[field] = []
    if view == 'opaque_relay':
        o['ordinary_logs'] = []
    if view == 'no_receipts':
        o['receipts'] = []
        # Local handoff_received is itself a receiver-signed receipt; ablate it too.
        o['events'] = [e for e in o['events'] if e['body']['action'] != 'handoff_received']
    if fault == 'missing_notice':
        o['events'] = [e for e in o['events'] if e['body']['action'] != 'revocation_received']
    elif fault == 'missing_link':
        o['events'] = [e for e in o['events'] if e['body']['action'] not in ('benchmark_checkpoint', 'reliability_outcome')]
    elif fault == 'missing_receipt':
        if o['receipts']:
            hid = o['receipts'][0]['body']['handoff']
            o['receipts'].pop(0)
            o['events'] = [e for e in o['events']
                           if not (e['body']['action'] == 'handoff_received' and e['body']['target'] == hid)]
    elif fault == 'tampered_receipt':
        if o['receipts']:
            # Remove redundant authentic receipt event to make proof unavailable.
            hid = o['receipts'][0]['body']['handoff']
            o['events'] = [e for e in o['events']
                           if not (e['body']['action'] == 'handoff_received' and e['body']['target'] == hid)]
            o['receipts'][0]['body']['sender'] = 'receiver_b'
    elif fault == 'ambiguous_route':
        if o['ordinary_logs']:
            alternative = copy.deepcopy(o['ordinary_logs'][0])
            alternative['recipient'] = 'receiver_b'
            o['ordinary_logs'].append(alternative)
    elif fault == 'reorder':
        for field in ('claims', 'handoffs', 'receipts', 'events', 'uses', 'ordinary_logs'):
            o[field].reverse()
    if 'batches' in o:
        removed_events = original_events - {digest(p) for p in o['events']}
        def allowed(batch):
            if view in ('ordinary_logs', 'opaque_relay'):
                return False
            nested = list(signed_artifacts(batch))
            if any(digest(p) in removed_events for p in nested):
                return False
            if view == 'no_receipts' and any(p['body'].get('kind') == 'handoff_receipt' for p in nested):
                return False
            # Do not leave an authentic nested copy of a removed/corrupted receipt.
            retained = {digest(p) for p in o['receipts']}
            if fault in ('missing_receipt', 'tampered_receipt') and any(
                    p['body'].get('kind') == 'handoff_receipt' and digest(p) not in retained for p in nested):
                return False
            return True
        o['batches'] = [b for b in o['batches'] if allowed(b)]
        if fault == 'reorder':
            o['batches'].reverse()
    return o


def audit(o):
    """No truth or observation-condition input; unsigned estimates stay unverified."""
    public, workflow = o['public_keys'], o['workflow']
    errors = []
    def valid(packets, kind):
        result = []
        for p in packets:
            try:
                owner, b = read(p, public)
                if b.get('kind') != kind or b.get('workflow') != workflow:
                    raise ValueError('wrong evidence scope')
                result.append(p)
            except (ValueError, KeyError, TypeError) as exc:
                errors.append({'artifact': digest(p), 'reason': str(exc)})
        return result
    # Only harvest evidence inside a verified original batch envelope.
    from trust_network.demo.reliability_audit import audit_batch
    batches = valid(o.get('batches', []), 'reliability_batch')
    nested = [p for b in batches for p in signed_artifacts(b)]
    def packets(field, kind):
        return list({digest(p): p for p in [*o[field], *[p for p in nested
                     if p['body'].get('kind') == kind]]}.values())
    claims = {digest(p): p for p in valid(packets('claims', 'claim'), 'claim')}
    events = valid(packets('events', 'gateway_event'), 'gateway_event')
    handoffs = valid(packets('handoffs', 'dependency_handoff'), 'dependency_handoff')
    receipts = valid(packets('receipts', 'handoff_receipt'), 'handoff_receipt')
    verified, intended = {}, {}
    for h in handoffs:
        try:
            sender = h['signature']['issuer']
            g = ClaimGateway(sender, keypair()[0], public, workflow, AUTHORITIES)
            validate_handoff(g, h)
            hid = digest(h)
            intended[hid] = route_label(h)
            claims.update({digest(p): p for p in h['body']['evidence']})
            g.handoffs[hid] = h
            for receipt in receipts:
                if receipt['body'].get('handoff') != hid:
                    continue
                acknowledge_handoff(g, receipt)
                if receipt['body']['status'] == 'accepted':
                    verified[hid] = route_label(h)
            # An independently retained receiver event can establish registration.
            for e in events:
                b = e['body']
                if (e['signature']['issuer'] == h['body']['recipient'] and
                    b.get('action') == 'handoff_received' and b.get('target') == hid and
                    b.get('reasons') == ['accepted', sender]):
                    verified[hid] = route_label(h)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({'artifact': digest(h), 'reason': str(exc)})
    index = local_index(events, public)

    def dependencies(cid, path=()):
        if cid in path or cid not in claims:
            raise ValueError('incomplete or cyclic lineage')
        parents = claims[cid]['body']['parents']
        return {cid}.union(*(dependencies(p, (*path, cid)) for p in parents))

    findings = {q: 'undetermined' for q in o['questions']}
    uses = valid(o['uses'], 'benchmark_use')
    grouped = {}
    for u in uses:
        grouped.setdefault(u['body']['proposal']['id'], {})[digest(u)] = (
            u['signature']['issuer'], u['body'], u)
    for packet in batches:
        try:
            body, plan = audit_batch(packet, public)
            owner = packet['signature']['issuer']
            proposals = {p['id']: p for p in plan['proposals']}
            for i, output in enumerate(body['outputs']):
                q = batch_question(packet, i)
                if q not in findings or output['action'] != 'COMPLETED':
                    continue
                proposal = proposals[output['proposal']]
                entry = index.get(output.get('local_head'))
                if not (entry and entry[0] == owner and
                        entry[1].get('action') == 'reliability_outcome' and
                        entry[1].get('target') == digest(proposal) and
                        entry[1].get('reasons') == ['COMPLETED']):
                    continue
                grouped.setdefault(q, {})[digest(packet)] = (owner,
                    {'proposal': proposal, 'action': output['action'],
                     'local_head': output['local_head']}, packet)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({'artifact': digest(packet), 'reason': str(exc)})
    for q in findings:
        candidates = grouped.get(q, {})
        if len(candidates) != 1:
            continue  # conflicting signed action records are not a selected chronology
        owner, b, u = next(iter(candidates.values()))
        try:
            if b['action'] != 'COMPLETED':
                continue
            deps = set().union(*(dependencies(cid) for cid in b['proposal']['claims']))
            notices = [eid for eid, (signer, event) in index.items()
                       if signer == owner and event['action'] == 'revocation_received'
                       and event['target'] in deps]
            if any(precedes(index, n, b['local_head'], owner, workflow) for n in notices):
                findings[q] = 'violation'
            # Absence from an uncommitted partial log is not evidence of innocence.
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({'artifact': digest(u), 'reason': str(exc)})
    return {'verified_routes': list(verified.values()),
            'intended_routes': list(intended.values()),
            'unverified_route_estimates': copy.deepcopy(o['ordinary_logs']),
            'sources': {cid: p['signature']['issuer'] for cid, p in claims.items()
                        if not p['body']['parents']},
            'findings': findings, 'rejected_evidence': errors}


def score(execution, observation, assessment):
    truth = execution['truth']
    def accuracy(expected, predicted):
        expected, predicted = set(expected), set(predicted)
        tp = len(expected & predicted)
        return {'true_positive': tp, 'expected': len(expected), 'predicted': len(predicted),
                'false_positive': len(predicted - expected),
                'precision': tp / len(predicted) if predicted else None,
                'recall': tp / len(expected) if expected else None}
    routes = lambda rows: [digest(r) for r in rows]
    predicted = [q for q, v in assessment['findings'].items() if v == 'violation']
    negatives = set(truth['actions']) - set(truth['violations'])
    # Observation oracle from controlled fixture removals, not auditor output.
    # A full positive needs the actor's notice, the signed bound head, and lineage.
    original = execution['observation']
    needed_notice = {digest(p) for p in original['events']
                     if p['signature']['issuer'] == 'receiver_a'
                     and p['body']['action'] == 'revocation_received'}
    observed_events = {digest(p) for p in observation['events']}
    heads = {p['body']['local_head'] for p in observation['uses']}
    sufficient_positive = (bool(truth['violations']) and bool(observation['uses'])
                           and bool(observation['claims']) and bool(needed_notice)
                           and needed_notice <= observed_events and heads <= observed_events)
    expected_unknown = set(truth['actions']) if not sufficient_positive else set()
    actual_unknown = {q for q, v in assessment['findings'].items() if v == 'undetermined'}
    return {'routes_verified': accuracy(routes(truth['routes']), routes(assessment['verified_routes'])),
            'routes_unsigned_estimate': accuracy(routes(truth['routes']), routes(assessment['unverified_route_estimates'])),
            'source_identity': accuracy(truth['sources'].items(), assessment['sources'].items()),
            'duty_violations': accuracy(truth['violations'], predicted),
            'false_accusations': len(set(predicted) & negatives), 'negative_actions': len(negatives),
            'decision_coverage': len(predicted) / len(truth['actions']),
            'warranted_undetermined': accuracy(expected_unknown, actual_unknown),
            'rejected_evidence_count': len(assessment['rejected_evidence']),
            'observation_bytes': len(canonical(observation)),
            'top_level_signed_artifacts': sum(len(observation[k]) for k in
                ('claims', 'handoffs', 'receipts', 'events', 'uses')),
            'model_calls': 0, 'tokens': 0}
