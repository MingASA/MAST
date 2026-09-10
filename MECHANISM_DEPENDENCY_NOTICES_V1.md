# 沿交接依赖主动通知与恢复失效前沿

2026-09-09。基于 closure v3 的新增机制；不改变旧 live / offline 矩阵，不包含付费实验结果。

## 本轮解决的问题

closure v3 能主动查证中间声明，但一个组织查出撤销后，其他组织仍可能等到自己的下一次查证才知道。新增机制把**具体交接对应的依赖集合**登记为本地通知路径，沿这条路径传播原始撤销证明。另一个缺口是已重建的证据可能再次失效：签名仍然有效，恢复前沿却不应继续把它视为可用的完成成果。

这两项设计不依赖新的实验估计即可实现、检查其安全边界；是否比单纯查证带来足够增量，要在固定消息时序和相同模型提议下验证。

## 1. 依赖登记 → 局部反向索引 → 有签收的主动通知

### 交接协议

`guarded_handoff(call, sender, recipient, claims, proposal_id)` 接受现有 `WorkflowController.call` 接口，执行：

1. sender 的 `reliability_handoff_prepare` 将 forward 提议交给现有 Reliability Policy。只有通过后才创建签名 `dependency_handoff`。
2. packet 绑定 workflow、recipient、targets 和恰好覆盖其完整依赖的签名声明包。sender **在返回可发送 packet 之前**登记路径。
3. recipient 的 `reliability_handoff_accept` 验签、核对收件人、验证完整依赖与派生规则，再按自己的撤销状态登记。返回签名 `handoff_receipt`，区分 accepted 与 blocked。
4. sender 的 `reliability_handoff_ack` 验证并保存签收。未收到 ACK 的交接仍保留通知路径，不能因 ACK 丢失而漏通知。

返回状态区分 PREPARATION_BLOCKED、PREPARATION_UNKNOWN、DELIVERY_UNKNOWN、ACK_PENDING、RECEIVED、RECEIVED_BLOCKED。准备阶段 batch 的 COMPLETED 仅指本地适配器创建了交接包，不代表远端已收到。所有结果均不授权接收方执行业务动作。

`prepare_handoff()` 是底层本地登记函数，只验证本地依赖。真实 workflow 应使用上述 policy-gated worker / guarded_handoff，不应绕过查证策略直接把底层函数当作完整门禁。

### 局部路由算法

每个 gateway 保存自己的反向索引：

```
claim_id → outgoing_handoff_ids → direct_recipient
```

每个 handoff 登记完整依赖闭包。因此根或中间声明被撤销时，只需访问该 target 的索引项，并按收件组织合并；无须知道全局图或读取其他组织的内部状态。查询相关索引的工作量随本地受影响交接数增长，不随全网组织数增长；签名消息生成仍有携带证明的大小成本。

`ClaimGateway.receive(revoke)` 自动调用调度逻辑，生成 `dependency_notice` 到本地 outbox。消息包含原发行者签名 revoke，以及与该 target 有关的已签名 handoff。转发者只是传递证据，不能代替原发行者撤销声明。

收件人验证所有 handoff 的签署者、收件人、闭包和 target 关系，验证原发行者的撤销证明，然后原子地登记撤销和 receipt。登记过程触发其自己的下游通知队列。即使 notice 比原 handoff 先到，也可以保存原始撤销；后来旧包到达时只能登记为 blocked。

同一撤销、相关交接集和收件人产生确定性 packet ID。重复 notice 返回原 receipt，不反复记录或放大传播；交接环路也不会无限重新排队。同一不可变依赖包的重复交接共用路径和首次登记 receipt，不把它们伪装成多个新的模型阅读事件。

### 投递和状态持久化

`pump_notifications(call, owners, max_deliveries=32)` 通过 worker 导出的 pending 队列投递并回传签收。它不读取组织状态文件。一次调用对同一 pending packet 最多尝试一次；失败保留队列，下一次调用再重试。级联通知消耗同一个 delivery budget。未知端点、接收失败、ACK 丢失均不会被改写为已确认送达。

