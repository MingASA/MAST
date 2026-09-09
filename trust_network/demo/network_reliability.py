"""Public-view evidence scheduling and enforced invoice decisions.

No provider dependency or access to another owner's database. Risk scores are
operational priorities, not learned probabilities or mathematical settlement.
"""
from dataclasses import asdict, dataclass, field
import math
import secrets

from trust_network.demo.claim_channel import issue, read
from trust_network.demo.claim_action_contract import approve_invoice
from trust_network.demo.documents import digest


@dataclass(frozen=True)
class ReliabilityConfig:
    policy: str = 'dependency'
    propagation_threshold: float = 1.0
    omission_weight: float = 0.0
    operation_loss: dict = field(default_factory=lambda: {"forward": 1.0, "approve_invoice": 100.0})
    authority_cost: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.policy not in ('autonomous', 'verify_all', 'dependency'):
            raise ValueError('unknown policy')
        for value in (self.propagation_threshold, self.omission_weight):
            if not math.isfinite(value) or value < 0:
                raise ValueError('invalid policy weight')
        if set(self.operation_loss) != {'forward', 'approve_invoice'}:
            raise ValueError('loss required for each supported operation')
        for value in self.operation_loss.values():
            if type(value) not in (int,float) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid receiver loss')
        for value in self.authority_cost.values():
            if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
                raise ValueError('invalid authority cost')


def ancestors(gateway, target):
    result, visiting = set(), set()
    def walk(node):
        if node in visiting:
            raise ValueError('cyclic evidence')
        if node in result:
            return
        visiting.add(node)
        packet = gateway.claims.get(node)
        if packet:
            for parent in packet['body']['parents']:
                walk(parent)
        visiting.remove(node)
        result.add(node)
    walk(target)
    return result


def plan(gateway, proposals, config=ReliabilityConfig()):
    """Batch root cut: deduplicate shared evidence, order by exposed loss.

    Invoice execution always requires current confirmation of every root in
    protected policies. Selectivity applies to propagation and shared evidence;
    a small budget never silently removes execution checks.
    """
    ids = [p['id'] for p in proposals]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate proposal id')
    decisions, checks = [], {}
    for proposal in proposals:
        if proposal['operation'] not in ('forward', 'approve_invoice'):
            raise ValueError('unregistered action contract')
        targets = proposal['claims']
        if not targets or len(set(targets)) != len(targets):
            raise ValueError('empty or duplicate claims')
        loss = config.operation_loss[proposal['operation']]
        if type(loss) not in (int, float) or not math.isfinite(loss) or loss < 0:
            raise ValueError('invalid declared loss')
        nodes = set().union(*(ancestors(gateway, t) for t in targets))
        missing = sorted(n for n in nodes if n not in gateway.claims)
        revoked = sorted(n for n in nodes if n in gateway.revoked)
        roots = sorted(n for n in nodes if n in gateway.claims and not gateway.claims[n]['body']['parents'])
        blocked = missing or revoked
        required = proposal['operation'] == 'approve_invoice' or loss * (1 + config.omission_weight) >= config.propagation_threshold
        if config.policy == 'verify_all':
            required = True
        if config.policy == 'autonomous':
            required = False
        action = 'REQUEST_EVIDENCE' if blocked else ('VERIFY' if required else 'PASS')
        # The autonomous arm still has the same structural channel contracts.
        # It means autonomous freshness selection, not an unprotected raw LLM.
        decisions.append({'proposal': proposal['id'], 'action': action,
                          'missing': missing, 'revoked': revoked, 'roots': roots,
                          'rebuild': sorted(n for n in nodes if n in gateway.claims and
                              gateway.claims[n]['body']['parents'] and
                              ancestors(gateway,n).intersection(set(missing + revoked))) if blocked else []})
        if required and not blocked:
            for root in roots:
                entry = checks.setdefault(root, {'root': root,
                    'authority': gateway.claims[root]['signature']['issuer'],
                    'proposals': [], 'exposure': 0.0})
                entry['proposals'].append(proposal['id'])
                entry['exposure'] += loss * (1 + config.omission_weight)
    # Cost is supplied by receiver configuration, never by an incoming proposal.
    for entry in checks.values():
        entry['cost'] = config.authority_cost.get(entry['authority'],1.0)
        entry['priority'] = entry['exposure'] / entry['cost']
    return {'config': asdict(config), 'proposals_hash': digest(proposals),
            'decisions': decisions,
            'checks': sorted(checks.values(), key=lambda e: (-e['priority'], e['root'])),
            'limitations': ['receiver_loss_is_not_error_probability',
                            'omission_weight_is_operational_approximation']}


