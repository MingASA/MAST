"""A typed relay is an explicit model choice, never a repaired fact or hold."""
import pytest
from trust_network.benchmark.workflow.backend import MemoryBackend,ProcessBackend
from trust_network.benchmark.workflow.spec import workload,ARMS
from trust_network.benchmark.workflow.engine import Workflow
from trust_network.benchmark.workflow.evaluate import score,audit
from trust_network.demo.documents import digest


@pytest.mark.parametrize('process',[False,True])
def test_owner_local_reference_validation(tmp_path,process):
    f=workload();backend=(ProcessBackend(f,ARMS['dependency'],tmp_path/'orgs') if process else MemoryBackend(f,ARMS['dependency']))
    root=f['roots']['A'];cid=digest(root)
    backend.call('coordinator',{'operation':'receive','packet':root})
    req={'operation':'reliability_sign_derived','parents':[cid],'fact_ref':cid,'rule':'relay'}
    out=backend.call('coordinator',req)
    assert out['packet']['body']['fact']==root['body']['fact']
    assert out['packet']['body']['parents']==[cid]
    wrong={**root['body']['fact'],'predicate':'invented'}
    assert 'packet' not in backend.call('coordinator',{'operation':'reliability_sign_derived','parents':[cid],'fact':wrong})
    for patch in [{'fact_ref':'missing'},{'fact':root['body']['fact']},{'rule':'sum_charges'},{'parents':[]}]:
        assert 'packet' not in backend.call('coordinator',{**req,**patch})


def test_reference_tape_recovery_and_no_implicit_repair():
    f=workload()
    raw,_=Workflow(MemoryBackend(f,ARMS['dependency']),'intermediate_retraction','dependency').run()
    tape={d['stage']:({k:v for k,v in d['draft'].items() if k!='fact'}|{'fact_ref':d['draft']['claims'][0]}
        if d['draft']['action']=='proceed' else d['draft']) for d in raw['decisions']}
    # Recovery envelope hashes vary, so replay of their exact IDs deliberately
    # remains unsupported; initial reference decisions must still realize fault.
    replay,truth=Workflow(MemoryBackend(f,ARMS['dependency']),'intermediate_retraction','dependency',tape=tape).run()
    m=score(replay,truth,audit(replay))
    assert m['fault_realized'] and m['containment_evaluable']
    assert m['unsafe_completed']==0
    for d in replay['decisions']:
        view=d['public_input'];assert all(cid in view['evidence_index'] for cid in view['required_parent_claims'])
    hold,truth=Workflow(MemoryBackend(f,ARMS['dependency']),'intermediate_retraction','dependency',tape={}).run()
    m=score(hold,truth,audit(hold))
    assert m['validity_reason']=='fault_not_realized' and not m['containment_evaluable']
    assert m['unrelated_overfreeze']==0 and m['unrelated_noncompletion']==2


def test_action_reference_resolves_only_explicit_local_index():
    f=workload();backend=MemoryBackend(f,ARMS['dependency'])
    raw,_=Workflow(backend,'active','dependency').run()
    task=next(d for d in raw['decisions'] if d['stage']=='invoice:A:a')
    claims=task['public_input']['candidate_claims']['task']
    assert task['public_input']['claim_id_index']=={'task[0]':claims[0],'task[1]':claims[1]}
    tape={d['stage']:d['draft'] for d in raw['decisions']}
    tape['invoice:A:a']={'action':'approve','claim_refs':['task[0]','task[1]'],'reason':'明确引用本任务证据'}
    replay,truth=Workflow(MemoryBackend(f,ARMS['dependency']),'active','dependency',tape=tape).run()
    invoice=next(e for e in replay['events'] if e['kind']=='task_end' and e['task']=='invoice:A:a' and e['phase']=='work')
    assert invoice['action']=='COMPLETED'
    tape['invoice:A:a']={'action':'approve','claim_refs':['task[9]'],'reason':'错误索引'}
    rejected,truth=Workflow(MemoryBackend(f,ARMS['dependency']),'active','dependency',tape=tape).run()
    invoice=next(e for e in rejected['events'] if e['kind']=='task_end' and e['task']=='invoice:A:a' and e['phase']=='work')
    assert invoice['action']=='MODEL_INVALID'
