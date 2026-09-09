"""Re-audit a saved reliability model pilot without making model calls."""
import argparse
import hashlib
import json
import platform
from pathlib import Path

from trust_network.demo.evaluate_reliability_workflow import aggregate, evaluate_run
from trust_network.demo.run_reliability_multiround import _source_hashes


def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def _integrity(root):
    files=[]
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name!='raw_integrity_manifest.json':
            files.append({'path':str(path.relative_to(root)),
                          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'kind':'reliability_model_pilot_reaudit_integrity_manifest',
            'scope':'corrected derived evaluations and summaries; source raw data remain in source_pilot',
            'files':files}


def run(source_root,output_root):
    source_root=Path(source_root).resolve(); output_root=Path(output_root).resolve()
    output_root.mkdir(parents=True,mode=0o700,exist_ok=False)
    source_manifest=json.loads((source_root/'experiment_manifest.json').read_text())
    manifest={'kind':'reliability_model_pilot_posthoc_reaudit',
              'status':'running','python':platform.python_version(),
              'source_pilot':str(source_root),
              'source_pilot_manifest_sha256':hashlib.sha256(
                  (source_root/'experiment_manifest.json').read_bytes()).hexdigest(),
              'model_calls_during_reaudit':0,
              'reason':'correct accountability scope: an authority-local receipt is not a consumer notice',
              'source_hashes':_source_hashes(),
              'source_model':source_manifest.get('model')}
    _write(output_root/'reaudit_manifest.json',manifest)
    rows=[]
    for source_eval in sorted(source_root.glob('hidden_revoke/repeat_*/**/run_record.json')):
        source_run=source_eval.parent
        relative=source_run.relative_to(source_root)
        fixture=source_run.parent.parent/'fixture'
        corrected=evaluate_run(source_run,fixture,fixture/'evaluation_truth.json')
        output_run=output_root/relative
        _write(output_run/'evaluation.json',corrected)
        rows.append({'policy':corrected['policy'],'repeat':corrected['repeat'],
                     'source_run':str(source_run),'output_run':str(output_run),
                     'evaluation':corrected})
    policies=sorted({row['policy'] for row in rows})
    by_policy={policy:aggregate([row['evaluation'] for row in rows
                                 if row['policy']==policy]) for policy in policies}
    status_counts={}
    finding_counts={}
    for row in rows:
        evaluation=row['evaluation']; status=evaluation['responsibility_status']
        status_counts[status]=status_counts.get(status,0)+1
        for finding in evaluation['accountability']['findings']:
            name=finding['classification']; finding_counts[name]=finding_counts.get(name,0)+1
    metrics={'source_pilot':str(source_root),'observed_workflows':len(rows),
             'model_calls_during_reaudit':0,'by_policy':by_policy,
             'responsibility_status_counts':status_counts,
             'accountability_finding_counts':finding_counts,
             'rows':[{'policy':row['policy'],'repeat':row['repeat'],
                      'output_run':str(Path(row['output_run']).relative_to(output_root)),
                      'responsibility_status':row['evaluation']['responsibility_status'],
                      'findings':[item['classification'] for item in
                                  row['evaluation']['accountability']['findings']],
                      'responsibility_not_determined':row['evaluation']['responsibility_not_determined']}
                     for row in rows]}
    _write(output_root/'metrics.json',metrics)
    lines=['# v5 追溯结果 posthoc re-audit','',
           '本目录不包含新的模型调用；它读取 v5 已保存的 run_record、events 和 fixture，修正审计器把来源组织本地 receipt 当成消费方通知的问题。v5 原始目录保持不变。','',
           '|策略|workflow|不安全完成|程序拦截|恢复成功|责任状态为 undetermined|','|---|---:|---:|---:|---:|---:|']
    for policy in policies:
        item=by_policy[policy]
        undetermined=sum(row['evaluation']['responsibility_not_determined']
                         for row in rows if row['policy']==policy)
        lines.append(f"|{policy}|{item['total_workflows']}|{item['unsafe_completion_workflows']}|"
                     f"{item['initial_program_intervention']}|{item['recovery_succeeded']}|{undetermined}|")
    lines += ['', 'accountability finding 计数：', '',
              '|finding|count|','|---|---:|']
    for name,count in sorted(finding_counts.items()): lines.append(f'|{name}|{count}|')
    lines += ['', '解释：autonomous 的两条轨迹属于“受控变更后撤销尚未正式送达但仍使用旧根”；dependency 的两条轨迹没有旧根使用，finding 为 no_fault_conclusion。签名和事件顺序不能单独证明原始权威过错、主观意图、物理损失或数值责任。']
    (output_root/'report.md').write_text('\n'.join(lines)+'\n')
    manifest['status']='completed'; manifest['observed_workflows']=len(rows)
    manifest['output_integrity_manifest']='raw_integrity_manifest.json'
    _write(output_root/'reaudit_manifest.json',manifest)
    _write(output_root/'raw_integrity_manifest.json',_integrity(output_root))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.source,args.out),ensure_ascii=False,indent=2))
