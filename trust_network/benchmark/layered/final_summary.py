"""Descriptive paired fixture bootstrap; incomplete workflows retain planned denominators."""
import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from .storage import write_json
from .final_plan import verify_plan
from .final_score import task_rows
from .final_run import inspect_journals


def cluster_interval(values,seed=911,repeats=2000):
    if not values:return {'mean':None,'interval_95':None,'fixtures':0}
    rng=random.Random(seed);n=len(values)
    estimates=sorted(sum(rng.choice(values) for _ in range(n))/n for _ in range(repeats))
    return {'mean':sum(values)/n,'interval_95':[estimates[int(.025*repeats)],estimates[int(.975*repeats)]],
            'fixtures':n,'method':'percentile bootstrap of fixture-level means; descriptive controlled-fixture interval'}


def summarize(output):
    output=Path(output);plan=json.loads((output/'plan.json').read_text());fixtures=verify_plan(plan)
    rows=[];tasks=[];unknown=[]
    for entry in plan['runs']:
        f=fixtures[entry['fixture_id']];directory=output/'runs'/entry['workflow_id'];p=directory/'result.json'
        if p.exists():
            value=json.loads(p.read_text());raw=value['raw'];m=raw['metrics'];tr=value['task_metrics']
            status='completed';extra=value['exposure']
        else:
            raw=None;m={};tr=task_rows(f);extra={};status='unknown' if (directory/'state.json').exists() else 'not_started'
            unknown.append(entry['workflow_id'])
        for t in tr:tasks.append({**entry,**t})
        journal=inspect_journals(directory)
        rows.append({**entry,'topology':f['topology'],'case':f['case'],'repetition':f['repetition'],'status':status,
            **m,'planned_tasks':len(tr),'planned_affected':len(f['evaluation']['affected_tasks']),
            'unknown_tasks':sum(t['result_unknown'] for t in tr),
            'true_model_holds':None if raw is None else sum(d['draft'].get('action')=='hold' and d.get('decision_origin')=='model' for d in raw['decisions']),
            'budget_holds':None if raw is None else sum(d.get('decision_origin')=='budget' for d in raw['decisions']),
            'error_seen_org_count':len(extra.get('error_seen_organizations',[])) if raw else None,
            'error_citing_org_count':len(extra.get('error_citing_organizations',[])) if raw else None,
            'message_bytes':extra.get('message_bytes'),
            'journal_calls':journal['calls_started'],'journal_attempts':journal['provider_attempts'],
            'journal_known_tokens':journal['known_tokens'],'journal_unknown_usage':journal['unknown_usage_attempts'],
            'recovery_requests':len(raw.get('recovery_requests',[])) if raw else None,
            'authority_confirmed':int((raw.get('source_revision') or {}).get('status')=='confirmed_offer') if raw else None})
    write_json(output/'aggregate.json',rows);write_json(output/'task_metrics.json',tasks)
    fields=sorted(set().union(*(r.keys() for r in rows)))
    with (output/'aggregate.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    by_fixture=defaultdict(dict)
    for r in rows:
        if r['group']=='main':by_fixture[r['fixture_id']][r['layer']]=r
    paired=[]
    for lower,upper in [('L0','L1'),('L1','L2'),('L2','L3'),('L3','L4')]:
        for metric in ('unsafe_completion_count','safe_final_completion','post_fault_error_organizations','overfrozen_tasks','known_tokens'):
            deltas=[]
            for fid,arms in by_fixture.items():
                a,b=arms[lower],arms[upper]
                if a['status']==b['status']=='completed' and a.get(metric) is not None and b.get(metric) is not None:
                    delta=b[metric]-a[metric];deltas.append(delta)
                    paired.append({'fixture_id':fid,'comparison':upper+' minus '+lower,'metric':metric,'delta':delta})
    write_json(output/'paired_differences.json',paired)
    intervals=[]
    for comparison in sorted({r['comparison'] for r in paired}):
        for metric in sorted({r['metric'] for r in paired}):
            values=[r['delta'] for r in paired if r['comparison']==comparison and r['metric']==metric]
            intervals.append({'comparison':comparison,'metric':metric,**cluster_interval(values)})
    write_json(output/'cluster_intervals.json',intervals)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    layers=['L0','L1','L2','L3','L4'];fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    for ax,(metric,title) in zip(axes.flat,[('unsafe_completion_count','Observed unsafe tasks (show unknown separately)'),
            ('error_action_blocks','Program blocks of unsafe candidates'),('true_model_holds','Actual model holds'),
            ('post_fault_error_organizations','Error recipient organizations, summed'),
            ('safe_final_completion','Safe final tasks'),('journal_known_tokens','Known tokens incl. incomplete calls')]):
        vals=[sum(r.get(metric) or 0 for r in rows if r['group']=='main' and r['layer']==l) for l in layers]
        ax.bar(layers,vals);ax.set_title(title,fontsize=10)
    fig.savefig(output/'main_results.png',dpi=160);fig.savefig(output/'main_results.pdf');plt.close(fig)
    counts={s:sum(r['status']==s for r in rows) for s in ('completed','unknown','not_started')}
    lines=['# 最终统一live结果（如有未完成行则为阶段报告）','',f'计划主矩阵300条，次级消融50条。状态：{counts}。',
        '', '分母固定：每层60个受控fixture，240个任务；任务未知不删行，不算安全完成。bootstrap按fixture重采样，',
        '两种业务变体不代表一般现实分布；各层是不同模型路径，配对差值不是严格因果估计。',
        '初始图由脚本生成，业务动作模拟，跨组织使用本机独立进程，权威查询为同步虚拟零延迟。',
        '', '|层|完成workflow/计划|已观察错误任务/计划任务|未知任务|安全最终完成|模型hold|预算hold|',
        '|---|---:|---:|---:|---:|---:|---:|']
    for layer in layers:
        rs=[r for r in rows if r['group']=='main' and r['layer']==layer]
        total=lambda key:sum(r.get(key) or 0 for r in rs)
        lines.append(f"|{layer}|{sum(r['status']=='completed' for r in rs)}/{len(rs)}|{total('unsafe_completion_count')}/{total('planned_tasks')}|{total('unknown_tasks')}|{total('safe_final_completion')}|{total('true_model_holds')}|{total('budget_holds')}|")
    lines+=['','错误数/计划任务是已观察下界；未知项不能当作已知安全。具体场景、拓扑、重复和消融见aggregate.csv。',
        '追溯主张沿用固定执行证据投影，不能拿各层不同执行的route_proof_coverage分母比较责任准确率。',
        '责任标签沿用contribution_generalization_v2；UNKNOWN/错误修订/错绑/过期/重放边界沿用dispute_safety_negative_offline_20260910；不重复计入新样本。',
        '', '![主结果](main_results.png)']
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    write_json(output/'progress.json',{'status':'completed' if not unknown else 'partial','planned':350,**counts})
    from .final_evidence import evaluate
    evaluate(output)
    manifest={}
    for p in sorted(output.rglob('*')):
        if not p.is_file() or 'workers' in p.parts or p.suffix in ('.lock','.pending') or p.name in ('lock','manifest.json'):continue
        manifest[str(p.relative_to(output))]=hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(output/'manifest.json',{'public_files':manifest,'private_exclusions':'per-workflow private_manifest.json records hashes/counts; private data not published'})
