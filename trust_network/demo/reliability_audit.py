"""Independent public evidence replay, never financial blame percentages."""
from trust_network.demo.claim_channel import ClaimGateway, read
from trust_network.demo.documents import digest, keypair
from trust_network.demo.network_reliability import plan, ReliabilityConfig, verification_targets, apply_status_evidence


def audit_batch(packet, public):
    owner, body = read(packet, public)
    if body['kind'] != 'reliability_batch':
        raise ValueError('wrong report kind')
    planner, signed_plan = read(body['plan'], public)
    if planner != owner or signed_plan['workflow'] != body['workflow']:
        raise ValueError('plan signer/scope mismatch')
    # Authority mapping must be supplied by the verifier, not inferred from
    # self-assertions in evidence. See audit_with_authorities below.
    return body, signed_plan


def audit_with_authorities(packet, public, authorities):
    body, signed_plan = audit_batch(packet, public)
    gateway = ClaimGateway('offline_auditor', keypair()[0], public, body['workflow'], authorities)
    pending = list(body['evidence']['claims'])
    while pending:
        progressed = False
        for claim in pending[:]:
            _, value = read(claim, public)
            if all(p in gateway.claims for p in value['parents']):
                event = gateway.receive(claim)
                if event['body']['action'] != 'received':
                    raise ValueError('invalid evidence graph')
                pending.remove(claim)
                progressed = True
        if not progressed:
            raise ValueError('incomplete or cyclic evidence graph')
    for revoke in body['evidence']['revocations']:
        gateway.receive(revoke)
    expected = plan(gateway, signed_plan['proposals'], ReliabilityConfig(**signed_plan['plan']['config']))
    if expected != signed_plan['plan']:
        raise ValueError('plan does not follow declared policy')
    batch_id = digest(body['plan'])
    queries = body['queries']
    if len(queries) != body['verification_calls']:
        raise ValueError('query count mismatch')
    allowed = {c['root']: c for c in expected['checks']}
    seen = set()
    for item in queries:
        query = item['query']; root = query['root']
        check = allowed.get(root)
        if (not check or root in seen or query['kind'] != 'reliability_query' or
            query['workflow'] != body['workflow'] or query['batch'] != batch_id or
            not query.get('challenge') or query['proposals'] != check['proposals'] or
            item['authority'] != check['authority']):
            raise ValueError('query scope mismatch')
        seen.add(root)
    confirmed = {}
    for reply in body['replies']:
        signer, value = read(reply, public)
        if value['kind'] != 'reliability_status' or {'authority': signer, 'query': value['query']} not in queries:
            raise ValueError('unbound authority reply')
        root = value['query']['root']
        if root in confirmed or value['status'] not in ('active','revoked','unknown'):
            raise ValueError('duplicate or invalid reply')
        confirmed[root] = value['status']
        apply_status_evidence(gateway,value)
    for root, status in body['status'].items():
        if status in ('active','revoked','unknown') and confirmed.get(root) != status:
            raise ValueError('unsupported authority observation')
    decisions = {d['proposal']: d for d in expected['decisions']}
    if len(body['outputs']) != len(decisions) or set(o['proposal'] for o in body['outputs']) != set(decisions):
        raise ValueError('incomplete outcomes')
    proposals = {p['id']:p for p in signed_plan['proposals']}
    findings = []
    for outcome in body['outputs']:
        decision = decisions[outcome['proposal']]
        violates = outcome['action'] == 'COMPLETED' and (
            decision['action'] == 'REQUEST_EVIDENCE' or
            any(confirmed.get(r) in ('revoked','unknown') for r in verification_targets(decision)) or
            (decision['action'] == 'VERIFY' and any(confirmed.get(r) != 'active' for r in verification_targets(decision))))
        if outcome['action']=='COMPLETED' and proposals[outcome['proposal']].get('intent')=='verify':
            violates=True
        if outcome['action']=='VERIFIED':
            decision=decisions[outcome['proposal']]
            if (proposals[outcome['proposal']].get('intent')!='verify' or
                decision['action']!='VERIFY' or
                any(confirmed.get(r)!='active' for r in verification_targets(decision))):
                raise ValueError('verification result lacks required evidence')
        if outcome['action'] in ('COMPLETED','VERIFIED'):
            proposal = proposals[outcome['proposal']]
            if proposal['operation'] == 'approve_invoice':
                from trust_network.demo.claim_action_contract import validate_invoice
                try:
                    validate_invoice(gateway,proposal['claims'],proposal['order'])
                except ValueError:
                    violates = True
        findings.append({'proposal': outcome['proposal'],
                         'classification': 'execution_report_violates_evidence_duty' if violates else 'no_proven_evidence_duty_violation',
                         'reported_outcome': outcome['action']})
    return {'policy_replay_valid': True, 'findings': findings,
            'effect_proven': False, 'authority_truth_proven': False,
            'limits': ['signed_reports_prove_statements_not_physical_effects',
                       'missing_reply_does_not_prove_authority_fault',
                       'no_notification_deadline_or_financial_apportionment']}
