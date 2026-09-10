# 跨组织工作流 benchmark v1

模式：live；后端：process；决定来源：live。共3条workflow，每条4项业务任务。
签名和私有事实正确性分别评估。跨任务恢复绑定失败另列，不伪装成已发生金额错误。

|条件|机制|错误完成/4|业务安全完成/4|恢复成功|错误接收组织|无关误冻|查证|跨任务绑定完成|
|---|---|---:|---:|---:|---:|---:|---:|---:|
|intermediate_retraction|root_gate|0|0|0|0|2|6|0|
|intermediate_retraction|dependency|0|0|0|0|2|6|0|
|intermediate_retraction|dependency_push|0|0|0|0|2|6|0|

## 本次 pilot 的有效性判定

三条 workflow 的 `truth.json` 都是 `faults=[]`，并在 tick 10 记录了 `fault_not_realized`。模型没有产出并由 coordinator 真实 worker 登记的中间 claim，旧调度路径使用 fixture fallback 构造撤销目标，worker 因本地不存在该 claim 而拒绝撤销。因此“错误完成 0/4、错误接收组织 0、恢复 0”不能解释为三种机制的 containment 结果，三臂之间没有可解释的机制差异。

本次 pilot 仍验证了真实模型调用、独立 process worker、签名交接、审计和原始归档接口：每臂 18 次模型调用，合计 54 次，已知 token 103,570，provider failure 0。模型 hold 分别为 14、15、16 次，且出现了派生 fact 不符合 `relay` 精确复制规则的输出。完整失败分析和后续接线修复见 [POSTMORTEM.md](POSTMORTEM.md)。

## 必须保留的解释边界

- simple_dependency_gate / dependency / verify_all 在默认配置下有相同检查覆盖，是等价校准，不应虚构机制差异。
- dependency_push 的通知按虚拟时钟投递；late_notice 不保证在动作前到达。
- scripted决定不是LLM能力结果；fixed_tape缺失阶段会hold，不补造批准。live样本单独归档。
- 来源身份匹配不等于事实责任；无本地签名顺序证明，不指控通知后违规使用。
- 冲突与签名事实错误可能被所有当前策略漏过；这是检测边界，不删除失败案例。
