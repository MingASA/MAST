import json
import pytest
from trust_network.demo import run_batch
from trust_network.demo.run_batch import BatchConfig,estimate,aggregate,run_record,case_hashes


def test_cost_estimate_has_no_calls(monkeypatch):
    monkeypatch.setattr(run_batch,'run_one',lambda *a,**k:pytest.fail('estimate called API'))
    result=estimate(BatchConfig())
    assert result['workflow_runs']==30 and result['mean_based_calls']==195
    assert result['mean_based_tokens']==358225
    assert result['selected_history_based_tokens']==379410


def test_error_kept_separate_and_partial_preserved(monkeypatch,tmp_path):
    case=tmp_path/'case'; case.mkdir(); (case/'truth.json').write_text('{"value":1}')
    def fails(case,env,folder,protocol,objective,**kwargs):
        event={'usage':{'total_tokens':4},'private_marker_leaked':True,'decision':{'checks':['scope A']}}
        (folder/f'{protocol}_{objective}.jsonl').write_text(json.dumps(event)+'\n')
        raise RuntimeError('network failed')
    monkeypatch.setattr(run_batch,'run_one',fails)
    result=run_record(0,'black_box:selfish',BatchConfig(),case,tmp_path/'unused',tmp_path/'out',case_hashes(case))
    assert result['status']=='error' and result['logged_calls']==1
    assert list((tmp_path/'out').rglob('*.jsonl.interrupted'))
    report=aggregate([result])[0]
    assert report['finished_runs']==0 and report['error_runs']==1
    assert report['outcomes']=={} and report['private_marker_hits_finished']==0
    assert report['private_marker_hits_failed_partial']==1


def test_distributions_count_all_runs_and_temperature_strata():
    base={'combination':'black_box:selfish','status':'finished','temperature':.2,'outcome':'completed','resubmits':1,'calls':6,'logged_private_marker_hits':2,'logged_calls':6,'logged_tokens':100,'checks_selected':['scope','scope'],'task_completed':True,'unsafe_completion':False}
    report=aggregate([dict(base,repetition=0),dict(base,repetition=1,outcome='rejected',task_completed=False)])[0]
    assert report['outcomes']=={'completed':1,'rejected':1}
    assert report['private_marker_hits_finished']==4
    assert report['checks_exact_text_frequency']=={'scope':4}
    assert report['resubmit_distribution']=={1:2}


def test_collect_interrupted_never_restarts_requests(monkeypatch,tmp_path):
    monkeypatch.setattr(run_batch,'run_one',lambda *a,**kw:pytest.fail('recovery restarted API'))
    (tmp_path/'manifest.json').write_text(json.dumps({'config':{'repetitions':2,'combinations':['black_box:selfish'],'temperatures':[.2]}}))
    folder=tmp_path/'run_000'/'black_box_selfish'; folder.mkdir(parents=True)
    event={'usage':{},'private_marker_leaked':False,'decision':{'checks':['scope']}}
    (folder/'black_box_selfish.jsonl').write_text(json.dumps(event)+'\n{"partial":')
    records=run_batch.collect_existing(tmp_path)
    assert [r['status'] for r in records]==['interrupted','not_started']
    assert records[0]['logged_calls']==1 and records[0]['truncated_log_line']
    assert list(folder.glob('*.jsonl.interrupted'))


def test_sampling_is_transport_only_not_extra_business_prompt(monkeypatch):
    from trust_network.demo import worker
    from trust_network.demo.provider import ProviderConfig
    seen=[]
    def complete(config,system,prompt):
        seen.append((config.temperature,prompt))
        return {'action':'pass','checks':[],'findings':[],'public_message':'ok'},{}
    monkeypatch.setattr(worker,'complete',complete)
    worker.handle('own dossier',ProviderConfig('m','https://example.invalid','test'),{'documents':{'a':1},'_sampling_temperature':.8})
    assert seen[0][0]==.8 and '_sampling_temperature' not in seen[0][1]
