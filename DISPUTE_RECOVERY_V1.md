# 争议传播与独立确认恢复 v1

已实现两项核心机制，随后补齐了真实模型 live adapter。机制基线为 **195 项测试**；加入 3 项无付费 adapter 边界测试后，当前全量为 **198 项通过**。

## 本轮落地结果

[内存离线闭环](results/dispute_lifecycle_v1_offline/report.md)与[实际进程闭环](results/dispute_lifecycle_v1_process/report.md)一致：

- 错误证据已经经过三跳、进入两条分支后，协调组织取得权威 CONTRADICTED 答复；此时来源尚未撤销声明。
- 复用既有交接反向索引，将该签名争议送达两个 middle 和两个 receiver，共4次投递、4份签收，无发送失败。
- 两个 A 动作均 REQUEST_EVIDENCE；两个无关 C 动作均 COMPLETED。
- 来源主动提出新事实125分，独立权威确认后，来源签署自己的真实撤销与替代声明。两分支按 closure v3 重建，最终两个 A 动作均 COMPLETED。

这是脚本明确提议、真实程序执行的机制验证，不是模型自发完成修订的实验，也不是与其他策略的统计性能比较。来源提出125分由脚本预先给定，协议没有从“否认100分”自行推断出125分。

## 传播与局部冻结

新模块 `dispute_protocol.py` 定义 dependency-dispute-v1，复用原 notification_outbox、receipt、ACK、pump、handoff_index。消息携带原权威签名答复，以及发送方签署的相关历史交接包。接收端检查：

- 本地独立配置的 scope→authority 信任映射，不相信发送者自称的权威；
- 原请求签名、请求者、工作流、具体声明、命题scope、nonce和答复绑定；
- 确为 CONTRADICTED，且声明属于所附的交接依赖闭包；
- 收件组织、发送方、交接包及重复包绑定。

接收端持久登记事实争议，然后仅向本地已登记的相关直接下游继续通知。重复通知返回同一签收；丢ACK保留pending，沿用有界pump的重试语义。签收证明本地登记，不证明模型理解、更不自动证明失职。

`ClaimGateway.blockers` 现在识别 `disputed:<claim_id>`，并沿父依赖传播阻断；因此即使某组织没有开启主动事实查证，已接收的有效争议也不能被普通转交/业务执行绕过。状态查询遇到争议返回 unknown，不伪装成发行者 revoke。无关 C 不受影响。

旧 claim 的有效历史否认证据在证书到期后不会自动消失；负面证据到期不等于事实已经恢复正确。此保守规则可能降低可用性，解除路径是新声明和受证据约束的恢复，而不是等待过期后再用旧声明。

## 谁能修订、怎样恢复

worker 新增 `reliability_dispute_register` 和 `reliability_dispute_revision`。前者只登记证据，不撤销声明；后者要求原发行者明确提交 proof 和新 fact。

修订接口在暂存网关中构造同业务范围、同父依赖、supersedes旧ID的候选，先验证结构，再请求独立权威确认这个精确新claim。确认请求绑定签名 revision_intent、新claim摘要与随机challenge。只有 CONFIRMED 才提交来源本地的真实撤销、替代声明和带 fact_resolution 的 offer；失败不会留下本地部分撤销。权威可能留有查询审计记录，但候选不因此被来源正式采用。

随后复用 `prepare_closure_recovery → frontier → rebuild_frontier_claim`：

- 失败batch的争议快照纳入公开证据，即便原接收方没有启用fact_policy也不能丢失恢复约束；
- 本地或失败batch已证明存在争议时，没有独立确认的普通revision offer被拒绝；
- 原发行者身份、原声明、完整新声明、scope和确认答复都要绑定；删除fact_resolution、改nonce、跨范围都不能通过；
- 后代仍由各自原发行者按受信任接收者的精确任务逐层重建；
- 旧争议和撤销保留，新图使用新ID；恢复本身不批准业务动作。最终仍需新的明确execute，并重新做freshness与事实确认。

接收者不会被赋予代替来源修改事实的权力。中间relay事实若因父声明错误而需要变更，应先从原事实源修订，再重建后代；不能直接改掉中间金额、留下不支持它的父证据。

## 审计与信任配置

配置同时提供独立信任映射和查证策略，例如：

```json
{
  "fact_authorities":{"settlement_basis_v1":"buyer"},
  "fact_policy":{"policy":"selective","authority":"buyer","forward_loss":1,"query_cost":1,"threshold":2}
}
```

fact_authorities 是本地配置，不从远程claim/消息推断。复用的通知接口按消息kind分派到争议验证，不把争议包交给revoke验证器。`audit_exchange` 独立验证争议路径与签收；批次审计验证签名争议快照和事实门禁；恢复验证继续依赖独立配置的权威与接收者。

原始RPC日志、签名包、结果和文件摘要分别归档。文件hash证明保存内容一致，不证明外部物理业务发生；没有消息期限、完整日志承诺或注意力证明时，不推断通知遗漏责任或法律责任。

## 复现

```bash
.venv/bin/python -m trust_network.benchmark.dispute_lifecycle --out results/dispute_lifecycle_reproduction
.venv/bin/python -m trust_network.benchmark.dispute_lifecycle --backend process --out results/dispute_lifecycle_process_reproduction
```

入口为离线脚本专用，没有付费模型开关。process版使用真正的持久化claim_worker及跨组织查询路由；并非多物理主机、行政域安全沙箱或真实付款系统。

## 下一步：冻结机制，转入 benchmark 和定向自然负向场景

按 [实验交接](TASK_EXPERIMENTS_DISPUTE_V1.md) 已补齐薄的 live 调度适配器，并完成五条小规模真实流程；完整结果见 [pilot 总结](results/dispute_live_pilot_v1_summary.md)。`v1_05` 已完成两条 A 分支的真实模型恢复闭环，`v1_02` 保留自然决策下 A hold/C 完成，负向适配器失败、provider timeout 和最终模型 hold 均未删除。独立权威自身出错、远端状态与 effect 竞态、经济责任分配仍未被本轮解决。
