"""Standalone evidence viewer for the real two-hop propagation experiment."""
import json
from pathlib import Path
import sys
from trust_network.demo.audit_claim_propagation import audit


def render(root):
    checked=audit(root)
    report=json.loads((root/'report.json').read_text())
    trace=json.loads((root/'trace.json').read_text())
    data=json.dumps({'audit':checked,'report':report,'trace':trace},ensure_ascii=False).replace('<','\\u003c')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>跨组织 Agent：传播阻断与责任证据</title>
<style>body{font:16px/1.65 system-ui,sans-serif;max-width:1050px;margin:40px auto;padding:0 20px;color:#172b38;background:#f6f8fa}h1{font-size:28px}button{padding:10px 16px;margin:4px;border:1px solid #9aaebc;border-radius:6px;background:white;cursor:pointer}button:focus,button:hover{background:#dcecf5}article,section{background:white;border:1px solid #d9e1e6;border-radius:10px;padding:20px;margin:16px 0}.muted{color:#536672}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:350px;overflow:auto}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd}.bad{color:#a62727}.good{color:#17613b}li{margin-bottom:8px}</style>
<h1>错误授权如何停止传播，事后又能证明什么？</h1>
<p>权威组织 → 采购协调 Agent → 独立仓储 Agent。两位 Agent 使用真实 MiniMax 形成交接建议，网关约束结构化授权声明的转述与使用。</p>
<section><strong>同一声明链上的受控对照</strong><table><thead><tr><th>仓储面对的情况</th><th>旧授权执行</th></tr></thead><tbody id="comparison"></tbody></table><p id="usage" class="muted"></p></section>
<p>选择查看责任证据：</p><nav><button data-mode="all">全部使用事件</button><button data-mode="before">通知尚未送达</button><button data-mode="active">主动向权威确认</button><button data-mode="after">已收到撤销</button></nav>
<div id="uses"></div>
<section><h2>结论边界</h2><ul><li>主动查询阻止了“权威已撤销、通知尚未送达”的旧授权使用；无关订单仍可执行。</li><li>接收记录证明本地已知顺序。没有接收记录不能证明通过其他渠道也不知情，更不能直接判定失职。</li><li>签名证明声明和门禁记录，不证明物理发货已发生；外部动作需独立执行凭证。</li><li>这是本机独立进程、受控撤销时序和模拟动作。查询后到执行前的状态变化窗口仍存在。</li><li>当前只支持精确转述的结构化事实，不代表任意自然语言推理已被验证。</li></ul></section>
<section><h2>原始证据</h2><p><a href="trace.json">完整轨迹</a> · <a href="responsibility_audit.json">责任证据重建</a> · <a href="report.md">实验报告</a></p><details><summary>查看模型交接决策</summary><pre id="agents"></pre></details></section>
<script type="application/json" id="data">DATA</script><script>
const data=JSON.parse(document.getElementById('data').textContent),r=data.report;
const rows=[['仅等通知：尚未收到撤销',r.before_notice_executed],['主动确认：尚未收到撤销',r.checked_before_notice_executed],['已收到撤销',r.after_notice_executed],['主动确认无关订单',r.checked_unaffected_executed]];
for(const [label,executed] of rows){let tr=document.createElement('tr');for(const text of [label,executed?'执行':'阻断']){let td=document.createElement('td');td.textContent=text;tr.append(td)}document.getElementById('comparison').append(tr)}
document.getElementById('usage').textContent=`${r.model_calls} 次真实模型调用，${r.tokens} token。界面重放历史证据，不触发外部动作。`;
document.getElementById('agents').textContent=JSON.stringify(data.trace.filter(e=>e.response.draft).map(e=>({organization:e.owner,decision:e.response.draft})),null,2);
const labels={no_prior_local_revocation_receipt:'没有在先的本地撤销接收凭证',blocked_after_authority_check:'主动查询确认撤销后阻断',blocked_after_notice:'收到撤销通知后阻断'};
function show(mode){const target=document.getElementById('uses');target.replaceChildren();for(const u of data.audit.uses){if(mode==='active'&&u.classification!=='blocked_after_authority_check')continue;if(mode==='after'&&u.classification!=='blocked_after_notice')continue;if(mode==='before'&&u.classification!=='no_prior_local_revocation_receipt')continue;let a=document.createElement('article'),h=document.createElement('strong'),p=document.createElement('p'),d=document.createElement('details'),s=document.createElement('summary'),pre=document.createElement('pre');h.textContent=`${u.organization} · 本地事件 ${u.local_sequence}`;p.textContent=labels[u.classification]||u.classification;s.textContent='展开声明摘要及签名接收证据';pre.textContent=JSON.stringify(u,null,2);d.append(s,pre);a.append(h,p,d);target.append(a)}}
document.querySelectorAll('button').forEach(b=>b.onclick=()=>show(b.dataset.mode));show('all');
</script></html>'''.replace('DATA',data)
    (root/'demo.html').write_text(html)
    return {'artifact':str(root/'demo.html'),'use_events':len(checked['uses'])}


if __name__=='__main__':print(json.dumps(render(Path(sys.argv[1]))))
