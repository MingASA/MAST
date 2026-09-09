"""Regression tests for concrete review counterexamples, without model calls."""
from dataclasses import asdict
import json
import pytest
from trust_network.demo.approval_scenario import ACTORS, generate
from trust_network.demo.approval_runtime import run_workflow
from trust_network.demo.approval_evaluation import validate_audit
from trust_network.demo.authority import ISSUER, attest
from trust_network.demo.documents import Decision, keypair


def reply(action='pass'):
    return {'decision':json.loads(json.dumps(asdict(Decision(action,(),(),'continue',
            requested_from=ISSUER if action=='request_evidence' else None)))),
            'usage':{'attempts':0,'total_tokens':0}}


def setup(tmp_path):
    generate(tmp_path/'cases')
    return {o:keypair() for o in (*ACTORS,ISSUER,'runtime')}


def test_expired_denial_requires_new_evidence(tmp_path):
    keys=setup(tmp_path); now=[1000.]; received=[]
    class Authority:
        def request(self,request):
            received.append(request)
            return attest({request['documents']['transaction']:{'model':'MX-40B','approved':False}},
                          request,keys[ISSUER][0],now[0])
    def actor(org,payload):
        if payload['authority_evidence'] is None: return reply('request_evidence')
        now[0]=1401.
        return reply()
    result=run_workflow(tmp_path/'cases/case_04',tmp_path/'run','risk_aware',actor,
                        Authority(),keys,clock=lambda:now[0])
    assert not result['committed'] and result['outcome']=='escalated_policy'
    assert len(received)==2


def test_signed_result_metadata_and_unique_query_nonce(tmp_path):
    keys=setup(tmp_path); received=[]
    class Authority:
        def request(self,request):
            received.append(request['request_id'])
            return attest({request['documents']['transaction']:{'model':'MX-40B','approved':True}},
                          request,keys[ISSUER][0],1000.)
    public={o:p[1] for o,p in keys.items()}
    for name in ('first','second'):
        out=tmp_path/name
        run_workflow(tmp_path/'cases/case_01',out,'verify_all',lambda *a:reply(),
                     Authority(),keys,clock=lambda:1000.,request_id='same-label')
        validate_audit(out,public)
    assert len(set(received))==2
    path=tmp_path/'first/runtime.json'; result=json.loads(path.read_text())
    result['tokens']=999999; path.write_text(json.dumps(result))
    with pytest.raises(ValueError,match='result seal'): validate_audit(path.parent,public)
