"""Standalone explorable artifact from recorded real runs, with no live API button."""
from pathlib import Path
import json


def render(root):
    records=json.loads((root/'records.json').read_text()); data=[]
    for r in records:
        folder=root/f"repeat_{r['repeat']}"/r['case']/r['protocol']
        steps=[]
        for event in json.loads((folder/'events.json').read_text()):
            if event['kind']!='response': continue
            response=event['response']; org=event['owner']
            if 'message' in response:
                content=response['message']['body']['content']
                title=content.get('action','offer')
                steps.append({'owner':org,'type':title,'content':content,
                    'explanation':response.get('draft',{}).get('explanation','')})
            elif 'commitment' in response:
                body=response['commitment']['body']
                steps.append({'owner':org,'type':body['status'],'content':{
                    'scope':body['scope'],'binding':body.get('binding_mode','dependency'),
                    'reasons':body['reasons'],'sequence':body['sequence']},'explanation':''})
            else:
                steps.append({'owner':org,'type':'local_repair','content':response.get('feedback'),
                              'explanation':'草稿未成为可执行的组织承诺'})
        data.append({'case':r['case'],'repeat':r['repeat'],'protocol':r['protocol'],
            'outcome':r['outcome'],'unsafe':r['unsafe_completion'],'feasible':r['final_feasible'],
            'queries':r['commitment_queries'],'tokens':r['tokens'],'steps':steps})
    summary=[]
    for protocol in ('autonomous','full','dependency'):
        group=[r for r in records if r['protocol']==protocol]
        summary.append({'protocol':protocol,'n':len(group),'unsafe':sum(bool(r['unsafe_completion']) for r in group),
            'safe':sum(r['outcome']=='completed' and r['final_feasible'] is True for r in group),
            'queries':sum(r['commitment_queries'] for r in group),'tokens':sum(r['tokens'] for r in group)})
    payload=json.dumps({'runs':data,'summary':summary},ensure_ascii=False).replace('<','\\u003c')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>真实 Agent 协作：证据与执行轨迹</title><style>
body{font:16px/1.6 system-ui;margin:24px auto;padding:0 20px;max-width:1200px;color:#172436;background:#f5f7fa}
h1{font-size:27px}table{border-collapse:collapse;background:white;width:100%}th,td{padding:10px;border-bottom:1px solid #dde3eb;text-align:left}
.layout{display:grid;grid-template-columns:260px 1fr;gap:20px;margin-top:24px}button{display:block;width:100%;text-align:left;padding:10px;margin:5px 0;background:white;border:1px solid #ccd4df;cursor:pointer;border-radius:6px}button:hover,button.selected{border-color:#1565c0;background:#eaf2ff}
article{background:white;padding:14px 18px;border-left:4px solid #5985ad;margin:12px 0;border-radius:4px}.denied{border-color:#b72626}.approved{border-color:#278047}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}.note{color:#465568}.bad{color:#b72626;font-weight:bold}.ok{color:#237542;font-weight:bold}@media(max-width:700px){.layout{grid-template-columns:1fr}}
</style><h1>真实 Agent 协作：证据与执行轨迹</h1>
<p>27 个真实 MiniMax run · 自然模型输出 · 三个组织各有私有资源 · 本机组织进程 · 模拟发运</p>
<p class="note">这是小样本研究记录，不是现实零风险证明。保护组本批没有收到错误的执行提议；不同组的模型轨迹不同，不能把全部差异归因于协议。候选计划送审与实际提交分开显示。</p>
<table><thead><tr><th>协议</th><th>不安全提交 / run</th><th>安全完成 / 6 个已授权任务</th><th>确认查询</th><th>token</th></tr></thead><tbody id="summary"></tbody></table>
<div class="layout"><nav id="runs"></nav><main><h2 id="title"></h2><p id="result"></p><section id="steps"></section></main></div>
<p><a href="report.md">研究结论与限制</a> · <a href="analysis.json">机制诊断与责任证据索引</a> · <a href="records.json">逐 run 数据</a></p>
<script id="data" type="application/json">PAYLOAD</script><script>
const data=JSON.parse(document.querySelector('#data').textContent);
const names={autonomous:'Agent 自主执行',full:'整计划证据',dependency:'依赖范围证据',supplier:'供应商',carrier:'物流商',buyer:'买方'};
const types={offer:'提供资源选项',propose:'请求执行候选计划',verify:'主动请求确认',reject:'拒绝方案',approved:'确认当前范围',denied:'拒绝当前范围',local_repair:'本组织修正草稿'};
for(const s of data.summary){const tr=document.createElement('tr');for(const v of [names[s.protocol],`${s.unsafe} / ${s.n}`,`${s.safe} / 6`,s.queries,s.tokens.toLocaleString()]){const td=document.createElement('td');td.textContent=v;tr.append(td)}document.querySelector('#summary').append(tr)}
function select(i){const r=data.runs[i];document.querySelectorAll('nav button').forEach((b,j)=>b.classList.toggle('selected',i===j));document.querySelector('#title').textContent=`${r.case} · 第 ${r.repeat+1} 次 · ${names[r.protocol]}`;const result=document.querySelector('#result');result.textContent=`${r.outcome}；确认 ${r.queries} 次；${r.tokens} token。`+(r.unsafe?'发生违反业务约束的提交。':r.feasible?'提交的计划满足事后检查的硬条件。':'未执行提交。');result.className=r.unsafe?'bad':'ok';const steps=document.querySelector('#steps');steps.replaceChildren();for(const s of r.steps){const a=document.createElement('article');a.className=s.type;const h=document.createElement('strong');h.textContent=`${names[s.owner]}：${types[s.type]||s.type}`;a.append(h);const pre=document.createElement('pre');pre.textContent=JSON.stringify(s.content,null,2);a.append(pre);if(s.explanation){const p=document.createElement('p');p.textContent='Agent 草稿解释：'+s.explanation;a.append(p)}steps.append(a)}}
data.runs.forEach((r,i)=>{const b=document.createElement('button');b.textContent=`${r.unsafe?'⚠ ':''}${r.case} / ${r.repeat+1} / ${names[r.protocol]}`;b.onclick=()=>select(i);document.querySelector('#runs').append(b)});select(Math.max(0,data.runs.findIndex(r=>r.unsafe)));
</script></html>'''.replace('PAYLOAD',payload)
    (root/'demo.html').write_text(html)
    return len(data)


if __name__=='__main__':
    print(render(Path('results/negotiation_v6_protocol_comparison')))
