"""Evidence-limited audit for reliability workflow provenance.

The controller event log is tamper-evident within a run. This module checks
that log and reconstructs factual delivery, revocation and action-use
relationships. It deliberately does not turn signatures into intent or
financial blame.
"""
import copy

from trust_network.demo.claim_channel import read
from trust_network.demo.claim_derivation import valid_derivation
from trust_network.demo.documents import digest


def append_event(events, event):
    """Append one controller event to a hash-chained, sequence-numbered log."""
    record=copy.deepcopy(event)
    record.pop('event_hash',None)
    record['sequence']=len(events)
    record['previous_hash']=events[-1].get('event_hash') if events else None
    record['event_hash']=digest(record)
    events.append(record)
    return record


def verify_event_chain(events):
    """Verify sequence, predecessor and content hash for a controller log."""
    previous=None
    for expected,event in enumerate(events):
        if not isinstance(event,dict) or event.get('sequence')!=expected:
            raise ValueError('event sequence mismatch')
        if event.get('previous_hash')!=previous:
            raise ValueError('event predecessor mismatch')
        actual=event.get('event_hash')
        body=copy.deepcopy(event); body.pop('event_hash',None)
        if actual!=digest(body):
            raise ValueError('event hash mismatch')
        previous=actual
    return {'valid':True,'events':len(events),'root':previous}


def _normalise_packet(value):
    packet=copy.deepcopy(value)
    # claim_id is a public view field, never part of a signed packet.
    if isinstance(packet,dict): packet.pop('claim_id',None)
    return packet


def _collect_packets(value, output):
    if isinstance(value,dict):
        if isinstance(value.get('body'),dict) and isinstance(value.get('signature'),dict):
            packet=_normalise_packet(value)
            kind=packet['body'].get('kind')
            if kind in ('claim','revoke'):
                output[digest(packet)]=packet
        for child in value.values(): _collect_packets(child,output)
    elif isinstance(value,list):
        for child in value: _collect_packets(child,output)


def _gateway_events(events, public_keys):
    result=[]
    for index,event in enumerate(events):
        if event.get('kind')!='worker_exchange': continue
        candidates=[]
        response=event.get('response',{})
        if isinstance(response,dict):
            candidates.append(response.get('event'))
            candidates.extend(response.get('events',[]) or [])
        for candidate in candidates:
            if not isinstance(candidate,dict) or not isinstance(candidate.get('body'),dict): continue
            if candidate['body'].get('kind')!='gateway_event': continue
            packet=_normalise_packet(candidate)
            issuer,body=read(packet,public_keys)
            result.append({'event_index':index,'issuer':issuer,'body':body,'packet':packet})
    return result


def _contains_root(claim_id, root_id, packets, visiting=None):
    if claim_id==root_id: return True
    visiting=set() if visiting is None else visiting
    if claim_id in visiting: raise ValueError('cyclic claim graph in accountability audit')
    packet=packets.get(claim_id)
    if packet is None or packet['body'].get('kind')!='claim': return False
    visiting.add(claim_id)
    result=any(_contains_root(parent,root_id,packets,visiting)
               for parent in packet['body'].get('parents',[]))
    visiting.remove(claim_id)
    return result


