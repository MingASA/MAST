"""Summarise a saved multi-round pilot with descriptive Wilson intervals."""
import argparse
import hashlib
import json
import math
import platform
from pathlib import Path


def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def _wilson(successes,total,z=1.959963984540054):
    if not total:
        return None
    p=successes/total
    denominator=1+(z*z/total)
    centre=(p+(z*z/(2*total)))/denominator
    radius=(z/denominator)*math.sqrt((p*(1-p)/total)+(z*z/(4*total*total)))
    return {'estimate':p,'lower':max(0.0,centre-radius),
            'upper':min(1.0,centre+radius),'successes':successes,'total':total}


def _integrity(root):
    files=[]
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name!='raw_integrity_manifest.json':
            files.append({'path':str(path.relative_to(root)),
                          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'kind':'reliability_multiround_stats_integrity_manifest',
            'scope':'posthoc statistical analysis only; source workflow data remain in source_pilot',
            'files':files}


def _count(rows,key):
    return sum(row['evaluation'].get(key,0) for row in rows)


def run(source_root,output_root):
    source_root=Path(source_root).resolve(); output_root=Path(output_root).resolve()
    output_root.mkdir(parents=True,mode=0o700,exist_ok=False)
    source_manifest=json.loads((source_root/'experiment_manifest.json').read_text())
    rows=[]
    for path in sorted(source_root.glob('*/*/*/evaluation.json')):
        evaluation=json.loads(path.read_text())
        rows.append({'path':path,'evaluation':evaluation})
    expected=source_manifest.get('planned_policy_workflows')
    if expected is not None and len(rows)!=expected:
        raise ValueError(f'expected {expected} evaluations, found {len(rows)}')
    manifest={'kind':'reliability_multiround_posthoc_stats','status':'running',
              'python':platform.python_version(),'source_pilot':str(source_root),
              'source_pilot_manifest_sha256':hashlib.sha256(
                  (source_root/'experiment_manifest.json').read_bytes()).hexdigest(),
              'model_calls_during_analysis':0,'interval':'Wilson 95% descriptive interval',
              'source_model':source_manifest.get('model')}
    _write(output_root/'analysis_manifest.json',manifest)
    conditions=sorted({row['evaluation']['condition'] for row in rows})
    policies=sorted({row['evaluation']['policy'] for row in rows})
    cells={}
    for condition in conditions:
        for policy in policies:
            selected=[row for row in rows if row['evaluation']['condition']==condition and
                      row['evaluation']['policy']==policy]
            n=len(selected)
            cells[f'{condition}/{policy}']={
                'condition':condition,'policy':policy,'workflow_count':n,
                'safe_completion':_wilson(_count(selected,'safe_completion_workflows'),n),
                'unsafe_completion':_wilson(_count(selected,'unsafe_completion_workflows'),n),
                'program_intervention':_wilson(_count(selected,'initial_program_intervention'),n),
                'recovery_success':_wilson(_count(selected,'recovery_succeeded'),n)
                    if condition=='hidden_revoke' else None,
                'unaffected_task_completion':_wilson(_count(selected,'unaffected_task_completed'),
                                                     _count(selected,'unaffected_task_submitted')),
                'model_holds':_count(selected,'model_hold_count'),
                'parser_invalid_workflows':_count(selected,'initial_model_parser_invalid'),
                'provider_failures':_count(selected,'model_failure_count'),
                'model_decisions':_count(selected,'model_decision_count'),
                'provider_attempts':_count(selected,'model_attempts_recorded'),
                'known_total_tokens':_count(selected,'known_total_tokens'),
                'verification_queries':_count(selected,'verification_queries'),
                'accountability_findings':sorted({finding['classification']
                    for row in selected for finding in row['evaluation']['accountability']['findings']})}
    strategy_totals={}
    for policy in policies:
        selected=[row for row in rows if row['evaluation']['policy']==policy]
        hidden=[row for row in selected if row['evaluation']['condition']=='hidden_revoke']
        n=len(selected); hn=len(hidden)
        strategy_totals[policy]={
            'workflow_count':n,
            'safe_completion':_wilson(_count(selected,'safe_completion_workflows'),n),
            'unsafe_completion':_wilson(_count(selected,'unsafe_completion_workflows'),n),
            'hidden_recovery_success':_wilson(_count(hidden,'recovery_succeeded'),hn),
            'hidden_program_intervention':_wilson(_count(hidden,'initial_program_intervention'),hn),
            'unaffected_task_completion':_wilson(_count(selected,'unaffected_task_completed'),
                                                 _count(selected,'unaffected_task_submitted')),
            'model_decisions':_count(selected,'model_decision_count'),
            'provider_attempts':_count(selected,'model_attempts_recorded'),
            'known_total_tokens':_count(selected,'known_total_tokens'),
            'verification_queries':_count(selected,'verification_queries'),
            'model_holds':_count(selected,'model_hold_count'),
            'provider_failures':_count(selected,'model_failure_count')}
    findings={}
    for row in rows:
        for item in row['evaluation']['accountability']['findings']:
            name=item['classification']; findings[name]=findings.get(name,0)+1
    metrics={'source_pilot':str(source_root),'model_calls_during_analysis':0,
             'workflow_count':len(rows),'conditions':conditions,'policies':policies,
             'cells':cells,'strategy_totals':strategy_totals,
             'accountability_finding_counts':findings,
             'limitations':['Wilson intervals are descriptive for the fixed pilot sample',
                            'simulated effects are not physical side-effect evidence',
                            'workflow observations share fixture and protocol structure']}
    _write(output_root/'metrics.json',metrics)
    lines=['# 扩大多轮实验的统计 posthoc 分析','',
           f'来源：`{source_root}`；本分析新增模型调用为 0。区间是固定样本上的 Wilson 95% 描述性区间，不是跨部署或总体可靠性的证明。','',
           '|条件|策略|N|安全完成|不安全完成|程序拦截|恢复成功|无关任务完成|模型 hold|查证次数|token|','|---|---|---:|---|---|---|---|---|---:|---:|---:|']
    def fmt(item):
        if item is None: return '—'
        return f"{item['successes']}/{item['total']} [{item['lower']:.3f}, {item['upper']:.3f}]"
    for name,item in cells.items():
        lines.append(f"|{item['condition']}|{item['policy']}|{item['workflow_count']}|"
                     f"{fmt(item['safe_completion'])}|{fmt(item['unsafe_completion'])}|"
                     f"{fmt(item['program_intervention'])}|{fmt(item['recovery_success'])}|"
                     f"{fmt(item['unaffected_task_completion'])}|{item['model_holds']}|"
                     f"{item['verification_queries']}|{item['known_total_tokens']}|")
    lines += ['', '策略总计：', '',
              '|策略|N|安全完成|不安全完成|hidden recovery|模型决定|provider尝试|查证次数|token|','|---|---:|---|---|---|---:|---:|---:|---:|']
    for policy,item in strategy_totals.items():
        lines.append(f"|{policy}|{item['workflow_count']}|{fmt(item['safe_completion'])}|"
                     f"{fmt(item['unsafe_completion'])}|{fmt(item['hidden_recovery_success'])}|"
                     f"{item['model_decisions']}|{item['provider_attempts']}|{item['verification_queries']}|"
                     f"{item['known_total_tokens']}|")
    lines += ['', 'accountability findings：', '']
    for name,count in sorted(findings.items()): lines.append(f'- `{name}`: {count}')
    lines += ['', '这些区间很宽，尤其 hidden_revoke 每个 cell 只有 6 个 workflow。它们支持方向判断：程序拦截稳定出现，但 recovery 的成功率受真实模型在旧/新来源并存时是否接受恢复契约影响；不能把当前比例外推为生产错误率。']
    (output_root/'report.md').write_text('\n'.join(lines)+'\n')
    manifest['status']='completed'; manifest['workflow_count']=len(rows)
    manifest['output_integrity_manifest']='raw_integrity_manifest.json'
    _write(output_root/'analysis_manifest.json',manifest)
    _write(output_root/'raw_integrity_manifest.json',_integrity(output_root))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.source,args.out),ensure_ascii=False,indent=2))
