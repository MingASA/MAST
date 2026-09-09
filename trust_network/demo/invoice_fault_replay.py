"""Explicit controlled replay of a real Agent aggregate, not natural errors."""
import copy
from trust_network.demo.claim_channel import ClaimGateway, issue, read
from trust_network.demo.claim_action_contract import approve_invoice
from trust_network.demo.documents import digest


def replay(inputs, total, authorization, keys, public, authorities, workflow):
    rows=[]
    for fault in ('none','changed_total','omitted_component'):
        body=copy.deepcopy(total['body'])
        if fault=='changed_total': body['fact']['value']['cents']-=1
        if fault=='omitted_component': body['parents']=body['parents'][:-1]
        # The harness owns this experiment key; modified packets are explicitly
        # signed fault injections, never attributed to the original LLM output.
        packet=total if fault=='none' else issue('broker',keys['broker'][0],body)
        for policy in ('signature_only','commit_validation','receive_validation'):
            gateway=ClaimGateway('finance',keys['finance'][0],public,workflow,authorities)
            for source in [*inputs,authorization]: gateway.receive(source)
            event=None; exposed=0
            if policy=='receive_validation':
                event=gateway.receive(packet)
                exposed=int(event['body']['action']=='received')
            else:
                read(packet,public)  # Benchmark controls verify authenticity.
                exposed=1
                if policy=='signature_only': gateway.claims[digest(packet)]=packet
                else: event=gateway.receive(packet)  # Commit-time semantic check.
            effects=[]
            try:
                approve_invoice(gateway,[digest(packet),digest(authorization)],'A',
                    lambda:effects.append('simulated_invoice_confirmation'))
            except ValueError: pass
            rows.append({'fault':fault,'policy':policy,'unverified_claim_exposed_to_receiver':exposed,
                'invalid_claim_exposed':bool(exposed and fault!='none'),
                'effect_occurred':bool(effects),'unsafe_effect':bool(effects and fault!='none'),
                'source_real_aggregate_hash':digest(total),'evaluated_packet':packet,
                'gateway_events':gateway.events,
                'attribution':'controlled harness modification' if fault!='none' else 'original real Agent aggregate'})
    return {'kind':'controlled_in_process_same_aggregate_replay','model_calls':0,'rows':rows,
            'limits':['signature-only is an intentionally weak provenance control',
                      'exposure is an instrumented handoff boundary, not measured natural LLM adoption',
                      'one downstream receiver; this is not a multi-hop population estimate']}
