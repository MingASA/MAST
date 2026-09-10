"""Signed, scoped recovery offers. Evidence replacement never grants an action.

An authority explicitly links a new source claim to its old claim. Derived
claims must be rebuilt and signed by their issuers; tasks must be proposed anew.
"""
import copy
from trust_network.demo.claim_channel import issue, read
from trust_network.demo.claim_derivation import valid_derivation
from trust_network.demo.documents import digest
from trust_network.demo.network_reliability import ancestors
from trust_network.demo.reliability_audit import audit_with_authorities


RECOVERY_EVIDENCE_PROTOCOL = 'recovery-evidence-v1'


def scope(fact):
    value=fact['value']
    if not isinstance(value,dict) or not value.get('order') or not value.get('currency'):
        raise ValueError('recovery requires explicit order and currency')
    # Action authority must not be silently broadened during a replacement.
    return fact['predicate'],value['order'],value['currency'],value.get('operation')


def replacement_offer(authority, old_id, new_packet):
    new_packet=copy.deepcopy(new_packet)
    original=authority.claims.get(old_id)
    if original is None:
        raise ValueError('unknown original')
    old_owner,old=read(original,authority.public)
    new_owner,new=read(new_packet,authority.public)
    if (old_owner!=authority.owner or new_owner!=authority.owner or
        old['kind']!='claim' or new['kind']!='claim' or old['parents'] or new['parents'] or
        old['workflow']!=authority.workflow or new['workflow']!=authority.workflow or
        scope(old['fact'])!=scope(new['fact']) or digest(new_packet)==old_id):
        raise ValueError('replacement authority or business scope mismatch')
    return issue(authority.owner,authority.key,{'kind':'replacement_offer',
        'workflow':authority.workflow,'old':old_id,'new':new_packet})


