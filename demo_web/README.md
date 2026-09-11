# MAST Protocol Replay Demo

这是 final benchmark 的确定性可视化重放，不是实时系统、实时模型调用或产品 Dashboard。

页面视觉参考答辩用单树流程图设计；运行时不依赖外部图片或网络资源。

## 真实 fixture 与结果

固定使用 `final-v1:long_chain_fork:confirmed_repair:business-1`，它来自 `results/final_unified_live_v1_combined_20260911/plan.json`。

- L0 对应 final workflow `w0130`：A_a、A_b 在错误事实基础上完成（2 unsafe completions）；C_a、C_b 正确完成。
- L4 对应 final workflow `w0134`：A_a、A_b 初次 action gate 被阻断，随后都经 authority-confirmed source revision、三项 descendant rebuild 和 fresh action check 恢复完成；C_a、C_b 保持完成。该 workflow 没有 budget stop。
- 受影响任务是 A_a、A_b；无关任务是 C_a、C_b。A 与 C 经过相同组织拓扑，但属于不同 claim dependency chains，因此视觉上将节点内两条 dependency lane 分开表达。

## 数据来源与展示层映射

`export_replay.py` 只读以下数据：

- final `plan.json`：fixture、拓扑、claim parents、任务、金额、affected / unrelated 集合；
- final `aggregate.json` 和 `task_metrics.json`：L0/L4 workflow 选择与最终任务结果；
- aggregate 所指向并通过 SHA-256 校验的 `w0130/result.json` 与 `w0134/result.json`：routes、recipient-bound handoffs、receipts、各组织 gateway events、dispute transport、source revision、rebuild records、fresh final action。

页面只显示一棵横向业务树。顶部 **对照组 · L0** 与 **MAST · L4** 是两套可独立切换、独立播放的演示，不会在一次 Auto Replay 中混播。L0 时间线固定为正常传播 / 错误传播 / 全部冻结；L4 时间线固定为正常传播 / 发现错误 / 局部阻断 / 修订重建 / 重新检查。底层 replay 和结果映射仍来自同一组数据：

- 正常传播同时呈现 claim、Handoff 与 Receipt；它们来自 `raw.routes` 及 signed `dependency_handoff` / `handoff_receipt`；
- Fault 来自 buyer 签名的 `CONTRADICTED` fact evidence 和各组织的 `fact_dispute_registered`；
- Contain 来自 L4 `REQUEST_EVIDENCE` outcomes、完整 dependency verification 与零 post-fault error handoffs；
- Repair 来自 `source_revision.status=confirmed_offer`、superseding source claim 和 buyer `CONFIRMED` reply；
- Rebuild 来自每项 recovery 的三个 `frontier_claim_rebuilt` records；旧 claims 不会被重新着绿；
- Recheck 来自 recovery `final_action=COMPLETED`、`authority_confirmation=CONFIRMED` 和 task-level `recovered=true`。

这些 stage 名称只组织动画节奏，不声称 runtime 原生提供了单一全局 event stream。Local View 仅汇总该组织导出的真实 gateway events，并明确不展示其他组织的完整私有账本。

## 生成与启动

```bash
./demo_web/run_demo.sh
```

默认地址是 `http://localhost:8765/?presentation=1`。也可以先生成数据再启动：

```bash
python3 demo_web/export_replay.py
cd demo_web && python3 -m http.server 8765 --bind 127.0.0.1
```

先点击顶部选择 L0 或 L4，再点击 **Auto Replay**。Auto Replay 只播放当前模式：L0 约 15.5 秒，L4 约 19.5 秒。页面支持 Pause、Step、Reset，也可点击底部任一步直接跳转；键盘 Enter / Space 同样可用。Presentation Mode 使用 `?presentation=1`；Chrome / Edge 按 F11 全屏，建议 1920×1080、浏览器缩放 100%。页面与数据完全本地运行，不需要网络、登录、数据库或 API key。

## 已知限制

动画压缩了 benchmark 的虚拟 tick 和多次 action opportunity，不按 wall-clock 比例绘制。横向树是用于答辩的简化投影：界面中的 `claim B` 对应真实 fixture 的无关 `Order C`，真实任务仍显示为 C_a / C_b。L0 第三步“全部冻结”是为了讲清“无法精准定位时会误伤无关支路”的演示层对照，并非 final benchmark 中 L0 的逐事件重放；final result 里 C_a / C_b 实际正常完成。页面继续保留 fixture、金额、拓扑与 L4 修复来源，但演示动作不应被当作协议实现的原生 event stream。buyer 是事实 authority 与 invoice authorization owner，不作为主传播节点。页面不声称签名能证明事实为真；签名只证明 issuer 与内容完整性。
