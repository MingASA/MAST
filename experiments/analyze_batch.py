"""Validate a completed, versioned MiniMax batch and produce descriptive plots."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from trust_network.demo.documents import Certificate,digest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def analyze(out,case):
    manifest=json.loads((out/'manifest.json').read_text())
    config=manifest['config']
    expected={(i,c) for i in range(config['repetitions']) for c in config['combinations']}
    records=[json.loads(p.read_text()) for p in sorted(out.glob('run_*/*/record.json'))]
    actual={(r['repetition'],r['combination']) for r in records}
    if expected!=actual or len(records)!=len(expected): raise ValueError('batch incomplete or duplicate run records')
    for relative,sha in manifest['case_hashes'].items():
        if hashlib.sha256((case/relative).read_bytes()).hexdigest()!=sha: raise ValueError('scenario changed')
    initial=digest(json.loads((case/'public/bundle.json').read_text()))
    signatures=0
    for r in records:
        combo=r['combination']; protocol,objective=combo.split(':')
        folder=out/f"run_{r['repetition']:03d}"/f'{protocol}_{objective}'
        if r['temperature']!=config['temperatures'][r['repetition']%len(config['temperatures'])]: raise ValueError('temperature mismatch')
        logs=list(folder.glob('*.jsonl'))+list(folder.glob('*.jsonl.interrupted'))
        events=[json.loads(line) for p in logs for line in p.read_text().splitlines()]
        if len(events)!=r['logged_calls']: raise ValueError('call count mismatch')
        if r['status']=='finished' and r['initial_bundle_hash']!=initial: raise ValueError('input bundle mismatch')
        if r['status']!='finished' and list(folder.glob('*.jsonl')): raise ValueError('failed log not preserved as interrupted')
        for event in events:
            cert=Certificate(**event['certificate'])
            pub=manifest['signing_public_keys'][event['organization']]
            if event['public_key']!=pub: raise ValueError('signing key changed during batch')
            if cert.issuer!=event['organization'] or cert.version!=event['version'] or cert.bundle_hash!=event['bundle_hash']: raise ValueError('certificate binding mismatch')
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub)).verify(bytes.fromhex(cert.signature),cert.payload())
            signatures+=1
    report={'planned_runs':len(expected),'recorded_runs':len(records),
            'status_counts':dict(Counter(r['status'] for r in records)),
            'logged_decision_calls':sum(r['logged_calls'] for r in records),
            'logged_http_attempts':sum(r['logged_api_requests'] for r in records),
            'logged_tokens':sum(r['logged_tokens'] for r in records),
            'verified_signatures':signatures,'case_hashes_unchanged':True,'batch_signing_keys_unchanged':True,
            'private_marker_hits_finished':sum(r['logged_private_marker_hits'] for r in records if r['status']=='finished'),
            'private_marker_hits_failed':sum(r['logged_private_marker_hits'] for r in records if r['status']!='finished')}
    with (out/'validation.json').open('x') as f: json.dump(report,f,indent=2)
    plot(out,records,config['combinations'])
    interpretation(out,records,config)
    return report


def interpretation(out,records,config):
    from trust_network.demo.run_batch import wilson
    lines=['# 批次结果解读','',
        '两组各15次，场景固定，温度0.2/0.5/0.8各5次。此处比较的是“黑箱+自私”和“可验证证书+责任”两个联合条件，不能把差异单独归因于证书或责任机制。',
        'resp沿用第一轮业务目标提示词，不在重复批次中改为新的遗漏结算规则。因此这批数据不构成ProportionalWithOmission在真实Agent上的效果验证。安全完成仅按现有demo执行器的有限判定规则计算，不是实际贸易合规证明。',
        '运行错误与业务结局分开。完成率及Wilson区间仅对正常返回的run计算；API/响应失败导致的选择偏差、混合温度和模型服务依赖均限制统计解释。不是数学参数拟合或机制因果有效性证明。','',
        '|组合|正常返回|运行错误|安全业务完成|升级人工|拒绝|完成率/正常返回|描述性95%区间|',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for combo in config['combinations']:
        group=[r for r in records if r['combination']==combo]
        finished=[r for r in group if r['status']=='finished']; count=sum(r['task_completed'] for r in finished)
        interval=wilson(count,len(finished)); bounds='N/A' if interval is None else f'{interval[0]:.1%}–{interval[1]:.1%}'
        rate='N/A' if not finished else f'{count/len(finished):.1%}'
        lines.append(f"|{combo}|{len(finished)}|{len(group)-len(finished)}|{count}|{sum(r['outcome'].startswith('human_escalation') for r in finished)}|{sum(r['outcome']=='rejected' for r in finished)}|{rate}|{bounds}|")
    lines+=['','|组合|温度|业务结局计数|运行错误|','|---|---:|---|---:|']
    for combo in config['combinations']:
        for temperature in config['temperatures']:
            group=[r for r in records if r['combination']==combo and r['temperature']==temperature]
            outcomes=dict(Counter(r['outcome'] for r in group if r['status']=='finished'))
            lines.append(f"|{combo}|{temperature}|{outcomes}|{sum(r['status']!='finished' for r in group)}|")
    lines+=['','无效改单触发人工升级属于执行器阻止越权或缺少必要字段的正常业务路径，不等于API失败，也不等于业务已完成。',
        '私有标记命中以含至少一个标记的输出条数累计，并分别列出正常返回和失败片段；零命中不证明没有其他形式泄露。',
        '错误日志只保留安全的异常类型，不能仅凭RuntimeError进一步区分网络、提供方和内容解析根因。没有对失败run补跑替换，因此不会只留下成功样本。',
        '原始检查范围频率在check_frequencies.csv，重提交与调用次数分布在aggregate.json；原文不同但语义近似的检查没有事后合并。']
    with (out/'interpretation.md').open('x') as f: f.write('\n'.join(lines)+'\n')


def plot(out,records,combinations):
    os.environ.setdefault('MPLCONFIGDIR','/tmp/wuxing-mpl')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    labels=['Black box + selfish' if c=='black_box:selfish' else 'Verified cert. + resp' for c in combinations]
    categories=('completed','human_escalation','rejected','terminated_resubmission_limit','error')
    bottoms=np.zeros(len(combinations)); x=np.arange(len(combinations))
    for category in categories:
        counts=[]
        for combo in combinations:
            group=[r for r in records if r['combination']==combo]
            if category=='error': count=sum(r['status']!='finished' for r in group)
            elif category=='human_escalation': count=sum(r.get('outcome','').startswith('human_escalation') for r in group if r['status']=='finished')
            else: count=sum(r.get('outcome')==category for r in group if r['status']=='finished')
            counts.append(count)
        if sum(counts):
            axes[0].bar(x,counts,bottom=bottoms,label=category); bottoms+=counts
    axes[0].set_xticks(x,labels,rotation=12); axes[0].set_ylabel('Workflow runs'); axes[0].legend(fontsize=8)
    axes[0].set_title('Outcomes (errors kept separate)')
    for offset,combo in enumerate(combinations):
        group=[r for r in records if r['combination']==combo and r['status']=='finished']
        counts=Counter(r['resubmits'] for r in group)
        axes[1].bar(np.arange(4)+(offset-.5)*.35,[counts.get(i,0) for i in range(4)],.35,label=labels[offset])
    axes[1].set_xticks(range(4)); axes[1].set_xlabel('Resubmissions'); axes[1].set_ylabel('Finished runs'); axes[1].legend(fontsize=8)
    groups=[[r['calls'] for r in records if r['combination']==combo and r['status']=='finished'] for combo in combinations]
    for i,group in enumerate(groups):
        if group:
            counter=Counter(group)
            axes[2].scatter([i]*len(counter),list(counter),s=[35*n for n in counter.values()],alpha=.65)
    axes[2].set_xticks(x,labels,rotation=12); axes[2].set_xlim(-.6,len(combinations)-.4)
    axes[2].set_ylabel('Calls per finished workflow'); axes[2].set_title('Bubble size = frequency')
    fig.suptitle('One fixed synthetic case; temperatures 0.2 / 0.5 / 0.8; descriptive observations only')
    fig.tight_layout(); fig.savefig(out/'behavior_distribution.png',dpi=180); fig.savefig(out/'behavior_distribution.svg'); plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,default=Path('results/minimax_batch_v2'))
    parser.add_argument('--case',type=Path,default=Path('examples/letter_of_credit')); args=parser.parse_args()
    print(json.dumps(analyze(args.out,args.case),indent=2))