def build_recovery_evidence(gateway, envelope_packet, task,
                            replacement_offer_packet, coordinator_registration,
                            replacement_source_packet):
    """Build the standard public evidence bundle for one recovery task.

    The bundle is transport data, not a new authorization. Its components are
    individually signed by the receiver, source authority, and coordinator.
    The coordinator only emits it after checking that the new source is in its
    local claim store and that the supplied registration event is one of its
    signed receive events. The resulting evidence id binds all components and
    the exact rebuild task together.
    """
    envelope_owner, envelope = read(envelope_packet, gateway.public)
    if (envelope_owner == gateway.owner or
        envelope.get('kind') != 'recovery_envelope' or
        envelope.get('workflow') != gateway.workflow or
        envelope.get('action_authorized') is not False or
        envelope.get('fresh_status_check_still_required') is not True):
        raise ValueError('invalid recovery envelope for evidence bundle')

    offer_owner, offer = read(replacement_offer_packet, gateway.public)
    source_owner, source = read(replacement_source_packet, gateway.public)
    if offer.get('kind') != 'replacement_offer' or offer.get('workflow') != gateway.workflow:
        raise ValueError('invalid replacement offer for evidence bundle')
    if source.get('kind') != 'claim' or source.get('workflow') != gateway.workflow:
        raise ValueError('invalid replacement source for evidence bundle')
    old_id = offer.get('old')
    new_id = digest(replacement_source_packet)
    if digest(offer.get('new')) != new_id:
        raise ValueError('replacement offer source mismatch')
    original = gateway.claims.get(old_id)
    registered = gateway.claims.get(new_id)
    if original is None or registered is None or digest(registered) != new_id:
        raise ValueError('recovery source is not registered at coordinator')
    old_owner, old = read(original, gateway.public)
    if (offer_owner != old_owner or source_owner != old_owner or
        old.get('kind') != 'claim' or source.get('kind') != 'claim' or
        old.get('parents') or source.get('parents') or
        old.get('workflow') != gateway.workflow or
        scope(old['fact']) != scope(source['fact']) or new_id in gateway.revoked):
        raise ValueError('replacement evidence provenance mismatch')

    registration_owner, registration = read(coordinator_registration, gateway.public)
    registration_id = digest(coordinator_registration)
    if (registration_owner != gateway.owner or
        registration.get('kind') != 'gateway_event' or
        registration.get('workflow') != gateway.workflow or
        registration.get('action') != 'received' or
        registration.get('target') != new_id or
        not any(digest(event) == registration_id for event in gateway.events)):
        raise ValueError('coordinator registration is not a local receive event')

    if sum(digest(item) == digest(replacement_offer_packet)
           for item in envelope.get('offers', [])) != 1:
        raise ValueError('replacement offer is not bound to recovery envelope')
    if sum(digest(item) == new_id for item in envelope.get('new_source_packets', [])) != 1:
        raise ValueError('replacement source is not bound to recovery envelope')
    if not isinstance(task, dict):
        raise ValueError('recovery task is missing')
    tasks = [item for item in envelope.get('tasks', [])
             if isinstance(item, dict) and
             item.get('proposal', {}).get('id') == task.get('proposal', {}).get('id')]
    if len(tasks) != 1 or tasks[0] != task:
        raise ValueError('recovery task is not bound to recovery envelope')
    if task.get('requires_new_model_decision') is not True:
        raise ValueError('recovery task does not require a new model decision')
    replacements = task.get('replacement_sources')
    if not isinstance(replacements, dict) or replacements.get(old_id) != new_id:
        raise ValueError('recovery task does not bind replacement source')
    rebuild_required = task.get('rebuild_required')
    if (not isinstance(rebuild_required, list) or not rebuild_required or
        not any(new_id in item.get('replacement_parents', [])
                for item in rebuild_required if isinstance(item, dict))):
        raise ValueError('recovery task has no bound derived rebuild')

    old_derived_claims = [item.get('old') for item in rebuild_required]
    bundle = {
        'kind': 'recovery_evidence_bundle',
        'protocol': RECOVERY_EVIDENCE_PROTOCOL,
        'workflow': gateway.workflow,
        'batch': envelope.get('batch'),
        'old_root': old_id,
        'new_root': new_id,
        'old_derived': (old_derived_claims[0] if len(old_derived_claims) == 1
                        else old_derived_claims),
        'recovery_envelope_digest': digest(envelope_packet),
        'task': copy.deepcopy(task),
        'rebuild_required': copy.deepcopy(rebuild_required),
        'signed_artifacts': {
            'recovery_envelope': copy.deepcopy(envelope_packet),
            'replacement_offer': copy.deepcopy(replacement_offer_packet),
            'replacement_source': copy.deepcopy(replacement_source_packet),
            'coordinator_registration': copy.deepcopy(coordinator_registration),
        },
        'runtime_validations': {
            'replacement_offer_validated_by_runtime': True,
            'replacement_source_registered_at_coordinator': True,
            'coordinator_registration_is_local_receive': True,
        },
        'constraints': {
            'action_authorized': False,
            'fresh_status_check_still_required': True,
            'old_source_status': 'revoked_historical_excluded',
            'old_source_must_not_be_counted': True,
        },
    }
    bundle['evidence_id'] = digest(bundle)
    return bundle


def validate_recovery_evidence(gateway, evidence):
    """Rebuild and compare a recovery evidence bundle before a write."""
    if not isinstance(evidence, dict) or evidence.get('kind') != 'recovery_evidence_bundle':
        raise ValueError('signed recovery evidence bundle is required')
    if evidence.get('protocol') != RECOVERY_EVIDENCE_PROTOCOL:
        raise ValueError('unsupported recovery evidence protocol')
    artifacts = evidence.get('signed_artifacts')
    if not isinstance(artifacts, dict):
        raise ValueError('recovery evidence artifacts are missing')
    required = ('recovery_envelope', 'replacement_offer', 'replacement_source',
                'coordinator_registration')
    if any(name not in artifacts for name in required):
        raise ValueError('recovery evidence artifact is missing')
    expected = build_recovery_evidence(
        gateway, artifacts['recovery_envelope'], evidence.get('task'),
        artifacts['replacement_offer'], artifacts['coordinator_registration'],
        artifacts['replacement_source'])
    if evidence != expected:
        raise ValueError('recovery evidence bundle mismatch')
    return expected


