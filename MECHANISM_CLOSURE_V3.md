# 完整依赖状态查证与中间声明恢复 v3

日期：2026-09-09。本文描述新增机制与研究边界；不是新的 MiniMax 实验报告。

## 研究问题与可证伪主张

本阶段验证：某发行者发现问题并撤回声明后，在通知尚未送达的多跳网络里，能否阻止错误继续被引用、转发和执行；能否只修复受影响分支；能否用本地签名证据证明通知后的违规使用。

根声明全部 active 并不意味着派生声明仍有效。中间发行者可以独立撤回自己签署的声明。只查根的策略缺少这项信息。这是新增查证范围的理由，不能将“查得更全面”本身包装成算法创新。

候选贡献是运行时闭环：完整依赖确定查证义务，负面证据沿具体依赖局部冻结，原发行者修订及受约束后代重建，显式动作再次检查，签名本地事件链约束事后结论。尚待正式配对实验确认增量及代价。

## 行动控制与负面证据

`ReliabilityConfig.policy` 新增：

- `dependency_closure`：沿动作声明的完整祖先图，向每条声明的实际发行者查证；是否必须查证沿用本地 loss/threshold 配置。invoice 始终要求完整查证。
- `verify_all_closure`：同样覆盖完整依赖，所有 forward 与 invoice 都要求查证。

保留 autonomous、dependency、verify_all 的根查证语义。签名 plan 中新策略增加 `verification_targets` 和 `verification_scope=issuer_dependency_closure_v1`；`roots` 仍是真正的根。为兼容旧传输，query 的 `root` 字段在 closure 策略里表示“本次被查证的声明 ID”，可能是派生声明，不表示根身份。

共享目标在一个本地批次内合并；跨组织不共享未经绑定的行动许可。查询带 batch、challenge、proposal 绑定，原发行者回复自己的本地状态。未知、无法访问、缺失父证据和预算不足均不能授权必须验证的动作。风险权重只是 operational approximation，不等价于概率、数学 omission settlement 或法律责任。

直接撤销附原发行者签名 revoke。发行者因祖先撤销而报告自身声明失效时，附 `dependency_revocations`：接收方验证它们属于本次查询的真实祖先，批量验完才写入。接收方只保存真正被撤销的声明，不把依赖后代或暂时不可用永久标成撤销。后续批次仍能局部阻断。

显式执行语义继续生效：`intent=verify` 成功只能返回 VERIFIED；必须再有 execute 提议。强制验证也不改变这一点。每个输出新增 `local_head`，绑定本地 `reliability_outcome` 签名事件。它证明报告与本地记录的关系，不证明物理效果。

## 中间声明恢复：复用 frontier，新增 v3

新增 `recovery_closure.py`；现有 `recovery_frontier.py` 按 envelope 的版本复用拓扑调度、原发行者签署、父证据登记与派生规则验证。v1/v2 继续可用。

流程：

1. 原发行者对自己已直接撤销的 root 或 derived claim 提出修订。派生种子保持原父列表和规则，新 fact 必须合法，父证据必须本地可用；父证据出错时应先修复父证据。
2. `claim_revision_offer` 绑定 old、新签名 claim 和原撤销包。新 claim 的 `supersedes` 产生明确的新身份；即使数值相同，也不能复活旧 ID。
3. 接收方用失败的签名 batch 生成 `recovery-frontier-v3` envelope。只接受 REQUEST_EVIDENCE / ESCALATE / BLOCKED 的任务；COMPLETED 与 EFFECT_UNKNOWN 不重试。
4. envelope 绑定原 batch、精确 proposal、替换种子和受影响后代图。验证者从公开 batch、旧声明与 offers 重新计算任务，拒绝漏节点、无关任务和替换范围扩张。多个种子不得互为祖先；先修复上游再处理后代。
5. frontier 只开放父替换已完成的节点，由原发行者在本地收到合法新父后重建。后代新 claim 同时绑定 `supersedes`、envelope digest 和 task_id，不能用另一任务的完成包顶替。
6. 全部必要后代完成后返回 `replacement_map`，调用者显式提议新动作，再进入相同的查证与业务合约。修复证据传输和业务转发分开记录。

恢复不是自动纠正事实。调用者/Agent 必须明确提出修订 fact；这里的确定性 fixture 由受控发行者重新确认声明，用于验证失效后的协议恢复，不伪装成 LLM 自己发现并修好未知事实。

worker 接口：

| operation | 输入 | 输出 |
|---|---|---|
| reliability_claim_revision | old, fact | 签名 offer、events |
| reliability_closure_recovery | batch, offers | v3 recovery envelope、events |
| reliability_frontier | envelope, task_id, completed | ready、remaining、replacement_map |
| reliability_frontier_rebuild | 上述字段 + old, fact | 新 claim、proof、event |

worker 配置增加可选 `recovery_receivers: [receiver_a, receiver_b]`，兼容单个 `recovery_receiver`。共享发行者依据本地 allowlist 校验信封签署者，不能由请求者授予自己的信任身份。上述接口已通过持久化 worker 路径的无 provider 测试。

## 追溯边界

benchmark 审计输出完整 `claim_issuers` 和 `dependency_edges`，通知检查包含中间声明。benchmark use receipt 与真实 batch outcome 均绑定本地日志 head。共享 `evidence_order.py` 验证同一组织、同一 workflow 的签名 predecessor 链；本组织通知在该链上先于所报告动作，才判定通知后使用。

真实多轮审计也使用签名 batch 中的提议和结果，不能由 unsigned 展示字段或另一个消费者的通知推导违约。历史报告没有 local_head 时仍可读取，但仅凭 controller 顺序不再证明通知先于动作；历史产物不重写。

没有收到通知、链缺失或缺少动作绑定时保持无已证实违约；签署者身份不等于错误事实责任。来源事实真伪、恶意、实际损失和法律责任均不在当前证明范围。

## 当前验收与待证明事项

针对性测试覆盖中间撤销导致的双分支拦截与恢复、单分支局部恢复、真实 worker、祖先负面证明、跨任务/跨发行者/错误 scope/非法派生拒绝、缺失父证据、不可重试结果，以及有/无本地顺序证明的追溯。

`closure_v3` 是新离线入口，不自动更改旧 benchmark/live 矩阵。完整正式运行与结果解释交给实验代理，见 [实验任务书](TASK_EXPERIMENTS_CLOSURE_V3.md)。本轮没有新增付费模型调用。

重要限制：查询时确认不与远端撤销或外部效果原子化；网关可强制其自身适配器路径，不能阻止绕过网关的任意外部行为。未加入租约、全网广播、物理回滚或完整恶意组织模型。
