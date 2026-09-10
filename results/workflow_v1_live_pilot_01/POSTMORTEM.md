# workflow v1 live pilot 01：运行后审阅

本归档保存的是一次真实模型接口 pilot，而不是可用于比较三种机制效果的有效性实验。运行范围严格按 `TASK_EXPERIMENTS_WORKFLOW_V1.md` 执行：`intermediate_retraction` 条件，`root_gate`、`dependency`、`dependency_push` 各运行一次，process backend，live 模型决定，不自动补跑。

## 归档与运行完整性

- 三个 arm 都正常结束，`manifest.json` 标记为 `completed`，实际模型调用为每个 arm 18 次，共 54 次；没有超过单 arm 的 28 次决定和 56 次 provider attempt 上限。
- 54 次模型调用均返回可解析结果；未知用量为 0，provider failure 为 0。每个 arm 的 `worker_errors=1` 来自一次受控的 `reliability_revoke` worker 调用失败，不是模型供应商故障。
- 每个 arm 都保留了 `trace.json`、`truth.json`、`audit.json`、`metrics.json` 和 `decision_tape.json`。本地归档完整性校验为 104 个条目，missing、extra、mismatch 均为 0；结果目录中未发现 API key 或 bearer token 模式。

## 实际结果

| arm | 模型调用 | 已知 token | hold | invalid action | worker error | fault realized | unsafe completed | safe completed | unrelated overfreeze |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| root_gate | 18 | 34,496 | 14 | 0 | 1 | 0 | 0 | 0 | 2 |
| dependency | 18 | 34,299 | 15 | 1 | 1 | 0 | 0 | 0 | 2 |
| dependency_push | 18 | 34,775 | 16 | 1 | 1 | 0 | 0 | 0 | 2 |

三条 trace 的 `truth.json` 都是 `faults=[]`，并在 tick 10 记录了 `fault_not_realized`。因此表中的零传播、零 unsafe completion 和零 recovery 不能解释为 containment 成功；错误任务从未进入可传播的真实故障状态。三条运行还都出现了 6 条 handoff 和 6 条 handoff acknowledgement，审计记录成功落盘，但均没有 notice/notice acknowledgement；`physical_effect_proven=false`，责任结论为 `undetermined`。

## 发现的问题

故障注入请求由 coordinator process worker 执行，目标 claim 是模型产生的中间声明；但本次 live 决策多次 `hold` 或没有产出可登记的有效 derived packet。调度器随后使用了 trace fixture 中的 fallback packet 来构造 `reliability_revoke` 请求，而这个 packet 并没有在 coordinator 的真实 worker 状态中登记。worker 正确拒绝撤销一个不属于自己的声明，结果被记录为 `worker call failed; no success inferred`，随后标记 `fault_not_realized`。

这暴露的是 live harness 的前置状态和故障注入之间的接口断裂，同时也暴露了真实模型在当前提示和证据界面下的高 hold 率。若继续把 fallback packet 当作真实已登记状态，实验会把“故障没有发生”误算成“机制拦截了故障”。

## 结论与后续边界

本次 pilot 支持的正向结论是：process worker、模型调用、跨组织 handoff、审计链、原始数据归档和完整性校验接口可以端到端运行；模型调用预算和敏感信息检查也符合任务书。负向结论是：当前 live pilot 尚未验证错误传播控制、恢复或三种 arm 的相对效果，且真实模型在此前置流程中产生了大量 hold。

下一步应先修复并测试故障前置：只有 coordinator worker 已登记的中间 claim 才能作为撤销目标；live 模式无法建立该状态时应明确终止为 `fault_not_realized`，不应静默替换为未登记的 fallback。修复后再决定是否重新启动一个同范围 pilot。根据任务书，首次三条完成后不自动补跑，本归档也不据此启动新的付费运行。
