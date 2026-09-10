# relay-reference-v1 三臂 live 实验复核

日期：2026-09-09。范围是 `intermediate_retraction` 的一次真实进程运行，比较 `root_gate`、`dependency`、`dependency_push` 各 1 条 workflow。每条 workflow 都使用独立组织目录和 MiniMax live 决策；没有覆盖已有结果目录。

## 有效性

三臂都在 tick 10 真实撤销了 coordinator 的 A 中间声明。`root_gate` 和 `dependency` 都有 2 次受该错误依赖影响的明确 execute 提议，因此 `containment_evaluable=true`。`dependency_push` 的通知在 tick 11 到达两个中间组织，模型随后没有形成故障后的 execute 提议，故记为 `no_post_fault_action_opportunity`，不能把它的零错误完成当作 containment 样本。

## 结果

|机制|有效性|错误完成|安全完成|错误接收组织|错误动作阻断|检测延迟|恢复|模型调用/尝试|已知 token|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|root_gate|fault_and_action_observed|0|1|2|0|未检测到消费者撤销|0|18 / 18|72,275|
|dependency|fault_and_action_observed|0|0|0|2|2 tick|0|20 / 20|82,752|
|dependency_push|no_post_fault_action_opportunity|0|0|0|0|1 tick|0|19 / 20|77,032|

`root_gate` 的错误证据沿两个分支到达两个下游组织，最大绝对 hop 为 3、相对故障发行者距离为 2；它没有最终错误账单完成，是因为这次模型在后续账单动作上 hold 或提交了无效动作。`dependency` 在两个中间节点的故障后动作被完整依赖门禁阻断。`dependency_push` 展示了主动通知更早到达，但本条没有可用于比较的故障后动作提议。

三臂共有 57 次模型调用、58 次 provider attempt、232,059 个已知 token；worker error 均为 0。动作引用使用 `claim_refs` 后，长声明 ID 没有再出现转抄错误；仍有模型 hold 和后续动作无效，这属于真实模型决策行为，不能由评分器补成批准。

## 结论边界

本次支持两个机制层面的正向观察：完整依赖能在真实进程中拦截撤销中间声明，主动通知能把消费者发现时间从 2 tick 提前到 1 tick。它没有支持“真实模型错误完成率下降”的统计结论，因为三臂都没有形成足够的最终错误完成样本，`dependency_push` 甚至没有故障后的动作机会。

本次也保留了一个负结果：只检查根声明时，已撤销的中间证据仍可继续被下游接收。事实本身仍未被真实性机制验证；签名有效但事实错误的缺口没有在本实验中解决。

原始数据见各臂的 `trace.json`、`truth.json`、`audit.json`、`metrics.json` 和 `decision_tape.json`。根目录 `integrity.json` 对 104 个归档文件逐一核验，运行结束后没有修改这些原始文件。
