# Pilot 01 后的机制接口修正与下一步

2026-09-09。审阅 checkpoint `0d88143`。本轮没有启动新的付费实验，旧 pilot 归档没有改写。

## 为什么不能直接重跑三臂

三条 live 工作流只有“调度结束”，没有完成任何业务任务。54 次调用、103570 token、零 provider failure 证明调用链可运行，但故障未发生，不能用零 unsafe/零传播证明防护有效。

检查原始 draft 发现比 fixture fallback 更早的断点：

- required_parent_claims 使用完整 packet 的 digest，public_claims 却没有显式以该 digest 建索引。模型把签名里的 bundle_hash 当成声明 ID，或声称所需 ID 不在证据中。
- 协调员曾明确 proceed，但为 A 输出 C 的描述，或把 total_charge 改为 signature_fee_basis，或把两个订单合并。relay 的精确相等检查正确拒绝了这些结果。
- 后续大量 hold 是缺失声明的连锁反应，不能当作独立模型失败，也不能当作算法控制错误的正例。

上一 checkpoint 已删除 live/fixed tape 的未登记 fixture fallback，并解释 relay 规则。这两项必要，但让模型继续重新输出确定性 JSON 仍有不必要的接口摩擦。因此本轮先补程序接口，没有直接重跑或切到新的事实错误场景。

## 已实现：显式引用转签

`decision_protocol=relay-reference-v1`。模型输入新增 `evidence_index`，以精确 claim digest 映射 fact、issuer、parents；保留原签名包供审计。所有机制臂共用该接口。

```json
{"action":"proceed","claims":["父声明ID"],"fact_ref":"父声明ID","reason":"同意按此证据转签"}
```

模型仍决定 proceed/hold，并必须选定本阶段精确父声明。worker 用本地已有且可用的父声明解析 fact_ref，所有 relay 父事实必须一致，再执行既有签名、依赖与恢复检查。fact_ref 不触发补证、不授权付款，也不会把 hold 当 proceed。

普通 `reliability_sign_derived` 和绑定 `reliability_frontier_rebuild` 均支持该接口；恢复先确定受信任信封中的 ready 节点和父列表，再解析引用。不存在、错父、已失效、非 relay、同时提交 fact 与 fact_ref 都拒绝。旧显式 fact 接口保留；错误 fact 不会被静默修正。没有复制其他组织私有状态或调用 truth。

这属于 Agent 与协议之间的类型化执行接口，是减少表达与序列化错误的工程机制；不是新的事实真实性算法，更不是已验证的模型成功率收益。对 relay 这种确定性转签，不必要求 LLM 做 JSON 抄写；真实判断仍在是否接受证据、是否查证、是否继续和是否批准。

## 实验有效性与指标修正

新增 `fault_expected / fault_realized / intervention_opportunities / containment_evaluable / validity_reason`。运行 completed 与 containment 有效性分开。故障未发生，或没有故障后的执行提议，报告直接标为不可用于该效果比较；active 是无故障对照，不伪装为 containment 正例。

intervention_opportunities 统计受错误依赖影响的明确 execute 提议，不能仅凭此计数认定“本来一定会错误完成”；真正增量仍需固定提议的对照。恢复绑定违规与业务事实错误继续分开计数。

`unrelated_overfreeze` 只统计最终 C 任务收到程序 BLOCKED/REQUEST_EVIDENCE/ESCALATE 的情况；另用 `unrelated_noncompletion` 记录所有原因的 C 未完成。前者仍是保守的最终门禁指标，不能完整捕获上游阻断造成的间接过冻。

[旧 pilot 的独立复评分](results/workflow_v1_pilot01_reanalysis/metrics.json)确认：三臂全部 fault_not_realized，C 未完成各 2，但最终协议误冻各 0。原始报告中各 2 的 overfreeze 是旧指标把所有未完成混在一起，不能作为协议误冻结论。复评分不改变历史决定和故障事实。

## 验证和下一步

**全量 183 项测试通过。**实际进程离线核验中故障成功发生，4/4 业务安全完成、2 个分支恢复，两个恢复重建请求都使用 fact_ref，worker error 与模型调用均为 0。这仅验证确定性接口和门禁接线。

新增测试覆盖内存/真实进程引用接口、错误引用/双重字段/错误规则拒绝、显式错误 fact 不修复、固定提议故障实现、无故障有效性标记。实际进程离线核验见 [结果](results/workflow_reference_v1_process_check/report.md)；它是脚本决定的接口核验，不是新 live 成功样本。

下一位实验代理先做 **1 条 active/root_gate live 接口校准**，不要立刻重跑三臂。检查显式 ID 是否被正确引用、普通派生能否登记、C/A 能否正常前进。若失败，直接归档失败原因，不自动重试；若通过，报告给用户后再启动原中间撤销三臂。active 成功不能从整体成功率分母中替换或删除旧失败 pilot。

后续中间撤销试验必须在真实签名中间声明确实登记后发生，且至少有后续动作提议，才具备相应干预机会。live 仍允许 hold，不按成功结果筛样或无限重试。参考 TASK_EXPERIMENTS_WORKFLOW_V1.md 顶部的当前交接。

目前没有证据支持改进后的真实模型成功率；也没有解决未撤销的签名事实错误。先验证这一个接口断点，再进入权威补证/冲突澄清研究，避免把无效工作流搬到更复杂场景。
