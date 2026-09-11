"""Receiver-owned action requirements over the verified public claim graph.

Invoice approval is intentionally distinct from paying or releasing goods.
Those operations require separate contracts and resource execution receipts.
"""
from trust_network.demo.documents import digest


def validate_invoice(gateway, claim_ids, order):
    """Check the business contract without authorizing or invoking an effect."""
    contract={'operation':'approve_invoice','version':1,
              'requires':['invoice_authorization','total_charge']}
    request={'contract':digest(contract),'order':order,'claims':list(claim_ids)}
    target=digest(request)
    def block(reason):
        gateway.record('action_contract_blocked',target,[reason])
        raise ValueError(reason)
    if not isinstance(order,str) or not order: block('invalid_order')
    if len(claim_ids)!=2 or len(set(claim_ids))!=2: block('exactly_two_distinct_claims_required')
    facts={}
    for claim_id in claim_ids:
        if gateway.blockers(claim_id): block('missing_or_revoked_dependency')
        fact=gateway.claims[claim_id]['body']['fact']
        if fact['predicate'] in facts: block('duplicate_evidence_type')
        facts[fact['predicate']]=fact['value']
    try:
        validate_invoice_facts(facts, order)
    except ValueError as exc:
        block(str(exc))
    return target,digest(contract)


def approve_invoice(gateway, claim_ids, order, effect):
    target,contract_id=validate_invoice(gateway,claim_ids,order)
    gateway.record('action_contract_allowed',target,[contract_id,*claim_ids])
    result=effect()
    gateway.record('action_effect_returned',target,[digest(result)])
    return result

def validate_invoice_facts(facts, order):
    """Shared business rules, independent of signatures/freshness/dependency gates."""
    def block(reason):
        raise ValueError(reason)
    if not isinstance(order,str) or not order: block('invalid_order')
    if set(facts)!={'invoice_authorization','total_charge'}: block('required_evidence_missing')
    authorization=facts['invoice_authorization']; total=facts['total_charge']
    if set(authorization)!={'order','operation','currency','maximum_cents','approved'}:
        block('invalid_authorization_schema')
    if set(total)!={'order','currency','cents'}: block('invalid_total_schema')
    if authorization['order']!=order or total['order']!=order: block('cross_order_evidence')
    if authorization['operation']!='approve_invoice' or authorization['approved'] is not True:
        block('operation_not_authorized')
    if not isinstance(total['currency'],str) or not total['currency'] or total['currency']!=authorization['currency']:
        block('currency_mismatch')
    if (type(total['cents']) is not int or type(authorization['maximum_cents']) is not int or
            total['cents']<0 or total['cents']>authorization['maximum_cents']):
        block('amount_not_authorized')
