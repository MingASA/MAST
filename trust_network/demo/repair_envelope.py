"""Public, version-specific repair state from the verified commitment ledger."""
from trust_network.demo.documents import digest
from trust_network.demo.negotiation import OWNERS, projection


def build_repair_envelope(book, plan, now, messages):
    checked = book.required(plan, now)
    invalid = []
    for owner in checked['denied']:
        receipt = book.latest[(owner, digest(projection(owner, plan, book.binding_mode)))]
        invalid.append({'owner': owner, 'rejected_scope': receipt['body']['projection'],
                        'reasons': receipt['body']['reasons'], 'signed_evidence': receipt})
    return {'kind': 'versioned_repair', 'rejected_plan_hash': digest(plan),
            'blocked_operation': 'execute_this_plan', 'invalid_dependencies': invalid,
            'unverified_dependencies': checked['missing'],
            'retained_approvals': checked['receipts'],
            'current_owner_offers': messages,
            'transition': {'propose': 'submit a revised candidate for program verification; does not bypass the gate',
                           'verify': 'check a candidate without requesting execution',
                           'reject': 'end negotiation if no acceptable candidate can be proposed'},
            'scope_rule': 'denial covers its signed projection; a revised projection requires fresh evidence'}


def verification_frontiers(required):
    """Check independent resource constraints before final buyer acceptance.

    Collect upstream conflicts together; do not acquire downstream approval for
    a candidate already requiring upstream repair. Dependencies are configured
    by the workflow contract, not guessed from private state.
    """
    if set(required) - set(OWNERS): raise ValueError('unknown evidence dependency')
    return [[o for o in ('supplier', 'carrier') if o in required],
            [o for o in ('buyer',) if o in required]]


def compact_repair_view(book, plan, now, messages):
    """LLM projection of gateway-verified evidence, not replacement audit data."""
    from trust_network.demo.public_quote_repair import quote_counterproposal
    envelope = build_repair_envelope(book, plan, now, messages)
    candidate = None
    for message in reversed(messages):
        if message['body']['organization'] == 'carrier':
            candidate = quote_counterproposal(plan, message, book.public_keys['carrier'], book.workflow_id)
            break
    return {'kind': 'verified_repair_options', 'rejected_plan_hash': digest(plan),
            'invalid_dependencies': [{'owner': item['owner'], 'reasons': item['reasons'],
                'evidence_hash': digest(item['signed_evidence'])} for item in envelope['invalid_dependencies']],
            'retained_approvals': [r['body']['owner'] for r in envelope['retained_approvals']],
            'unverified_dependencies': envelope['unverified_dependencies'],
            'counterproposal': candidate, 'transition': envelope['transition'],
            'scope_rule': envelope['scope_rule']}
