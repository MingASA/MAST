"""Fixed execution evidence profiles, separate from cross-layer task effects."""
import argparse
import hashlib
import json
from pathlib import Path
from trust_network.benchmark.contribution.forensics import project, audit, route_label
from trust_network.benchmark.contribution.live_replay import score_reference
from .score import observation
from trust_network.demo.documents import digest
from .spec import MAIN


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    rows=[];hashes={}
    def write(name,value):
        path=args.output/name;path.write_text(json.dumps(value,indent=2)+'\n')
        hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    for i,row in enumerate(json.loads((args.offline/'metrics.json').read_text())):
        if row['layer']!='L4' or row['case']!='active':continue
        raw=json.loads((args.offline/row['file']).read_text());o=observation(raw)
        # Align ordinary route labels to the same artifacts for this fixed trace.
        o['ordinary_logs']=[route_label(r['packet']) for r in raw['routes'] if r['accepted']]
        ex={'execution_id':hashlib.sha256((args.offline/row['file']).read_bytes()).hexdigest(),
            'observation':o,'reference':{'routes':o['ordinary_logs'],
            'sources':{digest(p):p['signature']['issuer']
                       for p in o['claims'] if not p['body']['parents']}}}
        write(str(i)+'_reference.json',{'execution_id':ex['execution_id'],'reference':ex['reference']})
        for layer,view in [*[(l,'ordinary_logs' if l=='L0' else 'full') for l in MAIN],
                           ('ablate_receipts','no_receipts'),('opaque','opaque_relay')]:
            observed=project(ex,view);assessed=audit(observed)
            write(f'{i}_{layer}_observation.json',observed)
            write(f'{i}_{layer}_audit.json',assessed)
            rows.append({'topology':row['topology'],'profile':layer,'execution_id':ex['execution_id'],
                         **score_reference(ex,observed,assessed)})
    write('metrics.json',rows)
    # Reuse independently labelled responsibility results, do not relabel live audits.
    source=Path('results/contribution_generalization_v2/report.md')
    write('prior_evidence.json',{'responsibility_report':str(source),
        'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'reuse':'independently_labeled_cases_not_added_to_new_execution_sample_count'})
    write('manifest.json',dict(hashes))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    profiles=[*MAIN,'ablate_receipts','opaque'];values=[];estimates=[]
    for layer in profiles:
        subset=[r for r in rows if r['profile']==layer]
        denom=sum(r['verified_routes']['expected'] for r in subset)
        values.append(sum(r['verified_routes']['matched'] for r in subset)/denom)
        estimates.append(sum(r['estimated_routes']['matched'] for r in subset)/denom)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained');x=list(range(len(profiles)))
    ax.bar([v-.18 for v in x],estimates,.36,label='Ordinary route estimate')
    ax.bar([v+.18 for v in x],values,.36,label='Signed route proof')
    ax.set_xticks(x,profiles);ax.set_ylim(0,1.2);ax.legend();ax.set_title('Same execution, fixed route denominator; evidence profiles only')
    fig.savefig(args.output/'fixed_traceability.png',dpi=180);plt.close(fig)
    (args.output/'report.md').write_text('# 固定轨迹证据配置\n\nL0=普通日志视图，L1–L4=完整证据视图。'
        '这是同一执行的证据消融，不是这些层自然运行后具有相同轨迹的声称。'
        'L1–L4 的追溯能力预期持平，不能为了阶梯效果人为降低中间层。\n\n'
        '来源身份不等于事实责任；独立责任正负例复用 prior_evidence.json 指向的既有实验，'
        '不重复计入样本。新执行无独立责任标签，准确率保持 null。\n\n![证据](fixed_traceability.png)\n')

if __name__=='__main__':main()
