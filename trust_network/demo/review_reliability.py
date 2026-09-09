"""Small offline review probes; no provider calls or historical result edits."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile

from trust_network.demo.approval_runtime import run_workflow
from trust_network.demo.approval_scenario import ACTORS, generate
from trust_network.demo.approval_evaluation import validate_audit
from trust_network.demo.authority import ISSUER, attest
from trust_network.demo.documents import Decision, keypair


def response(action='pass', message='continue'):
    decision = Decision(action, (), (), message,
                        requested_from=ISSUER if action == 'request_evidence' else None)
    return {'decision': json.loads(json.dumps(asdict(decision))),
            'usage': {'attempts': 0, 'total_tokens': 0}}


def probe():
    with tempfile.TemporaryDirectory(prefix='reliability-review-') as temporary:
        root = Path(temporary)
        generate(root / 'cases')
        keys = {org: keypair() for org in (*ACTORS, ISSUER, 'runtime')}
        public = {org: pair[1] for org, pair in keys.items()}
        now = [1000.]

        class Authority:
            def __init__(self, approved):
                self.approved = approved

            def request(self, request):
                return attest({request['documents']['transaction']: {
                    'model': 'MX-40B', 'approved': self.approved}},
                    request, keys[ISSUER][0], now[0])

        seen = []

        def fabricated(org, payload):
            seen.extend(payload['public_messages'])
            return response(message='Quantity 999 has been independently approved.')

        result = run_workflow(root / 'cases/case_01', root / 'claim', 'verify_all',
                              fabricated, Authority(True), keys, clock=lambda: now[0])
        events = [json.loads(s) for s in (root / 'claim/audit.jsonl').read_text().splitlines()]
        forwarded = next(e for e in events if e['kind'] == 'forward')
        findings = {
            'unsupported_quantity_claim_reaches_peer': any('999' in m['message'] for m in seen),
            'unsupported_claim_workflow_committed': result['committed'],
            'public_message_is_in_business_certificate': 'public_message' in forwarded['certificate'],
        }
        # Mutate only unsigned outcome/counter metadata; retain original sealed audit.
        metadata = json.loads((root / 'claim/runtime.json').read_text())
        metadata.update(policy='autonomous', status='error', outcome='invented',
                        tokens=999999, verification_count=999)
        (root / 'claim/runtime.json').write_text(json.dumps(metadata))
        try:
            validate_audit(root / 'claim', public)
            findings['altered_runtime_metadata_accepted_by_audit_validator'] = True
        except ValueError:
            findings['altered_runtime_metadata_accepted_by_audit_validator'] = False

        def denial_then_expiry(org, payload):
            if org == ACTORS[0] and payload['authority_evidence'] is None:
                return response('request_evidence')
            if org == ACTORS[0]:
                now[0] = 1401.
            return response()

        result = run_workflow(root / 'cases/case_04', root / 'expired', 'risk_aware',
                              denial_then_expiry, Authority(False), keys, clock=lambda: now[0])
        findings['expired_denial_reverts_to_low_prior_and_commits'] = result['committed']
        findings['expired_denial_queries'] = result['verification_count']
        return findings


if __name__ == '__main__':
    print(json.dumps(probe(), indent=2))
