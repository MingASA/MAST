"""Read-only comparison of four existing graphs and round-2 equilibria."""
import argparse
import csv
from pathlib import Path
from trust_network.scenarios.synthetic import synthetic_random,SyntheticConfig
from trust_network.scenarios.letter_of_credit import letter_of_credit


def downstream_concentration(graph):
    """E[1{visit v} * strictly subsequent loss] / E[total loss], all-pass.

    Forward reach/error mass and affine backward loss integrate the original
    routing and error process exactly; this does not solve a new equilibrium.
    """
    order=graph.topological()
    reach={v:0. for v in order}; corrupt=dict(reach)
    reach[graph.source]=1.; corrupt[graph.source]=graph.node(graph.source).alpha
    for v in order:
        for edge in graph.outgoing(v):
            w=edge.v; alpha=graph.node(w).alpha
            reach[w]+=edge.q_uv*reach[v]
            corrupt[w]+=edge.q_uv*(alpha*reach[v]+(1-alpha)*edge.p_uv*corrupt[v])
    affine={}; downstream={}
    for v in reversed(order):
        a=b=0.
        for edge in graph.outgoing(v):
            aw,bw=affine[edge.v]; alpha=graph.node(edge.v).alpha
            a+=edge.q_uv*(aw+bw*alpha)
            b+=edge.q_uv*bw*(1-alpha)*edge.p_uv
        downstream[v]=(a,b)
        node=graph.node(v)
        affine[v]=(a+(node.L if node.forced_penalty else 0.),
                   b+(0. if node.forced_penalty else node.L))
    a,b=affine[graph.source]; total=a+b*graph.node(graph.source).alpha
    rows=[]
    for node in graph.nodes:
        if node.type!='verify': continue
        a,b=downstream[node.id]
        loss=a*reach[node.id]+b*corrupt[node.id]
        rows.append({'node':str(node.id),'reach_probability':reach[node.id],
            'downstream_expected_loss':loss,'total_expected_loss':total,
            'concentration':loss/total if total else None})
    return rows


def analyze(source,out):
    with source.open() as stream: historical=list(csv.DictReader(stream))
    out.mkdir(parents=True,exist_ok=False)
    cases=[('synthetic',seed,synthetic_random(SyntheticConfig(seed=seed))) for seed in (7,11,23)]
    cases.append(('letter_of_credit',0,letter_of_credit()))
    nodes=[]; summaries=[]
    for name,seed,graph in cases:
        rows=downstream_concentration(graph)
        nodes.extend(dict(scenario=name,seed=seed,**r) for r in rows)
        selected=[r for r in historical if r['scenario']==name and int(r['seed'])==seed
                  and r['protocol']=='black_box' and r['alignment']=='baseline']
        values={r['w_omit']:float(r['observed_poa']) for r in selected if r['w_omit'] in ('0.0','1.0')}
        summaries.append({'scenario':name,'seed':seed,'verify_nodes':len(rows),
            'max_concentration':max(r['concentration'] for r in rows),
            'mean_concentration':sum(r['concentration'] for r in rows)/len(rows),
            'poa_w0':values['0.0'],'poa_w1':values['1.0'],
            'poa_improvement':values['0.0']-values['1.0'],
            'relative_improvement':1-values['1.0']/values['0.0']})
    for filename,rows in (('nodes.csv',nodes),('comparison.csv',summaries)):
        with (out/filename).open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    lines=['# 第三轮：下游价值集中度（已有4图）','',
        '固定所有verify为pass，沿用原路由、错误生成/传播与损失参数。令T为全路径损失，T>v为访问v后严格下游的损失：',
        '`C(v) = E[1{访问v} × T>v] / E[T]`。分子含到达概率，不能把罕见重提交副本条件下的高损失当作全局高集中度。',
        '普通损失为L×错误状态；强制终止罚按原模型无条件计入。分母不含检查成本，因为参照策略不检查。',
        '用前向到达/错误质量与后向仿射损失精确积分，无Monte Carlo、无新sweep。节点集中度可重叠，不相加为1。',
        '这是经过该位置之后的价值分布，含随后新生错误与不可避免终止罚，不能解释为该检查可挽救的损失或因果效应。','',
        '|场景|verify数|最大C|平均C|PoA w=0|PoA w=1|绝对改善|',
        '|---|---:|---:|---:|---:|---:|---:|']
    for s in summaries:
        lines.append(f"|{s['scenario']}:{s['seed']}|{s['verify_nodes']}|{s['max_concentration']:.6f}|{s['mean_concentration']:.6f}|{s['poa_w0']:.6f}|{s['poa_w1']:.6f}|{s['poa_improvement']:.6f}|")
    lines+=['',f'PoA直接读取`{source}`，固定black_box背景，采用第二轮较差已收敛起点汇总口径。',
        '四图最大C均为1：全部损失都在必经检查之后，所以“存在高集中度瓶颈”无法区分信用证的明显改善与随机图的零改善。',
        '信用证平均值较低主要因为低到达率的重提交副本，不能把副本数量效应误认作机制解释。',
        'n=4仅为探索性观察，无统计检验；本对比没有为“高下游集中度可预测遗漏责任有效”提供区分性支持，也没有否定它。',
        '后续需要包含绕过审查的分支、审查前/其他支路损失的场景，并分开控制检出/修复能力、检查成本和责任份额，检验可预防损失和激励阈值；本轮不生成。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return summaries


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('results/sweep_v2_omission_final/summary.csv'))
    parser.add_argument('--out',type=Path,default=Path('results/structure_v3'))
    args=parser.parse_args()
    for row in analyze(args.source,args.out): print(row)


if __name__=='__main__': main()
