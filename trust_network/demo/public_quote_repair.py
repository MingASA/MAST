"""Construct a bounded counterproposal using only signed carrier offers.

Never executes or silently changes buyer intent. A new buyer decision and fresh
affected evidence are required for this candidate to become executable.
"""
import copy
from trust_network.demo.documents import digest
from trust_network.demo.negotiation import validate_plan
from trust_network.demo.negotiation_worker import verify


def quote_counterproposal(plan, carrier_message, public_key, workflow_id):
    validate_plan(plan)
    body = verify(carrier_message, 'carrier', public_key, workflow_id)
    services = body['content']['services']
    candidate = copy.deepcopy(plan)
    grouped = {}
    for index, row in enumerate(candidate['shipments']):
        service = services.get(row['service'])
        if (service is None or service['dispatch_day'] != row['dispatch_day'] or
                service['arrival_day'] != row['arrival_day']):
            return None
        grouped.setdefault(row['service'], []).append(index)
    for name, indexes in grouped.items():
        service = services[name]
        if sum(candidate['shipments'][i]['quantity'] for i in indexes) > service['capacity']:
            return None
        for i in indexes: candidate['shipments'][i]['cost'] = 0
        candidate['shipments'][indexes[0]]['cost'] = service['price']
    validate_plan(candidate)
    if digest(candidate) == digest(plan): return None
    return {'kind': 'counterproposal_not_authorized', 'base_plan_hash': digest(plan),
            'authority_offer_hash': digest(carrier_message), 'candidate': candidate,
            'changed_fields': ['shipments.cost'],
            'requires': ['buyer_new_execution_intent', 'fresh_affected_approvals']}
