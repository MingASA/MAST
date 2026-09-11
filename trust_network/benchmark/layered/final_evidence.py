"""Same-live-execution evidence projections; never reuse varying cross-layer denominators."""
import json
from pathlib import Path
from .storage import write_json
from .score import observation
from trust_network.benchmark.contribution.forensics import project,audit,route_label
from trust_network.benchmark.contribution.live_replay import score_reference
from trust_network.demo.documents import digest


def evaluate(output):
    output=Path(output);plan=json.loads((output/'plan.json').read_text());rows=[]
    directory=output/'evidence_projections';directory.mkdir(exist_ok=True)
    selected=[r for r in plan['runs'] if r['layer']=='L4' and r['group']=='main']
    for entry in selected:
        path=output/'runs'/entry['workflow_id']/'result.json'
        if not path.exists():continue
        raw=json.loads(path.read_text())['raw'];o=observation(raw)
        o['ordinary_logs']=[route_label(r['packet']) for r in raw['routes'] if r['accepted']]
        ex={'execution_id':digest(raw),'observation':o,'reference':{'routes':o['ordinary_logs'],
            'sources':{digest(p):p['signature']['issuer'] for p in o['claims'] if not p['body']['parents']}}}
        for view,fault in [('full','none'),('ordinary_logs','none'),('no_receipts','none'),
                           ('opaque_relay','none'),('full','missing_link'),('full','tampered_receipt')]:
            observed=project(ex,view,fault);assessed=audit(observed)
            score=score_reference(ex,observed,assessed)
            row={'fixture_id':entry['fixture_id'],'view':view,'fault':fault,
                 'execution_id':ex['execution_id'],**score}
            name=entry['workflow_id']+'_'+view+'_'+fault+'.json'
            write_json(directory/name,{'reference':ex['reference'],'observation':observed,'audit':assessed,'score':row})
            rows.append(row)
    write_json(output/'traceability.json',rows)
    (directory/'README.md').write_text('固定同一L4执行的证据投影；不是各层自然追溯准确率。缺失/篡改只有实际改变证据时才适用，见projection_applicability。来源身份不是事实责任；责任正负例复用既有独立标签。\n')
    if rows:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        labels=[('full','none'),('ordinary_logs','none'),('no_receipts','none'),('opaque_relay','none'),('full','missing_link'),('full','tampered_receipt')]
        fig,ax=plt.subplots(figsize=(12,4),layout='constrained')
        for offset,key in [(-.2,'estimated_routes'),(.2,'verified_routes')]:
            values=[]
            for view,fault in labels:
                rs=[r for r in rows if r['view']==view and r['fault']==fault]
                denominator=sum(r[key]['expected'] for r in rs)
                values.append(sum(r[key]['matched'] for r in rs)/denominator if denominator else 0)
            ax.bar([i+offset for i in range(len(labels))],values,.4,label=key)
        ax.set_xticks(range(len(labels)),[v+'/'+f for v,f in labels],rotation=15);ax.set_ylim(0,1.15);ax.legend()
        fig.savefig(output/'traceability.png',dpi=160);fig.savefig(output/'traceability.pdf');plt.close(fig)
