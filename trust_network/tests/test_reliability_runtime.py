from dataclasses import asdict,replace
from pathlib import Path
import copy
import json
import time
import pytest
from trust_network.demo.documents import Certificate,Decision,keypair
from trust_network.demo.authority import AuthorityClient,ISSUER,attest,inspect
from trust_network.demo.approval_scenario import ACTORS,generate
from trust_network.demo.approval_runtime import run_workflow
from trust_network.demo.approval_evaluation import evaluate,validate_audit
from trust_network.demo.reliability import RiskConfig,VisibleContext,decide


@pytest.fixture
def scenario(tmp_path):
    generate(tmp_path/'cases')
    keys={o:keypair() for o in (*ACTORS,ISSUER,'runtime')}
    return tmp_path/'cases',keys


def passer(org,payload):
    return {'decision':json.loads(json.dumps(asdict(Decision('pass',('document_consistency',),(),'continue')))),
            'usage':{'attempts':0,'total_tokens':0}}


def execute_fixture(root,keys,out,case,policy,**kwargs):
    case=root/case
    client=AuthorityClient(case/'organizations/buyer_authority/registry.json',keys[ISSUER][0])
    return run_workflow(case,out,policy,passer,client,keys,**kwargs)


def test_same_public_input_opposite_private_truth(scenario):
    root,_=scenario
    for a,b in (('case_01','case_02'),('case_03','case_04')):
        for path in ('public/bundle.json','intake.json',*(f'organizations/{o}/private.md' for o in ACTORS)):
            assert (root/a/path).read_bytes()==(root/b/path).read_bytes()
        assert json.loads((root/a/'ground_truth.json').read_text())['authorized']
        assert not json.loads((root/b/'ground_truth.json').read_text())['authorized']
    bundle=json.loads((root/'case_02/public/bundle.json').read_text())
    assert {bundle[k]['model'] for k in ('order','invoice','packing_list','transport_order')}=={'MX-40B'}


def test_policy_veto_prevents_forward_and_commit_without_truth_access(scenario,tmp_path,monkeypatch):
    root,keys=scenario; original=Path.read_text
    def guarded(path,*args,**kwargs):
        if path.name in ('ground_truth.json','registry.json'): pytest.fail('online runtime read private/evaluator file')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',guarded)
    seen=[]
    def actor(org,payload):
        seen.append((org,copy.deepcopy(payload)))
        assert 'AUTHORITY_ONLY_71' not in json.dumps(payload) and 'authorized_truth' not in payload
        return passer(org,payload)
    case=root/'case_02'
    for policy in ('autonomous','verify_all','risk_aware'):
        out=tmp_path/policy
        result=run_workflow(case,out,policy,actor,
            AuthorityClient(case/'organizations/buyer_authority/registry.json',keys[ISSUER][0]),keys)
        assert result['committed']==(policy=='autonomous')
        events=[json.loads(line) for line in (out/'audit.jsonl').read_text().splitlines()]
        assert sum(e['kind']=='forward' for e in events)==(3 if policy=='autonomous' else 0)
        assert result['verification_count']==(0 if policy=='autonomous' else 1)
        validate_audit(out,{o:p[1] for o,p in keys.items()})
    assert seen[0][1]==seen[3][1]==seen[4][1]  # first LLM input identical across policies


def test_selective_cost_saving_exposes_low_risk_counterexample(scenario,tmp_path):
    root,keys=scenario; groups={}
    for policy in ('autonomous','verify_all','risk_aware'):
        rows=[]
        for case in sorted(root.glob('case_*')):
            result=execute_fixture(root,keys,tmp_path/policy/case.name,case.name,policy)
            rows.append(evaluate(case,result))
        groups[policy]=rows
    assert [sum(r['verification_count'] for r in groups[p]) for p in groups]==[0,4,2]
    assert [sum(r['unsafe_completion'] for r in groups[p]) for p in groups]==[2,0,1]
    assert [sum(r['verification_cost'] for r in groups[p]) for p in groups]==[0,12,6]


def test_shared_cache_is_fair_and_omission_changes_real_action(scenario,tmp_path):
    root,keys=scenario
    for policy in ('verify_all','risk_aware'):
        result=execute_fixture(root,keys,tmp_path/policy,'case_01',policy)
        assert result['committed'] and result['verification_count']==1  # three gates, one query
    base=RiskConfig(routine_loss=100)
    without=execute_fixture(root,keys,tmp_path/'without','case_04','risk_aware',config=base)
    with_omission=execute_fixture(root,keys,tmp_path/'omission','case_04','risk_aware',config=replace(base,omission_weight=1))
    assert without['committed'] and not with_omission['committed']
    assert with_omission['verification_count']==1


def test_baseline_can_request_same_evidence_and_policy_blocks_ignored_denial(scenario,tmp_path):
    root,keys=scenario; case=root/'case_02'
    def requester(org,payload):
        if payload['authority_evidence'] is None:
            return {'decision':json.loads(json.dumps(asdict(Decision('request_evidence',(),(),'please check',requested_from=ISSUER)))),
                    'usage':{'attempts':0,'total_tokens':0}}
        return passer(org,payload)
    for policy in ('autonomous','risk_aware'):
        result=run_workflow(case,tmp_path/policy,policy,requester,
            AuthorityClient(case/'organizations/buyer_authority/registry.json',keys[ISSUER][0]),keys)
        assert result['committed']==(policy=='autonomous')
        assert result['verification_count']==1