def prepare_recovery(gateway, batch_packet, offers):
    offers=copy.deepcopy(offers)
    owner,batch=read(batch_packet,gateway.public)
    if owner!=gateway.owner or batch.get('workflow')!=gateway.workflow:
        raise ValueError('wrong recovery batch')
    audit=audit_with_authorities(batch_packet,gateway.public,gateway.authorities)
    if any(f['classification']=='execution_report_violates_evidence_duty' for f in audit['findings']):
        raise ValueError('batch has a reported duty violation; investigate before retry')
    proposals={p['id']:p for p in batch['plan']['body']['proposals']}
    retry_ids={o['proposal'] for o in batch['outputs'] if o['action'] in ('REQUEST_EVIDENCE','ESCALATE','BLOCKED')}
    # Never retry COMPLETED or EFFECT_UNKNOWN: retrying may duplicate effects.
    relevant=set().union(*(ancestors(gateway,c) for pid in retry_ids for c in proposals[pid]['claims']))
    staged=gateway.fork()
    replacements={}; packets=[]
    for offer in offers:
        signer,body=read(offer,gateway.public)
        if body.get('kind')!='replacement_offer' or body.get('workflow')!=gateway.workflow:
            raise ValueError('invalid replacement offer')
        old_id=body['old']
        if old_id not in relevant or old_id in replacements:
            raise ValueError('unrelated or duplicate replacement')
        original=gateway.claims.get(old_id)
        if original is None:
            raise ValueError('original evidence unavailable')
        # Reuse issuer checks; resulting bytes are irrelevant to validation.
        old_owner,old=read(original,gateway.public); new_owner,new=read(body['new'],gateway.public)
        if (signer!=old_owner or signer!=new_owner or new.get('kind')!='claim' or
            old['parents'] or new['parents'] or new.get('workflow')!=gateway.workflow or
            scope(old['fact'])!=scope(new['fact']) or digest(body['new'])==old_id):
            raise ValueError('replacement authority or business scope mismatch')
        if staged.receive(body['new'])['body']['action']!='received':
            raise ValueError('replacement is not locally valid')
        replacements[old_id]=digest(body['new']); packets.append(body['new'])
    tasks=[]
    for pid in sorted(retry_ids):
        proposal=proposals[pid]
        nodes=set().union(*(ancestors(gateway,c) for c in proposal['claims']))
        rebuild=[{'old':c,'issuer':gateway.claims[c]['signature']['issuer'],
                  'rule':gateway.claims[c]['body'].get('rule','relay'),
                  'parents':gateway.claims[c]['body']['parents'],
                  'replacement_parents':[
                      replacements.get(parent,parent)
                      for parent in gateway.claims[c]['body']['parents']
                  ]}
                 for c in sorted(nodes) if c in gateway.claims and gateway.claims[c]['body']['parents']
                 and ancestors(gateway,c).intersection(replacements)]
        tasks.append({'proposal':proposal,'replacement_sources':{o:n for o,n in replacements.items() if o in nodes},
                      'rebuild_required':rebuild,'requires_new_model_decision':True})
    # Publish only after every offer validates. Old statements/revocations stay.
    gateway.adopt(staged)
    body={'kind':'recovery_envelope','workflow':gateway.workflow,'batch':digest(batch_packet),
          'offers':offers,'new_source_packets':packets,'tasks':tasks,
          'excluded_proposals':[o['proposal'] for o in batch['outputs'] if o['proposal'] not in retry_ids],
          'action_authorized':False,'fresh_status_check_still_required':True}
    packet=issue(gateway.owner,gateway.key,body)
    gateway.record('recovery_prepared',digest(packet),[digest(batch_packet)])
    return packet


