from dataclasses import replace
import json
from pathlib import Path
from trust_network.demo.documents import Decision,Certificate,keypair
from trust_network.demo import run


def test_signed_certificate_rejects_tamper_and_wrong_version():
    key,public=keypair(); bundle={'invoice':'v1'}
    decision=Decision('pass',('document_scope',),(),'ok')
    cert=Certificate.issue('bank',1,bundle,decision,key)
    assert cert.verify(public,bundle,1)
    assert not cert.verify(public,{'invoice':'v2'},1)
    assert not cert.verify(public,bundle,2)
    assert not replace(cert,action='reject').verify(public,bundle,1)
    assert not cert.verify(keypair()[1],bundle,1)


def test_versioned_revision_and_context_boundary(monkeypatch,tmp_path):
    inputs=[]
    def scripted(org,payload,*args):
        inputs.append((org,payload))
        assert 'private' not in json.dumps(payload)
        decision={'action':'pass','checks':['own scope'],'findings':[], 'public_message':'ok'}
        if org=='seller': decision.update(action='revise',replacement_model='MX-40')
        return {'decision':decision,'usage':{'total_tokens':1}}
    monkeypatch.setattr(run,'invoke',scripted)
    env=tmp_path/'credentials'; env.write_text('OPENAI_API_KEY=test-only\nOPENAI_BASE_URL=https://example.invalid/v1\nCAI_MODEL=openai/MiniMax-M3')
    result=run.run_one(run.ROOT/'examples/letter_of_credit',env,tmp_path/'output','verified_certificate','resp')
    assert result['task_completed'] and result['resubmits']==1
    assert inputs[1][1]['bundle_version']==2
    assert inputs[1][1]['certificates']==[]  # old-version certificate cannot be reused
    assert result['calls']==6


def test_unresolved_evidence_goes_to_human(monkeypatch,tmp_path):
    def scripted(org,payload,*args):
        return {'decision':{'action':'request_evidence','checks':[],'findings':[],'public_message':'need evidence','requested_from':'buyer' if org=='seller' else 'seller'},'usage':{}}
    monkeypatch.setattr(run,'invoke',scripted)
    env=tmp_path/'env'; env.write_text('OPENAI_API_KEY=test\nOPENAI_BASE_URL=https://example.invalid')
    result=run.run_one(run.ROOT/'examples/letter_of_credit',env,tmp_path/'output','black_box','selfish')
    assert result['outcome']=='human_escalation_unresolved_evidence'
    assert not result['unsafe_completion']