def test_budget_and_authority_failure_cannot_commit(scenario,tmp_path):
    root,keys=scenario
    result=execute_fixture(root,keys,tmp_path/'budget','case_02','risk_aware',config=RiskConfig(budget=0))
    assert result['outcome']=='escalated_policy' and result['verification_count']==0
    class Unavailable:
        def request(self,request): raise RuntimeError('offline')
    result=run_workflow(root/'case_02',tmp_path/'failure','verify_all',passer,Unavailable(),keys)
    assert result['status']=='error' and not result['committed']
    assert result['verification_cost']==3
    assert evaluate(root/'case_02',result)['unsafe_completion'] is None


def test_certificate_rejects_tamper_wrong_issuer_replay_and_expiry(scenario):
    root,keys=scenario; bundle=json.loads((root/'case_01/public/bundle.json').read_text())
    now=time.time(); request={'documents':bundle,'version':1,'request_id':'run-1','now':now}
    cert=attest({bundle['transaction']:{'approved':True,'model':'MX-40B'}},request,keys[ISSUER][0],now)
    assert inspect(cert,bundle,1,keys[ISSUER][1],'run-1',now)=='approved'
    for changed,req,at in ((replace(cert,action='reject'),'run-1',now),
                           (replace(cert,issuer='seller'),'run-1',now),
                           (cert,'run-2',now),(cert,'run-1',now+301)):
        with pytest.raises(ValueError): inspect(changed,bundle,1,keys[ISSUER][1],req,at)
    updated=copy.deepcopy(bundle); updated['invoice']['quantity']=11
    with pytest.raises(ValueError): inspect(cert,updated,1,keys[ISSUER][1],'run-1',now)
    with pytest.raises(ValueError): inspect(cert,bundle,2,keys[ISSUER][1],'run-1',now)


def test_audit_detects_truncation(scenario,tmp_path):
    root,keys=scenario; out=tmp_path/'run'
    execute_fixture(root,keys,out,'case_01','risk_aware')
    log=out/'audit.jsonl'; lines=log.read_text().splitlines()
    log.write_text('\n'.join(lines[:-1])+'\n')
    with pytest.raises(ValueError,match='truncated'): validate_audit(out,{o:p[1] for o,p in keys.items()})


def test_existing_settlement_reused_and_cached_evidence_not_omission(scenario,tmp_path):
    from trust_network.demo.approval_accountability import postmortem
    root,keys=scenario
    for name in ('case_01','case_04'):
        out=tmp_path/name
        runtime=execute_fixture(root,keys,out,name,'risk_aware',config=RiskConfig(omission_weight=1))
        result=postmortem(out,evaluate(root/name,runtime))
        assert result['supported']
        assert sum(amount for org,amount in result['settlement']['net'])==pytest.approx(result['settlement']['social'])
        if name=='case_01':
            assert result['forwarded_without_authority_evidence']==[]
            assert result['settlement']['social']==3
        else:
            assert result['forwarded_without_authority_evidence']==sorted(ACTORS)
            assert result['settlement']['social']==10


def test_bad_signature_is_fail_closed_in_runtime(scenario,tmp_path):
    root,keys=scenario
    class Imposter:
        def request(self,request):
            return attest({request['documents']['transaction']:{'approved':True,'model':'MX-40B'}},request,keypair()[0])
    result=run_workflow(root/'case_02',tmp_path/'run','risk_aware',passer,Imposter(),keys)
    assert result['status']=='error' and not result['committed']
    events=[json.loads(line) for line in (tmp_path/'run/audit.jsonl').read_text().splitlines()]
    assert not any(e['kind']=='forward' for e in events)


def test_remote_authority_adapter_never_sends_private_key(scenario,tmp_path):
    from http.server import BaseHTTPRequestHandler,HTTPServer
    from threading import Thread
    from trust_network.demo.authority import RemoteAuthorityClient
    root,keys=scenario; received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append(request)
            cert=attest({request['documents']['transaction']:{'approved':False,'model':'MX-40B'}},request,keys[ISSUER][0])
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(asdict(cert)).encode())
    server=HTTPServer(('127.0.0.1',0),Handler); thread=Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        client=RemoteAuthorityClient(f'http://127.0.0.1:{server.server_port}/')
        public_only=dict(keys); public_only[ISSUER]=(None,keys[ISSUER][1])
        result=run_workflow(root/'case_02',tmp_path/'run','risk_aware',passer,client,public_only)
        assert result['outcome']=='escalated_policy' and result['verification_count']==1
        assert len(received)==1 and 'signing_key' not in received[0]
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_preflight_budget_never_calls_provider(monkeypatch):
    from trust_network.demo import provider
    from trust_network.demo.run_reliability import estimate
    monkeypatch.setattr(provider,'complete',lambda *a,**k:pytest.fail('estimate invoked model'))
    budget=estimate()
    assert budget['planned_runs']==36 and budget['planning_actor_calls']==144
    assert budget['planning_tokens']==306388