def rebuild_derived_claim(gateway, envelope_packet, task, fact, rule=None, evidence=None):
    """Rebuild one affected derived claim under a signed recovery envelope.

    The original issuer supplies the new derived claim. The envelope fixes the
    old claim, exact replacement parent list and workflow; the caller still
    must supply a fresh model-approved fact. No action authorization is
    inferred from this operation, and the old claim remains in the gateway.
    """
    validated_evidence = validate_recovery_evidence(gateway, evidence)
    if (digest(validated_evidence['signed_artifacts']['recovery_envelope']) !=
        digest(envelope_packet) or validated_evidence.get('task') != task):
        raise ValueError('recovery evidence does not match rebuild request')
    envelope_owner,envelope=read(envelope_packet,gateway.public)
    if (envelope.get('kind')!='recovery_envelope' or
        envelope_owner==gateway.owner or envelope.get('workflow')!=gateway.workflow or
        envelope.get('action_authorized') is not False or
        envelope.get('fresh_status_check_still_required') is not True):
        raise ValueError('invalid recovery envelope')
    if not isinstance(task,dict) or task.get('proposal',{}).get('id') not in {
            item.get('proposal',{}).get('id') for item in envelope.get('tasks',[]) if isinstance(item,dict)}:
        raise ValueError('unbound recovery task')
    task_ids=[item for item in envelope['tasks']
              if item.get('proposal',{}).get('id')==task['proposal']['id']]
    if len(task_ids)!=1 or task_ids[0]!=task:
        raise ValueError('recovery task mismatch')
    offers=envelope.get('offers')
    if not isinstance(offers,list) or not offers:
        raise ValueError('recovery envelope has no replacement offers')
    offered_replacements={}
    for offer in offers:
        signer,offer_body=read(offer,gateway.public)
        if (offer_body.get('kind')!='replacement_offer' or
            offer_body.get('workflow')!=gateway.workflow):
            raise ValueError('invalid replacement offer in envelope')
        old_source_id=offer_body.get('old')
        if old_source_id in offered_replacements:
            raise ValueError('duplicate replacement offer in envelope')
        old_source=gateway.claims.get(old_source_id)
        if old_source is None:
            raise ValueError('replacement source predecessor unavailable')
        old_source_owner,old_source_body=read(old_source,gateway.public)
        new_source=offer_body.get('new')
        new_source_owner,new_source_body=read(new_source,gateway.public)
        if (signer!=old_source_owner or new_source_owner!=old_source_owner or
            old_source_body.get('kind')!='claim' or new_source_body.get('kind')!='claim' or
            old_source_body.get('parents') or new_source_body.get('parents') or
            scope(old_source_body['fact'])!=scope(new_source_body['fact']) or
            digest(new_source)==old_source_id):
            raise ValueError('replacement offer provenance mismatch')
        offered_replacements[old_source_id]=digest(new_source)
    required=task.get('rebuild_required')
    if not isinstance(required,list) or len(required)!=1:
        raise ValueError('recovery requires one derived claim rebuild')
    rebuild=required[0]
    old_id=rebuild.get('old')
    original=gateway.claims.get(old_id)
    if original is None:
        raise ValueError('original derived claim unavailable')
    issuer,old=read(original,gateway.public)
    if (issuer!=gateway.owner or rebuild.get('issuer')!=gateway.owner or
        old.get('kind')!='claim' or old.get('workflow')!=gateway.workflow or
        old.get('parents')!=rebuild.get('parents') or
        not old.get('parents')):
        raise ValueError('recovery derived claim scope mismatch')
    replacements=task.get('replacement_sources',{})
    if (not isinstance(replacements,dict) or not replacements or
        any(offered_replacements.get(old)!=new for old,new in replacements.items())):
        raise ValueError('recovery replacement mapping is not backed by offers')
    expected_parents=[replacements.get(parent,parent) for parent in old['parents']]
    if rebuild.get('replacement_parents')!=expected_parents:
        raise ValueError('recovery parent mapping mismatch')
    new_parents=rebuild['replacement_parents']
    if not isinstance(new_parents,list) or len(set(new_parents))!=len(new_parents):
        raise ValueError('invalid rebuilt dependencies')
    if any(parent not in gateway.claims for parent in new_parents):
        raise ValueError('rebuilt dependency unavailable')
    if any(parent in gateway.revoked for parent in new_parents):
        raise ValueError('rebuilt dependency revoked')
    if rule is None:
        rule=rebuild.get('rule','relay')
    if rule!=rebuild.get('rule','relay'):
        raise ValueError('recovery rule mismatch')
    inputs=[gateway.claims[parent]['body']['fact'] for parent in new_parents]
    if not valid_derivation(rule,fact,inputs):
        raise ValueError('rebuilt derived fact violates rule')
    packet=issue(gateway.owner,gateway.key,{'kind':'claim','workflow':gateway.workflow,
        'fact':copy.deepcopy(fact),'parents':list(new_parents),'rule':rule})
    checked=gateway.receive(packet)
    if checked['body']['action']!='received':
        raise ValueError('rebuilt derived claim was not accepted')
    gateway.record('derived_claim_rebuilt',digest(packet),[old_id,*new_parents])
    return packet