worker state 增加 outgoing handoffs、反向索引、incoming receipts、outbox 与 ACK。兼容没有这些字段的旧状态。事务分支同时复制全部协议状态，避免多证据校验失败时提前泄漏通知。worker 用临时文件、fsync 和原子替换保存状态，并在返回 packet/receipt 前完成本地提交；仍然是单组织串行 worker，不是并发数据库或分布式事务。

worker 统一导出本次操作产生的全部签名 gateway events，包括级联 notification_queued，避免追溯时人为缺失 predecessor 链。

### 接口

| operation | 主要输入 | 主要输出 |
|---|---|---|
| reliability_handoff_prepare | id, recipient, claims | 通过本地 policy 的 batch；成功 result.handoff |
| reliability_handoff_accept | packet | result: handoff_receipt |
| reliability_handoff_ack | packet: receipt | result.registered |
| reliability_notifications | 无 | pending packets、审计视图 |
| reliability_notification_accept | packet: notice | result: notification_receipt |
| reliability_notification_ack | packet: receipt | result.acknowledged |

这些新增操作已接入持久化 worker，旧的原始 receive 操作不自动构造交接路径。实验必须显式采用相同交接协议后，比较启用/停用通知投递，不能拿路径登记差异混充查证策略收益。

## 2. 恢复前沿面对二次失效

v3 frontier 完成原有签名、任务和派生合法性验证后，再基于**当前本地**撤销状态检查 replacement seeds 与 completed packets 的依赖：

- `usable_completed`：仍可复用的重建成果；
- `invalidated_replacements`：已验证签名但已知失效的替换及其 blocker；
- `suspended`：受这些失效影响、不能继续重建的节点；
- `requires_replan`：需要新修订/恢复任务；
- `recovery_complete`：必要重建全部完成，且替换证据没有已知失效。

`replacement_map` 排除失效替换。未受影响的已完成分支保留，其他仍可用的 ready 节点可以继续。不能在同一信封里重复签出同一个已撤销的新 ID，假装修复完成。`remaining` 包含未完成节点和失效替换义务，不再能单独被解释为“缺几个新签名”。

只有通过原发行者对新撤销声明的修订及新恢复信封，才能建立下一轮替换。frontier 没有发现远端未送达撤销的超能力；最终动作仍要按 policy 查证。

## 3. 追溯与可以支持的结论

`audit_notification_exchange(notice, receipt, public, authorities)` 只用交换的签名包独立验证通知与签收，输出 registration_proven。`notification_audit` 将 outbox 记录为 unacknowledged 或 signed_receipt。

- outbox 证明本地已登记待发信息，不证明网络送达；
- receipt 证明接收方签署了登记声明，不证明 Agent 已阅读、更不证明事实正确；
- 无 ACK 可能是消息、ACK、节点或传输异常，当前没有可信 deadline / 完整日志假设，不据此判定 omission 失职；
- receipt 的本地 revocation event 可与后续动作的 signed local_head 组成现有通知后使用的追溯证据。

## 4. 验收与研究价值边界

当前全量测试 169 passed；最后补齐全部事件导出后，11项相关测试通过。新测试覆盖双分支级联、无关声明继续、通知先到、重复/环路终止、丢失ACK重试、重启保存、非法通知事务回滚、实际worker交接，以及种子/完成证据二次撤销与保留无关成果。没有新增付费模型调用。

新增价值候选是**已经发现的负面证据更早到达相关消费者**，以及**恢复期间失效仅影响相应成果**。不声称仅靠通知能获得可靠消息传输：如果通知迟到、丢失或节点停机，必须保留动作前查证；也不声称受控网关能禁止组织绕过网关执行外部行为。

当前不实现通知租约、全局一致时钟、法律责任比例、外部动作回滚或恶意发行者事实检测。下阶段实验边界见 TASK_EXPERIMENTS_DEPENDENCY_NOTICES_V1.md。
