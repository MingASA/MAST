"""Run a small real-model pilot focused on standardized revocation recovery.

Only the hidden-revocation condition is used. Autonomous is retained as a
baseline and dependency is the mechanism arm. This pilot is deliberately
bounded and validates recovery-evidence-v1; it is not a replacement for the
larger C comparison.
"""
import argparse
import hashlib
import json
import platform
from pathlib import Path

from trust_network.demo.evaluate_reliability_workflow import aggregate, evaluate_run
from trust_network.demo.prepare_reliability_workflow import prepare
from trust_network.demo.provider import ProviderConfig
from trust_network.demo.run_reliability_multiround import (
    MAX_MODEL_DECISIONS_PER_WORKFLOW, _source_hashes, run_workflow)


POLICIES=('autonomous','dependency')
REPEATS=2
CONDITION='hidden_revoke'


def _write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def _integrity(root):
    files=[]
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name!='raw_integrity_manifest.json':
            files.append({'path':str(path.relative_to(root)),
                          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'kind':'real_model_pilot_integrity_manifest',
            'scope':'all generated raw and derived files except this manifest',
            'files':files,
            'note':'No API key or environment file is copied into the output.'}


def _report(output,metrics,rows,model):
    lines=['# 标准恢复证据 bundle 真实模型小 pilot','',
           '本轮只测试 hidden_revoke；autonomous 是基线，dependency 是当前机制臂。'
           '每组 2 个 workflow，每个 workflow 最多 4 次模型决定。样本用于接线验证，'
           '不作总体可靠性结论。','',
           f'模型：{model}；真实模型决定上限：{len(POLICIES)*REPEATS*MAX_MODEL_DECISIONS_PER_WORKFLOW}。','',
           '|策略|workflow|安全完成|不安全完成|程序拦截|恢复来源替换|派生重建|恢复重决策|恢复成功|无关任务完成|模型决定|provider失败|token|',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for policy in POLICIES:
        row=metrics['by_policy'][policy]
        lines.append('|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|'.format(
            policy,row['total_workflows'],row['safe_completion_workflows'],
            row['unsafe_completion_workflows'],row['initial_program_intervention'],
            row['recovery_source_replaced'],row['recovery_rebuild_completed'],
            row['recovery_redecision_count'],row['recovery_succeeded'],
            row['unaffected_task_completed'],row['model_decision_count'],
            row['model_failure_count'],row['known_total_tokens']))
    lines += ['', '逐 workflow 结果：', '',
              '|repeat|策略|initial invoice|recovery invoice|program interception|replacement|rebuild|receiver redecision|error|',
              '|---:|---|---|---|---|---|---|---|---|']
    for row in rows:
        e=row['eval']; recovery=e.get('recovery_error')
        lines.append('|{}|{}|{}|{}|{}|{}|{}|{}|{}|'.format(
            row['repeat'],row['policy'],
            row['initial_action'],row['recovery_action'],
            e['initial_program_intervention'],e['recovery_source_replaced'],
            e['recovery_rebuild_completed'],e['recovery_redecision_count'],
            json.dumps(recovery,ensure_ascii=False)))
    lines += ['', '结果解释：', '',
              '- 真实模型输出、provider 尝试和失败均保留在各 workflow 的 model_calls、run_record 和 events 中。',
              '- 恢复成功必须同时满足新来源、派生声明重建、receiver 新决策和最终动作完成；hold、provider failure 或非法结构不算成功。',
              '- 这次只验证修复后的恢复路径是否能被真实模型走通；若仍失败，按失败阶段修复，不重抽到正结果。',
              '- 所有动作仍是模拟适配器报告，不证明真实付款、发货、物理副作用或法律责任。']
    (output/'report.md').write_text('\n'.join(lines)+'\n')


def run(output,env_file):
    output=Path(output).resolve()
    output.mkdir(parents=True,mode=0o700,exist_ok=False)
    provider=ProviderConfig.load(Path(env_file))
    fixture=output/CONDITION/'fixture'
    prepare(fixture,CONDITION)
    manifest={'kind':'real_model_recovery_validation_pilot','status':'running',
              'python':platform.python_version(),'condition':CONDITION,
              'repeats_per_policy':REPEATS,'policies':list(POLICIES),
              'planned_policy_workflows':len(POLICIES)*REPEATS,
              'max_model_decisions_per_workflow':MAX_MODEL_DECISIONS_PER_WORKFLOW,
              'hard_model_decision_cap':len(POLICIES)*REPEATS*MAX_MODEL_DECISIONS_PER_WORKFLOW,
              'hard_provider_attempt_cap':len(POLICIES)*REPEATS*MAX_MODEL_DECISIONS_PER_WORKFLOW*2,
              'model':provider.model,'provider_base_url':provider.base_url,
              'sampling':{'max_completion_tokens':provider.max_tokens,
                          'temperature':provider.temperature,'reasoning_split':True,
                          **({'thinking':{'type':'disabled'}}
                             if provider.model=='MiniMax-M3' else {})},
              'source_hashes':_source_hashes(),
              'runtime_truth_accessed':False,
              'stop_rule':'two repeats per policy; no redraw after hold/failure; stop at hard cap',
              'previous_stage':'results/next_agent_multiround_expanded_v1',
              'recovery_input_revision':'recovery-evidence-v1 bundle: signed envelope, replacement offer, replacement source, coordinator registration',
              'validation_artifacts':['metrics.json','report.md','raw_integrity_manifest.json']}
    _write(output/'experiment_manifest.json',manifest)
    rows=[]
    for repeat in range(REPEATS):
        for policy in POLICIES:
            run_dir=output/CONDITION/f'repeat_{repeat:02d}'/policy
            run_dir.mkdir(parents=True,mode=0o700)
            run_workflow(fixture,run_dir,env_file,CONDITION,repeat,policy,
                         MAX_MODEL_DECISIONS_PER_WORKFLOW)
            evaluation=evaluate_run(run_dir,fixture,fixture/'evaluation_truth.json')
            _write(run_dir/'evaluation.json',evaluation)
            _write(run_dir/'accountability.json',evaluation['accountability'])
            batches=evaluation.get('accountability',{}).get('action_uses',{})
            initial_action='unknown'; recovery_action='none'
            record=json.loads((run_dir/'run_record.json').read_text())
            for batch in record['batches']:
                for item in batch['outputs']:
                    if item['proposal']=='invoice-A':
                        if batch['stage']=='initial': initial_action=item['action']
                        if batch['stage']=='recovery': recovery_action=item['action']
            rows.append({'repeat':repeat,'policy':policy,'run_dir':str(run_dir),
                         'initial_action':initial_action,'recovery_action':recovery_action,
                         'eval':evaluation,'accountability_outputs':batches})
    by_policy={policy:aggregate([row['eval'] for row in rows if row['policy']==policy])
               for policy in POLICIES}
    metrics={'planned_policy_workflows':manifest['planned_policy_workflows'],
             'observed_policy_workflows':len(rows),
             'hard_model_decision_cap':manifest['hard_model_decision_cap'],
             'hard_provider_attempt_cap':manifest['hard_provider_attempt_cap'],
             'by_policy':by_policy,
             'new_model_calls_during_evaluation':0,
             'all_event_chains_valid':all(row['eval']['event_chain_valid'] for row in rows),
             'all_raw_accountability_reports_present':all(
                 (Path(row['run_dir'])/'accountability.json').exists() for row in rows),
             'rows':[{'repeat':row['repeat'],'policy':row['policy'],
                      'run_directory':row['run_dir'],
                      'initial_action':row['initial_action'],
                      'recovery_action':row['recovery_action'],
                      'recovery_error':row['eval']['recovery_error']}
                     for row in rows]}
    _write(output/'metrics.json',metrics)
    _report(output,metrics,rows,provider.model)
    manifest['status']='completed'
    manifest['observed_policy_workflows']=len(rows)
    manifest['observed_model_decisions']=sum(row['eval']['model_decision_count'] for row in rows)
    manifest['observed_provider_attempts']=sum(row['eval']['model_attempts_recorded'] for row in rows)
    manifest['observed_provider_failures']=sum(row['eval']['model_failure_count'] for row in rows)
    manifest['raw_integrity_manifest']='raw_integrity_manifest.json'
    _write(output/'experiment_manifest.json',manifest)
    _write(output/'raw_integrity_manifest.json',_integrity(output))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.out,args.env_file),ensure_ascii=False,indent=2))