def audit_accountability(run_record, events, fixture_manifest, control_event):
    """Return factual provenance and an evidence-limited responsibility audit."""
    chain=verify_event_chain(events)
    public_keys=fixture_manifest['public_keys']
    packets={}
    _collect_packets(events,packets)
    _collect_packets(run_record,packets)
    old_root=control_event['old_root']
    old_packet=packets.get(old_root)
    source_issuer=(old_packet or {}).get('signature',{}).get('issuer')
    deliveries=[event for event in events
                if event.get('kind')=='claim_delivery' and
                event.get('packet_digest')==old_root and event.get('action')=='received']
    revoke_deliveries=[(index,event) for index,event in enumerate(events)
                       if event.get('kind')=='claim_delivery' and
                       event.get('packet_kind')=='revoke' and event.get('action')=='received']
    gateway_events=_gateway_events(events,public_keys)
    revocation_receipts=[item for item in gateway_events
                         if item['body'].get('action')=='revocation_received' and
                         item['body'].get('target')==old_root]
    control_indices=[index for index,event in enumerate(events)
                     if event.get('kind')=='controlled_event' and event.get('target')==old_root]
    batch_indices={}
    for index,event in enumerate(events):
        if event.get('kind')=='worker_exchange' and event.get('operation')=='reliability_batch':
            stage=event.get('request',{}).get('stage')
            batch_indices.setdefault(stage,[]).append(index)
    consumer_owners={event.get('owner') for event in events
                     if event.get('kind')=='worker_exchange' and
                     event.get('operation')=='reliability_batch' and event.get('owner')}
    consumer_delivery_indices=[index for index,event in revoke_deliveries
                               if event.get('receiver') in consumer_owners]
    consumer_receipts=[item for item in revocation_receipts
                       if item['issuer'] in consumer_owners]

    completed_uses=[]
    transformation_mismatches=[]
    for batch in run_record.get('batches',[]):
        stage=batch.get('stage')
        for proposal in batch.get('proposals',[]):
            claims=proposal.get('claims',[])
            if not isinstance(claims,list): continue
            includes_old=any(_contains_root(claim,old_root,packets) for claim in claims)
            if includes_old:
                for output in batch.get('outputs',[]):
                    if output.get('proposal')==proposal.get('id') and output.get('action')=='COMPLETED':
                        completed_uses.append({'stage':stage,'proposal':proposal.get('id'),
                            'claims':claims,'batch_event_indices':batch_indices.get(stage,[])})
    for claim_id,packet in packets.items():
        body=packet.get('body',{})
        parents=body.get('parents',[])
        if body.get('kind')!='claim' or not parents: continue
        parent_packets=[packets.get(parent) for parent in parents]
        if any(parent is None for parent in parent_packets): continue
        if not valid_derivation(body.get('rule','relay'),body.get('fact'),
                                [parent['body']['fact'] for parent in parent_packets]):
            transformation_mismatches.append({'claim_id':claim_id,
                'issuer':packet['signature']['issuer'],'parents':parents,
                'rule':body.get('rule','relay')})

    # A source authority's own local receipt is not a notice to the consumer.
    # Count only a formal revoke delivery or gateway receipt owned by an
    # organization that actually executed a batch in this run.
    notice_indices=consumer_delivery_indices+[item['event_index'] for item in consumer_receipts]
    notice_index=min(notice_indices,default=None)
    control_index=min(control_indices,default=None)
    use_after_notice=[]; use_without_notice=[]
    for use in completed_uses:
        indices=use['batch_event_indices']
        use_index=min(indices) if indices else None
        if notice_index is not None and use_index is not None and use_index>notice_index:
            use_after_notice.append(use)
        elif control_index is not None and use_index is not None and use_index>control_index:
            use_without_notice.append(use)

    findings=[]
    findings.extend({'classification':'downstream_transformation_mismatch',**item}
                    for item in transformation_mismatches)
    findings.extend({'classification':'used_after_revocation_notice',**item}
                    for item in use_after_notice)
    findings.extend({'classification':'used_after_controlled_change_without_recorded_notice',**item}
                    for item in use_without_notice)
    if not findings:
        findings.append({'classification':'no_fault_conclusion',
                         'reason':'available signed/runtime evidence does not establish a protocol duty violation'})
    if use_after_notice:
        responsibility_status='protocol_duty_violation_proven'
        responsibility_reason='signed event order shows use after the receiver recorded the revocation notice; intent and loss remain unproven'
    else:
        responsibility_status='undetermined'
        responsibility_reason='signatures establish provenance and event order, but notification duties, intent and physical loss are not established'
    return {
        'event_chain':chain,
        'source':{'claim_id':old_root,'issuer':source_issuer,
                  'formal_delivery_orgs':sorted({event['receiver'] for event in deliveries}),
                  'formal_delivery_count':len(deliveries),
                  'max_propagation_hops':max((event.get('path_length',0) for event in deliveries),default=0)},
        'revocation':{'controlled_event_observed':control_index is not None,
                      'controlled_event_index':control_index,
                      'formal_notice_delivery_orgs':sorted({event['receiver'] for _,event in revoke_deliveries}),
                      'consumer_notice_delivery_orgs':sorted({event['receiver'] for _,event in revoke_deliveries
                                                              if event.get('receiver') in consumer_owners}),
                      'gateway_receipt_owners':sorted({item['issuer'] for item in revocation_receipts}),
                      'consumer_gateway_receipt_owners':sorted({item['issuer'] for item in consumer_receipts}),
                      'gateway_receipt_index':notice_index},
        'derived_claim_checks':{'checked':len(transformation_mismatches)+sum(
            1 for packet in packets.values()
            if packet.get('body',{}).get('kind')=='claim' and packet.get('body',{}).get('parents')),
            'transformation_mismatches':transformation_mismatches},
        'action_uses':{'completed_using_old_root':completed_uses,
                       'completed_after_revocation_notice':use_after_notice,
                       'completed_after_controlled_change_without_notice':use_without_notice},
        'findings':findings,
        'responsibility':{'status':responsibility_status,'reason':responsibility_reason,
                          'numeric_attribution':None},
        'limits':['runtime event log does not prove physical side effects',
                  'signed source change does not prove original issuer fault',
                  'missing notification duty or loss model prevents numeric blame']
    }
