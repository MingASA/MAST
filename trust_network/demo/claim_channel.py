"""Signed dependency channel for authoritative structured claim forwarding.

Authority is configured per predicate. This initial rule supports exact relay,
not arbitrary semantic inference from prose. Each gateway owns its local view.
"""
import copy
from dataclasses import asdict
import secrets
from trust_network.demo.documents import Certificate, Decision, digest
from trust_network.demo.claim_derivation import valid_derivation


def issue(owner, key, body):
    return {'body': body, 'signature': asdict(Certificate.issue(owner, 1, body,
            Decision('pass', ('claim_channel',), (), ''), key))}


def read(packet, public):
    cert = Certificate(**packet['signature'])
    if (tuple(cert.checks) != ('claim_channel',) or cert.action != 'pass' or
            not cert.verify(public[cert.issuer], packet['body'], 1)):
        raise ValueError('invalid claim channel signature')
    return cert.issuer, packet['body']


class ClaimGateway:
    def __init__(self, owner, key, public, workflow, authorities, fact_authorities=None):
        self.owner, self.key, self.public = owner, key, public
        self.workflow, self.authorities = workflow, authorities
        self.fact_authorities=dict(fact_authorities or {})
        self.claims, self.revoked, self.events = {}, {}, []
        for field in self.PROTOCOL_STATE: setattr(self,field,{})

    PROTOCOL_STATE=('handoffs','handoff_index','incoming_handoffs','handoff_receipts',
                    'notification_outbox','notification_acks','notification_receipts','fact_disputes')

    def snapshot(self):
        return copy.deepcopy({field:getattr(self,field) for field in
                              ('claims','revoked','events',*self.PROTOCOL_STATE)})

    def restore(self,state):
        for field in ('claims','revoked','events',*self.PROTOCOL_STATE):
            setattr(self,field,copy.deepcopy(state.get(field,[] if field=='events' else {})))
        if 'handoff_index' not in state:
            for hid,packet in self.handoffs.items():
                for claim in packet['body']['evidence']:
                    self.handoff_index.setdefault(digest(claim),[]).append(hid)

    def fork(self):
        result=copy.copy(self);result.restore(self.snapshot());return result

    def adopt(self,staged):
        self.restore(staged.snapshot())

    def record(self, action, target, reasons=()):
        body = {'kind': 'gateway_event', 'workflow': self.workflow, 'action': action,
                'target': target, 'reasons': list(reasons), 'sequence': len(self.events)+1,
                'previous': digest(self.events[-1]) if self.events else None}
        event = issue(self.owner, self.key, body); self.events.append(event)
        return event

    def blockers(self, claim_id):
        if claim_id in self.revoked: return [claim_id]
        if claim_id in self.fact_disputes:return ['disputed:'+claim_id]
        if claim_id not in self.claims: return ['missing:'+claim_id]
        result = []
        for parent in self.claims[claim_id]['body']['parents']:
            result.extend(self.blockers(parent))
        return sorted(set(result))

    def receive(self, packet):
        owner, body = read(packet, self.public)
        if body['workflow'] != self.workflow: raise ValueError('wrong workflow')
        if body['kind'] == 'revoke':
            target = body['target']
            # A revocation can arrive before its claim. Attach the original
            # signed packet so authority can still be checked without guessing.
            original_owner, original = read(body['original'], self.public)
            if (digest(body['original']) != target or original_owner != owner or
                    original['kind'] != 'claim' or original['workflow'] != self.workflow):
                raise ValueError('unauthorized revocation')
            self.revoked[target] = packet
            impacted = [c for c in self.claims if self.blockers(c)]
            event=self.record('revocation_received', target, impacted)
            if self.handoffs:
                from trust_network.demo.propagation_notice import enqueue_revocation
                enqueue_revocation(self,packet)
            return event
        if body['kind'] != 'claim': raise ValueError('unsupported packet')
        claim_id = digest(packet); parents = body['parents']
        if not isinstance(parents, list) or len(parents) > 16 or len(set(parents)) != len(parents):
            raise ValueError('invalid dependencies')
        if parents:
            if any(p not in self.claims for p in parents):
                return self.record('blocked', claim_id, ['missing_dependency'])
            if not valid_derivation(body.get('rule','relay'),body['fact'],
                                    [self.claims[p]['body']['fact'] for p in parents]):
                return self.record('blocked', claim_id, ['unsupported_transformation'])
        elif self.authorities.get(body['fact']['predicate']) != owner:
            return self.record('blocked', claim_id, ['not_authoritative'])
        self.claims[claim_id] = packet
        blocked = self.blockers(claim_id)
        return self.record('blocked' if blocked else 'received', claim_id, blocked)

    def use(self, claim_id, operation):
        blocked = self.blockers(claim_id)
        return self.record('use_blocked' if blocked else 'use_allowed', claim_id,
                           blocked or [operation])

    def execute(self, claim_id, operation, effect):
        event = self.use(claim_id, operation)
        if event['body']['action'] != 'use_allowed':
            raise ValueError('claim dependency blocked execution')
        return effect()

    def execute_checked(self, claim_id, operation, query_authority, effect):
        """Challenge each root owner before use; no private state in this gateway.

        This checks authority state at query time. It does not make revocation
        and an external physical effect atomic.
        """
        if self.blockers(claim_id):
            self.use(claim_id,operation)
            raise ValueError('claim dependency blocked execution')
        def roots(target):
            parents=self.claims[target]['body']['parents']
            return set().union(*(roots(p) for p in parents)) if parents else {target}
        challenge=secrets.token_hex(24)
        for root in sorted(roots(claim_id)):
            authority=self.claims[root]['signature']['issuer']
            request={'kind':'status_query','workflow':self.workflow,'root':root,
                     'claim':claim_id,'operation':operation,'challenge':challenge}
            try:
                packet=query_authority(authority,request)
                signer,body=read(packet,self.public)
                if signer!=authority or body.get('query')!=request or body.get('kind')!='status_reply':
                    raise ValueError('status reply scope mismatch')
                self.record('authority_status_received',root,[digest(packet)])
                if body.get('status')!='active': raise ValueError('authority did not confirm')
            except Exception:
                self.record('use_blocked',claim_id,['authority_status_unavailable_or_not_active'])
                raise
        return self.execute(claim_id,operation,effect)
