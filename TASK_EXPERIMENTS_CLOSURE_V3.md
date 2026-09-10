# 实验代理任务：closure v3，多跳传播—恢复—追溯

你只需仓库即可执行本任务。当前优先级是离线验证，不运行付费 MiniMax；不要沿用旧任务书扩大 live 矩阵。先读 `MECHANISM_CLOSURE_V3.md`、`REVIEW_CONTAINMENT_LIVE_PILOT_V1.md` 和本文件。

## 目标

分别回答：

1. 根声明仍有效、只有中间声明被发行者撤销时，完整依赖查证比根门禁增加了什么？
2. 在相同查证覆盖下，局部恢复与证据绑定能否增加正常任务完成或拒绝非法恢复？
3. 放宽低风险转发查证是否使错误传播更远，即使最终 invoice 仍安全？
4. 本地签名链能否识别中间声明通知后的违规使用，并在缺证时避免错误指控？

不要把结构性反例描述为总体错误率估计，不把“查更多”称为新的优化算法。发生负面结果要保留。

## 第一步：固定版本，正式离线矩阵

确认 `.venv/bin/python` 可用，记录 Git HEAD、未提交 diff 和新文件 hash；不要替研究者擅自改 policy 或修复结果。当前可能有尚未提交的机制代码，单记 HEAD 不够。必要回归：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m trust_network.benchmark.closure_v3 --out results/closure_v3_offline_v1
```

输出目录必须不存在；已有目录时使用新的明确版本名，不覆盖。入口生成 source hashes、每条 raw trace / evaluator truth / audit、metrics 和 report；API calls 与 token 均为零。若执行失败，保留部分目录和异常，不把部分结果当作完整矩阵。

共 5 条件 × 7 配置 = 35 条脚本 workflow，每条 A/C 订单 × a/b 下游，共 4 个业务任务，恢复不增加分母。

| 配置 | 行动检查 | 恢复 |
|---|---|---|
| autonomous | 共享结构检查，自主 freshness | bound v3 |
| simple_root_gate | 所有转发/动作查全部根，批内合并 | bound v3 |
| dependency | 原策略，默认阈值 | bound v3 |
| dependency_closure | 完整依赖，默认阈值 | bound v3 |
| verify_all_closure | 全动作查完整依赖 | bound v3 |
| dependency_closure_selective | forward loss=1，threshold=2；invoice仍完整查证 | bound v3 |
| dependency_closure + notice_only | 与严格 closure 同检查 | 普通签名派生，移除 worker 的任务证据验证 |

strict dependency_closure 和 Verify-All closure 在当前默认风险配置下应具有相同查证要求。这个等价对照是诚实校准，不应人为制造差异。selective 是单独列明的风险阈值变体，不和严格策略混报。

所有配置使用相同原始签名声明及脚本提议。每条 raw 的 `scripted_trace_hash` 必须配对一致。查询 challenge 及恢复 packet ID 可以不同；不能要求不同签名 batch 的恢复包字节一致。网络使用确定性 delay，行为造成后续不同是机制结果，不是暗中改外生故障。

条件：无撤销、根撤销、分叉前中间撤销、单分支中间撤销、部分通知后再送旧包。发行者在初始合法发布后受控撤回，然后各中间 Agent 提交固定转发提议。记录发现后的扩散，不将发现前的合法接收追认错误。

`recovery_evidence` 消息只是取证/修复输入，不是经批准的业务传播：从错误工作传播指标排除，但保留原始传输记录和消息成本。这一点要在报告中明示。

## 第二步：追溯与恢复边界

复用 `test_closure_recovery_v3.py` 和 `test_local_notice_order.py` 的边界，不重复编造大规模随机数据。整理机器可读表和机制案例，至少包括：

- 错误发行者、跨业务 scope、错误 fact、遗漏重建节点、跨任务完成包、缺失父证据；
- 原始有效派生包可通过普通 channel，但跨任务的 completion 被 bound frontier 拒绝；非法派生由两者的共同 channel 都拒绝；
- 中间声明自身的撤销通知、其他组织收到通知、只有全局时间顺序、缺少本地链；
- 已 COMPLETED / EFFECT_UNKNOWN 的任务不能被恢复器重试。

不要把共享结构检查的收益计到 evidence binding 上。当前正常恢复矩阵的 notice_only 仍共享合法调度和 offer 准备，只移除 worker 完成验证，不是“移除所有恢复证据”的极端消融。正常恢复率可能完全相同；非法恢复边界才检验绑定的直接作用。

## 指标与交付

原指标保留，并从原始 events 整理每个组织的看见、引用、继续转发与执行表。汇总错误传播距离、触达组织/分支、程序拦截、无关误冻、恢复成功、最终 unsafe completion、查询数、各类消息数。模型自行 hold 在 scripted replay 中不适用，不填写成模型成功率。

追溯分别报告声明发行者/依赖链、可证明协议违约、证据不足；无物理效果和法律责任结论。签名状态只证明发行者当前声明，未证明业务事实正确。

交付新结果目录内：`report.md`、`metrics.json`、`mechanism_cases.md`、边界案例表、源码/运行命令/完整性清单。报告分开写：检查覆盖增量、局部恢复增量、证据绑定增量、选择性查证代价。不要仅给一个总胜率。

旧 v7 与 live pilot 原始结果不修改。若补做旧 trace 语义重放，单独存目录，VERIFIED 不算执行；没有后续模型批准就报告等待明确动作，不伪造反事实响应。旧结果缺少签名 local_head 时不得按新证据等级追溯。

## 第三步：只提交 live pilot 方案

离线结果完成后再提交一个方案，不自行运行：shared-intermediate / branch-intermediate 两条件 × simple_root_gate / strict closure / notice_only 三配置，各 1 条 workflow，共 6 条；必须有两个实际 receiver 组织，共享发行者使用本地 `recovery_receivers` allowlist。

每 workflow 最多 10 次模型决定、每决定最多 2 次 provider 尝试：上限 60 次决定、120 次尝试。建议 max_completion_tokens=2048；方案必须从真实完整 prompt 估算输入 token，并明确 reasoning/usage 统计口径，不能只乘输出上限当总 token。不得擅自增加上限以获得完整恢复。

先让用户批准具体 runner、矩阵和预算。现有旧 `benchmark.live` 没有自动切换到这个 v3 pilot；新的 worker 接口已经可用，但组织调度及模型恢复提议要按本任务书接入，不能直接运行旧 live 命令冒充新实验。
