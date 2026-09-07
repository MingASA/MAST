"""Generate honest comparison reports from all second-round sweep rows."""
from pathlib import Path
import csv
import json
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/wuxing-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path):
    with path.open() as stream: return list(csv.DictReader(stream))


def write_new(path,text):
    with path.open('x') as stream: stream.write(text)


def omission_report(root):
    rows=read(root/'summary.csv'); starts=read(root/'by_start.csv')
    trends=json.loads((root/'trends.json').read_text())
    lines=['# 优先级1：遗漏责任与检查次数','',
           f'共{len(starts)}个起点行、{len(rows)}个组合；144个起点均收敛。取已找到的较差均衡，不声称穷举最坏PoA。',
           '三个协议在本次参数下得到相同汇总结果。w_omit=0与旧Proportional的逐起点PoA/检查比及第一轮最差均衡PoA精确一致，详见zero_weight_regression.csv。旧检查比是本轮补算。',
           '全场景中PoA随权重弱单调不增，检查比弱单调不减，但并非严格单调：种子11没有实质改善，多个区间出现平台。144个起点的检查比最大为1，没有观察到超过社会成本最优解检查次数的过度验证。',
           '信用证w=1时PoA从2.638268降至1.006474，检查比从0升至1；这属于弥补检查不足，不能描述成已观察到“降低PoA但过度检查”的副作用。也不能推广为更大权重或其他预算下不会过度检查。',
           '', '|场景|seed|协议|目标|observed PoA|检查比|检查比起点范围|', '|---|---:|---|---|---:|---:|---|']
    for r in rows:
        lines.append(f"|{r['scenario']}|{r['seed']}|{r['protocol']}|{r['target']}|{float(r['observed_poa']):.8f}|{float(r['over_check_ratio']):.8f}|{r['check_ratio_min']}–{r['check_ratio_max']}|")
    write_new(root/'report.md','\n'.join(lines)+'\n')
    fig,axes=plt.subplots(2,4,figsize=(15,7))
    selected=[r for r in trends if r['protocol']=='black_box']
    for col,item in enumerate(selected):
        axes[0,col].plot(item['weights'],item['poa'],'o-'); axes[0,col].axhline(1,color='gray',ls='--')
        axes[0,col].set_title(f"{item['scenario']} ({item['seed']})")
        axes[1,col].plot(item['weights'],item['over_check_ratio'],'o-',color='darkorange')
        axes[1,col].axhline(1,color='gray',ls='--'); axes[1,col].set_xlabel('Omission weight')
        for ax in axes[:,col]: ax.grid(alpha=.2)
    axes[0,0].set_ylabel('Observed PoA'); axes[1,0].set_ylabel('Equilibrium / optimal checks')
    fig.suptitle('All weights and seeds; three protocols coincide in this sweep')
    fig.tight_layout(); fig.savefig(root/'omission_tradeoff.png',dpi=180); fig.savefig(root/'omission_tradeoff.svg'); plt.close(fig)


def roles_report(root):
    rows=read(root/'summary.csv'); starts=read(root/'by_start.csv')
    mismatches=json.loads((root/'mismatches.json').read_text())
    lines=['# 优先级2：逐节点角色消融','',
           '按展开后的每一个节点分别干预；两个银行节点各4个提交实例，共8处。共24个配置（包括8份相同baseline）、288个起点行。相同baseline只实际求解一次并复用，b/c独立求解。',
           '', '|节点|决策方|付费方|默认承担方|该节点L|','|---|---|---|---|---:|']
    for m in mismatches: lines.append(f"|{m['node']}|{m['decision_maker']}|{m['payer']}|{m['bearer']}|{m['loss']}|")
    lines+=['','所有节点的(a)/(b)/(c)最差已发现均衡PoA均约2.638268，检查比均为0，没有向随机图1.09–1.16靠拢。',
            '但这不意味着所有起点都不变：出口方银行k=0或k=1完全对齐时，selfish全检查起点收敛到更差结果，见下表。其余起点未出现超过1e-9的成本/检查比变化。',
            '关键结构限制：这些审单节点L=0，当前bearer只在loss节点结算时使用。因此(b)是收益函数上的无效干预，不足以识别“决策责任分离”的因果效应。(c)对出口方银行真正改变的是payer：从卖方补贴变为银行自己付费，可能减少验证。不能把没有改善归因于已证实的链条深度影响；链深度等仍未单独消融。',
            '', '|变化节点|协议|起点/目标|baseline PoA|完全对齐PoA|baseline检查比|完全对齐检查比|', '|---|---|---|---:|---:|---:|---:|']
    index={(r['ablation_node'],r['alignment'],r['protocol'],r['target'],r['start']):r for r in starts}
    changes=[]
    for r in starts:
        if r['alignment']=='baseline': continue
        b=index[r['ablation_node'],'baseline',r['protocol'],r['target'],r['start']]
        if abs(float(r['social_cost'])-float(b['social_cost']))>1e-9 or abs(float(r['over_check_ratio'])-float(b['over_check_ratio']))>1e-9:
            changes.append({'baseline':b,'variant':r})
            lines.append(f"|{r['ablation_node']}|{r['protocol']}|{r['start']}/{r['target']}|{float(b['observed_poa']):.8f}|{float(r['observed_poa']):.8f}|{float(b['over_check_ratio']):.8f}|{float(r['over_check_ratio']):.8f}|")
    lines+=['','以下完整表对每个节点、每个协议与目标给出(a)/(b)/(c)三行：','',
            '|节点|协议|目标|消融|observed PoA|检查比|','|---|---|---|---|---:|---:|']
    for r in sorted(rows,key=lambda r:(r['ablation_node'],r['protocol'],r['target'],r['alignment'])):
        lines.append(f"|{r['ablation_node']}|{r['protocol']}|{r['target']}|{r['alignment']}|{float(r['observed_poa']):.8f}|{float(r['over_check_ratio']):.8f}|")
    write_new(root/'report.md','\n'.join(lines)+'\n')
    write_new(root/'changed_starts.json',json.dumps(changes,indent=2))


if __name__=='__main__':
    omission_report(Path('results/sweep_v2_omission_final'))
    roles_report(Path('results/sweep_v2_roles'))
