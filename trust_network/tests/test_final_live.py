import copy
import json
import pytest
from trust_network.benchmark.layered.final_plan import make_plan,verify_plan,fixture
from trust_network.benchmark.layered.engine import Run
from trust_network.benchmark.layered.final_run import execute,inspect_journals
from trust_network.benchmark.layered.final_score import task_rows
from trust_network.benchmark.layered.final_summary import cluster_interval
from trust_network.benchmark.layered.storage import write_json
from trust_network.demo import provider


def test_plan_semantics_and_fixed_denominators():
    p=make_plan();fs=verify_plan(p)
    assert sum(r['group']=='main' for r in p['runs'])==300
    assert sum(r['group']=='ablation' for r in p['runs'])==50
    for f in fs.values():
        other=fixture(f['topology'],f['case'],1-f['repetition'])
        assert f['business']!=other['business']
        assert f['evaluation']['affected_tasks']==other['evaluation']['affected_tasks']
        assert len(f['graph']['tasks'])==4
    bad=copy.deepcopy(p);bad['runs'][0]['layer']='L4'
    with pytest.raises(ValueError):verify_plan(bad)


@pytest.mark.parametrize('topology,case,layer',[
    ('long_chain_fork','active','L0'),
    ('converge_then_fork','signed_false','L4'),
    ('reused_org_independent','confirmed_repair','L4')])
def test_changed_business_runtime(topology,case,layer,tmp_path):
    f=fixture(topology,case,1)
    raw=Run(topology,case,layer,fixture=f).run()
    assert raw['truth']['expected_cents']==f['evaluation']['private_expected_cents']
    assert raw['truth']['affected_tasks']==f['evaluation']['affected_tasks']
    assert raw['metrics']['unsafe_completion_count']==0
    if case in ('active','confirmed_repair'):assert raw['metrics']['safe_final_completion']==4
    assert all(d['public_input'].get('evaluation') is None for d in raw['decisions'])
    assert len(task_rows(f,raw))==4
    if case=='active':
        other=Run(topology,case,layer,backend='process',directory=tmp_path/'workers',fixture=f).run()
        assert other['metrics']['safe_final_completion']==raw['metrics']['safe_final_completion']


def test_attempt_journal_written_before_request(monkeypatch):
    events=[]
    def reply(config,system,prompt):
        assert events[-1]['status']=='attempt_started'
        return {'action':'hold'},{'total_tokens':3,'prompt_tokens':2,'completion_tokens':1},{},'{}',{}
    monkeypatch.setattr(provider,'_complete_once_trace',reply)
    provider.complete_traced(provider.ProviderConfig('m','https://example.invalid','secret'),'s','p',journal=events.append)
    assert [e['status'] for e in events]==['attempt_started','attempt_returned']
    assert 'secret' not in json.dumps(events)


def test_resume_never_reissues_started_workflow(tmp_path,monkeypatch):
    f=fixture('long_chain_fork','active',0);e={'workflow_id':'w0000','layer':'L0'}
    directory=tmp_path/'runs'/'w0000';directory.mkdir(parents=True)
    write_json(directory/'state.json',{'status':'started'})
    monkeypatch.setattr(Run,'run',lambda self:pytest.fail('must not repeat paid workflow'))
    assert execute(tmp_path,e,f,live=True)=='unknown'
    assert inspect_journals(directory)['calls_started']==0
    assert all(t['unsafe_completion'] is None for t in task_rows(f))


def test_cluster_uses_fixture_values():
    result=cluster_interval([1,1,1])
    assert result['fixtures']==3 and result['interval_95']==[1,1]
    assert cluster_interval([])['mean'] is None


def test_failed_attempt_retains_received_usage(monkeypatch):
    events=[]
    def fail(*args):
        error=RuntimeError('truncated')
        error.provider_response={'usage':{'total_tokens':9},'response_text':'received'}
        raise error
    monkeypatch.setattr(provider,'_complete_once_trace',fail)
    with pytest.raises(provider.ProviderTraceError):
        provider.complete_traced(provider.ProviderConfig('m','https://example.invalid','secret'),'s','p',journal=events.append)
    assert events[-1]['status']=='attempt_failed' and events[-1]['usage']['total_tokens']==9