def run_batch(gateway, proposals, query_authority, effect,
              config=ReliabilityConfig(), verification_budget=None):
    """Intercept model proposals; authorize once per batch, then contract-check.

    query_authority(owner, query) returns an owner-signed reliability_status
    packet. effect(proposal) is a caller-owned adapter (simulation by default).
    This serial boundary is NOT atomic with remote state or external effects.
    """
    if verification_budget is not None and (type(verification_budget) is not int or verification_budget < 0):
        raise ValueError('invalid verification budget')
    # Snapshot prevents later mutation from changing the signed decision scope.
    import json
    proposals = json.loads(json.dumps(proposals))
    evidence = json.loads(json.dumps({'claims': list(gateway.claims.values()),
                                    'revocations': list(gateway.revoked.values())}))
    schedule = plan(gateway, proposals, config)
    plan_packet = issue(gateway.owner, gateway.key, {'kind': 'reliability_plan',
        'workflow': gateway.workflow, 'plan': schedule, 'proposals': proposals})
    gateway.record('reliability_planned', digest(plan_packet))
    batch = digest(plan_packet)
    challenge = secrets.token_hex(24)
    replies, status, queries = [], {}, []
    calls = 0
    for check in schedule['checks']:
        root = check['root']
        # If an earlier root failed for every dependent proposal, no later check
        # can authorize one of those proposals in this batch: stop that branch.
        dependents = [d for d in schedule['decisions'] if d['proposal'] in check['proposals']]
        if all(any(status.get(r) in ('revoked', 'unknown', 'unavailable', 'budget_exhausted')
                   for r in d['roots']) for d in dependents):
            status[root] = 'branch_frozen'
            continue
        if verification_budget is not None and calls >= verification_budget:
            status[root] = 'budget_exhausted'
            continue
        query = {'kind': 'reliability_query', 'workflow': gateway.workflow,
                 'root': root, 'batch': batch, 'challenge': challenge,
                 'proposals': check['proposals']}
        queries.append({'authority': check['authority'], 'query': query})
        calls += 1
        try:
            packet = query_authority(check['authority'], query)
            owner, body = read(packet, gateway.public)
            if owner != check['authority'] or body.get('kind') != 'reliability_status' or body.get('query') != query:
                raise ValueError('authority reply scope mismatch')
            if body.get('status') not in ('active', 'revoked', 'unknown'):
                raise ValueError('unknown authority status')
            status[root] = body['status']
            replies.append(packet)
            gateway.record('reliability_status_received', root, [digest(packet), body['status']])
            if body['status']=='revoked' and body.get('revocation') is not None:
                revoker,revocation=read(body['revocation'],gateway.public)
                if revoker!=owner or revocation.get('kind')!='revoke' or revocation.get('target')!=root:
                    raise ValueError('revocation proof scope mismatch')
                gateway.receive(body['revocation'])
        except Exception:
            if status.get(root) not in ('revoked','unknown'):
                status[root] = 'unavailable'
            gateway.record('reliability_query_failed', root)
    outputs = []
    by_id = {p['id']: p for p in proposals}
    for decision in schedule['decisions']:
        proposal = by_id[decision['proposal']]
        failed = [r for r in decision['roots'] if status.get(r) != 'active'] if decision['action'] == 'VERIFY' else []
        outcome = {'proposal': proposal['id'], 'result': None, 'failed_roots': failed}
        known_negative = [r for r in decision['roots'] if status.get(r) in ('revoked','unknown')]
        if decision['action'] == 'REQUEST_EVIDENCE' or known_negative:
            outcome['action'] = 'REQUEST_EVIDENCE'
        elif failed:
            outcome['action'] = 'REQUEST_EVIDENCE' if any(status.get(r) == 'revoked' for r in failed) else 'ESCALATE'
        else:
            # Re-check local revocation state after callbacks and immediately
            # before contract enforcement. Never rewrite the model's claims.
            if any(gateway.blockers(c) for c in proposal['claims']):
                outcome['action'] = 'REQUEST_EVIDENCE'
            else:
                effect_started = False
                def invoke_effect():
                    nonlocal effect_started
                    effect_started = True
                    return effect(proposal)
                try:
                    if proposal['operation'] == 'approve_invoice':
                        outcome['result'] = approve_invoice(gateway, proposal['claims'], proposal['order'], invoke_effect)
                    else:
                        outcome['result'] = invoke_effect()
                    outcome['action'] = 'COMPLETED'
                except ValueError as exc:
                    outcome['action'] = 'EFFECT_UNKNOWN' if effect_started else 'BLOCKED'
                    outcome['reason'] = str(exc)
                except Exception:
                    # An effect adapter may have performed work before failing.
                    outcome['action'] = 'EFFECT_UNKNOWN'
        gateway.record('reliability_outcome', digest(proposal), [outcome['action']])
        outputs.append(outcome)
    report = {'kind': 'reliability_batch', 'workflow': gateway.workflow,
              'plan': plan_packet, 'evidence': evidence, 'queries': queries, 'replies': replies,
              'status': status, 'outputs': outputs, 'verification_calls': calls,
              'effects_are_adapter_reports': True}
    return issue(gateway.owner, gateway.key, report)


def authority_status(gateway, query):
    if query.get('kind') != 'reliability_query' or query.get('workflow') != gateway.workflow:
        raise ValueError('wrong query scope')
    root = query['root']
    original = gateway.claims.get(root)
    owned = original and read(original, gateway.public)[0] == gateway.owner and not original['body']['parents']
    status = ('revoked' if gateway.blockers(root) else 'active') if owned else 'unknown'
    body = {'kind': 'reliability_status', 'query': query, 'status': status}
    if status=='revoked':
        body['revocation']=gateway.revoked[root]
    packet = issue(gateway.owner, gateway.key, body)
    gateway.record('reliability_status_replied', root, [digest(packet), status])
    return packet
