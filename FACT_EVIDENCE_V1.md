> **后续已完成：** [争议传播与确认恢复](DISPUTE_RECOVERY_V1.md) 已接入。争议机制基线195项测试，加入 live adapter 边界测试后当前全量198项通过；下文“尚未实现”描述保留为前一阶段记录。

# 结算依据补证门禁 v1：已实现部分与实测边界

**全量192项测试通过；没有新增付费调用。**

当前已实现：签名补证服务、动作前强制事实门禁、持久化本地争议、公开证据审计、内存与真实进程离线运行。**尚未实现争议证据的跨组织主动广播、基于争议自动生成修订/恢复信封，以及新事实门禁的 live 实验。**旧撤销传播与 closure 恢复机制仍保留，不能把两者直接冒充新 dispute 闭环。

## 本轮新增结果

[16 条脚本矩阵](results/fact_basis_v1_offline/report.md)；[真实 process worker 核验](results/fact_basis_v1_process/report.md)。全部新增模型调用为 0，决定来源是 scripted，不是新的真实模型效果样本。

公开单据一致、但独立买方台账金额不一致时：

|策略|无依据完成/4|错误触达组织|事实补证次数|
|---|---:|---:|---:|
|只有完整依赖 freshness|2|5|0|
|只在公开冲突时补证|2|5|0|
|所有下游转交/最终动作补证|0|1|20|
|选择性：低风险转交略过，最终动作补证|0|5|12|

这验证了**未撤销的错误也能被程序拦截**，而且通过实际 worker 路径实现。全查从 coordinator 的转交开始拦截，因此 source → coordinator 已发生的首次接收仍计入污染；没有把源头服务上的阻断算作下游算法收益。

选择性策略省查询，但错误已到达所有五个下游组织，不能只用最终错误完成同为零宣称它与全查同样安全。正常条件下补证次数为 32 对 12，四项业务都完成。公开冲突时 conflict-triggered 只用 4 次补证就阻止 A，C 正常完成。权威 UNKNOWN 时强门禁保留 C、暂停 A；UNKNOWN 表示依据不足，不证明金额本身必然为假。

## 信息分布与真实性范围

沿用七组织三跳双分支业务。source 发布 total_charge，buyer 原有授权服务之外拥有独立 `settlement_registry`，表示正式结算依据，不能与付款额度混淆。台账只由 buyer 的 `private.json`/内存私有适配器读取；其他组织只收到 CONFIRMED、CONTRADICTED、UNKNOWN 的签名命题答复与记录版本，不收到台账或正确金额。

新增场景 `unconfirmed_settlement_basis` 明确区别于旧 generic signed_false：前者有预先约定的独立业务权威，后者的任意事实真实性尚未解决。权威正确性是本矩阵的假设；若台账错误、权威欺骗或串通，签名不会把它变成真相，本协议没有普遍真实性保证。

四种策略固定工作流、脚本提议、公开声明、权威台账与其他门禁，只有五个下游角色的 fact_policy 不同。source/buyer 仍是发布既有文件的固定服务。场景标签与 evaluator truth 不传给门禁。

## 运行时与审计

- `fact_evidence.py` 复用 Certificate 支撑的 claim_channel.issue/read，不另造签名系统。独立 scope 为 settlement_basis_v1，保留旧 authority.py 的正式型号批准接口及历史语义。
- 请求由 requester 签名，绑定 workflow、claim digest、完整声明、proposal digest、batch digest、nonce 和本地配置的 authority。权威返回绑定该请求、版本与有效期的签名答复；无跨动作 affirmative 缓存。
- `network_reliability.run_batch(..., fact_config=...)` 在 freshness 之后、effect 之前查询。失败/未知/否认均 REQUEST_EVIDENCE；只有完整通过后才继续原动作合约。verify 不隐式执行。
- `reliability_batch` 和 `reliability_handoff_prepare` 都接入，不能仅保护付款而让强制转交补证被绕开。ProcessBackend 沿原跨组织 query 通道请求 buyer，查询服务自己读取私有台账。
- 同键不同值的公开声明触发 conflict；签名否认将精确 claim 加入持久化 fact_disputes。本地索引不篡改原签名，也不伪造 issuer revoke。新查询 CONFIRMED 不自动解除旧争议；必须另行提交原发行者的新证据/恢复图。
- 当前相关派生链的检查会展开全部祖先；原 claim 的 dispute 因此不能靠简单转签绕过。无关 C 不进入该争议集合。模型 public view 展示签名争议证据。
- 批次保存 fact_config、查询/回复、判定时点、状态、选中声明和补证次数。独立审计重算选择与动作边界；调用方必须另外提供 `{settlement_basis_v1: buyer}` 的信任映射，不能只相信被审计报告自称谁是权威。

协议只提供串行 worker 内的动作前检查，不与远端台账或真实付款建立原子事务。证书签发后、effect 前权威状态变化的竞态仍存在。持久争议不能自动消失虽然保守，但可能降低恢复率；本轮不把这部分未完成任务包装成已完成的安全业务。

## 配置与复现

组织 config.json 添加：

```json
{"fact_policy":{"policy":"selective","authority":"buyer","forward_loss":1,"query_cost":1,"threshold":2}}
```

支持 closure_only、conflict_triggered、verify_all、selective。配置阈值用于转交调度，最终动作必查（仅 selective 与 verify_all）；显式 verify 和已登记争议在所有启用本接口的臂都必须查。分数是操作性启发式，不是已学习的错误概率或数学责任结算。

```bash
.venv/bin/python -m trust_network.benchmark.fact_basis --out results/fact_basis_reproduction
.venv/bin/python -m trust_network.benchmark.fact_basis --backend process \
  --cases unconfirmed_settlement_basis --policies verify_all \
  --out results/fact_basis_process_reproduction
```

入口只支持离线决定，不能误启动 MiniMax。输出路径必须不存在。完整原始 trace 可由 workflow.evaluate.audit 验证，fact 验证费用单独列在 fact_queries，不能与 freshness 查询混为同一指标。

## 下一步，不依赖新模型实验

1. 为 dispute 定义独立于 revoke 的签名传播消息，验证 scope 与权威、复用交接反向索引、收据和去重，避免不可信组织广播任意冻结。
2. 让原发行者基于已确认的修订提议签署替代证据；将 dispute 的旧新图接入受约束恢复。UNKNOWN 不触发自动编造金额，权威否认也不赋予下游改写原声明的权力。
3. 增加权威错误、不可用、回复重放与台账版本变化的离线边界。先测机制增量，再交接小规模 live；当前不要直接复用旧三臂 live 命令来宣称已经测了事实补证。
