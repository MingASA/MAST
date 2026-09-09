"""Evidence-bound messages and organization-owned proposal signatures.

The protocol validates a deliberately finite business vocabulary. It makes no
claim to prove arbitrary natural-language statements. Draft prose is retained
at the sender/auditor, never promoted to an executable peer assertion.
"""
from dataclasses import asdict, dataclass
import copy
from trust_network.demo.documents import Certificate, Decision, digest
from trust_network.demo.authority import inspect


OPERATIONS = {
    'export_bank': 'submit_documents',
    'issuing_bank': 'release_payment_permission',
    'fulfillment': 'release_shipment',
}


def receive_history(receiver, public_keys, bundle, workflow_id, policy, messages, now):
    """Require the complete ordered predecessor chain, not just valid signatures."""
    if receiver not in OPERATIONS: raise ValueError('unknown receiving organization')
    expected=list(OPERATIONS)[:list(OPERATIONS).index(receiver)]
    if len(messages)!=len(expected): raise ValueError('missing or extra predecessor receipt')
    previous=[]; validated=[]
    for sender,envelope in zip(expected,messages):
        packet=envelope['body']['proposal']
        if packet.get('packet_version')!=2 or packet.get('predecessor_hashes')!=previous:
            raise ValueError('predecessor chain does not match signed receipt')
        validated.append(receive_packet(sender,public_keys,bundle,workflow_id,policy,envelope,now))
        previous.append(digest(envelope))
    return validated


@dataclass(frozen=True)
class ContractResult:
    action: str
    reasons: tuple[str, ...]
    accepted_message: dict | None = None


def expected_intent(organization, bundle):
    return {'operation': OPERATIONS[organization], 'transaction': bundle['transaction'],
            'document_version': bundle['document_version'],
            'model': bundle['invoice']['model'], 'quantity': bundle['invoice']['quantity']}


def issue_proposal(organization, private_key, request, proposal):
    """Called inside the originating organization's gateway, never by the receiver."""
    body = {'organization': organization, 'request_id': request['request_id'],
            'input_hash': digest(request), 'proposal': copy.deepcopy(proposal)}
    certificate = Certificate.issue(organization, 1, body,
        Decision('pass', ('proposal_integrity',), (), 'signed proposal'), private_key)
    return {'body': body, 'signature': asdict(certificate)}


def receive_proposal(organization, public_key, request, envelope):
    body = envelope['body']
    signature = Certificate(**envelope['signature'])
    if (signature.issuer != organization or body['organization'] != organization or
            body['request_id'] != request['request_id'] or body['input_hash'] != digest(request) or
            tuple(signature.checks) != ('proposal_integrity',) or
            not signature.verify(public_key, body, 1)):
        raise ValueError('untrusted or replayed organization proposal')
    return copy.deepcopy(body['proposal'])


def receive_packet(organization, public_keys, bundle, workflow_id, policy, envelope, now):
    """Independently called by each receiving gateway on peer messages."""
    body=envelope['body']; signed=Certificate(**envelope['signature'])
    if (signed.issuer!=organization or body['organization']!=organization or
            tuple(signed.checks)!=('proposal_integrity',) or
            not signed.verify(public_keys[organization],body,1)):
        raise ValueError('invalid peer message signature')
    packet=body['proposal']
    if packet['workflow_id']!=workflow_id or packet['policy']!=policy:
        raise ValueError('peer message belongs to different workflow or policy')
    message=packet['accepted_message']
    if message['from']!=organization or message['document_hash']!=digest(bundle):
        raise ValueError('peer message document or identity mismatch')
    if policy in ('authority_only','evidence_contract'):
        evidence=packet['evidence']
        if not evidence: raise ValueError('peer message lacks authorization evidence')
        verified=inspect(Certificate(**evidence['certificate']),bundle,bundle['document_version'],
                         public_keys['buyer_authority'],evidence['request_id'],now)
        if verified!='approved': raise ValueError('peer action is not authorized')
        if policy=='evidence_contract':
            proposal={'action':'pass','intent':message['intent'],
                      'claims':{field:value['value'] for field,value in message['claims'].items()}}
            checked=check_contract(organization,bundle,proposal,verified,digest(evidence['certificate']))
            if checked.action!='allow' or checked.accepted_message!=message:
                raise ValueError('peer message violates action contract')
    return copy.deepcopy(message)


def check_contract(organization, bundle, proposal, evidence_status, evidence_hash=None):
    """Check the proposed operation, then evidence, before any peer sees it.

    evidence_status/hash must come from the receiver's certificate verifier.
    Here authorization is a hard action prerequisite, not a tunable risk score.
    A malformed/unsupported draft can be repaired locally; denial must stop.
    """
    if organization not in OPERATIONS:
        raise ValueError('unknown organization')
    action = proposal.get('action')
    if action in ('reject', 'escalate'):
        return ContractResult('stop', ('organization_declined',))
    if action == 'request_evidence':
        return ContractResult('request_evidence', ('organization_requested_evidence',))
    if action != 'pass':
        return ContractResult('repair', ('unsupported_action',))
    reasons = []
    intent = expected_intent(organization, bundle)
    # Strict JSON-value equality avoids True being accepted as quantity 1.
    if digest(proposal.get('intent')) != digest(intent):
        reasons.append('intent_mismatch_or_unauthorized_operation')
    expected = {'model': intent['model'], 'quantity': intent['quantity'],
                'formal_authorization': True}
    claims = proposal.get('claims')
    if not isinstance(claims, dict) or digest(claims) != digest(expected):
        reasons.append('claims_must_match_document_and_authorization_contract')
    if reasons:
        return ContractResult('repair', tuple(reasons))
    if evidence_status in ('denied', 'unknown', 'stale_denied', 'stale_unknown'):
        return ContractResult('stop', ('authority_has_not_authorized_action',))
    if evidence_status != 'approved':
        return ContractResult('request_evidence', ('current_authority_evidence_required',))
    if not isinstance(evidence_hash, str) or len(evidence_hash) != 64:
        raise ValueError('approved status requires verified evidence reference')
    # Document equality supports quantity/model correspondence, NOT formal
    # authority approval of quantity. Each assertion carries its actual scope.
    message = {'from': organization, 'intent': intent,
        'claims': {
            'model': {'value': intent['model'], 'basis': 'public_document', 'reference': digest(bundle)},
            'quantity': {'value': intent['quantity'], 'basis': 'public_document', 'reference': digest(bundle)},
            'formal_authorization': {'value': True, 'basis': 'formal_model_authorization',
                                     'reference': evidence_hash}},
        'document_hash': digest(bundle)}
    return ContractResult('allow', ('action_and_claim_dependencies_satisfied',), message)
