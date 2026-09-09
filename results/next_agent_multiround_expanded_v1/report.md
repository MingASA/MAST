# V20 五组织多轮真实模型实验报告

本阶段在上一阶段结果已保存的基础上运行新目录，未覆盖 `results/next_agent_experiments/`。每个条件 6 个 workflow，每个 workflow 运行 autonomous、verify_all、dependency 三个策略臂，共 36 个策略 workflow。每个策略 workflow 最多 4 次业务模型决定：初始协调、初始接收方，以及一次补证后的协调和接收方重决策；provider 格式重试仍按 provider 的最多 1 次追加。

上一阶段归档：`results/next_agent_experiments/experiment_manifest.json`，状态 `completed`。本阶段目录：`/home/cjy/wuxing/results/next_agent_multiround_expanded_v1`。

## 任务级主结果

|条件|策略|workflow数|安全完成|不安全完成|初始拦截|程序拦截revoked|模型合约阻断|恢复成功|无关任务提交|无关任务完成|模型决定|provider失败|模型hold|查证次数|已知token|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|active|autonomous|6|6|0|0|0|0|0|6|6|12|0|0|0|34884|
|active|verify_all|6|6|0|0|0|0|0|6|6|12|0|0|30|37956|
|active|dependency|6|5|0|0|0|0|0|6|6|12|0|1|20|34214|
|hidden_revoke|autonomous|6|0|6|0|0|0|0|6|6|12|0|0|0|38146|
|hidden_revoke|verify_all|6|3|0|6|6|0|3|6|6|22|0|3|36|82884|
|hidden_revoke|dependency|6|1|0|6|6|0|1|6|6|19|0|5|22|65209|

策略合计：

|策略|workflow数|安全完成|不安全完成|unsafe/workflow|safe/workflow|恢复率/hidden workflow|无关任务完成率/提交|模型API尝试|响应数|usage未知|查证次数|旧声明正式到达组织累计|最大传播跳数|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|autonomous|12|6|6|0.5|0.5|0.0|1.0|25|25|0|0|24|2|
|verify_all|12|9|0|0.0|0.75|0.5|1.0|37|37|0|66|24|2|
|dependency|12|6|0|0.0|0.5|0.16666666666666666|1.0|31|31|0|42|24|2|

比率的分母均为任务级 workflow；模型 hold、provider failure、EFFECT_UNKNOWN 不计为安全完成。旧声明的组织触达按事件日志中签名 claim 被 `receive` 接受的组织计数，模型看见输入与网络正式接受分开。

## 正负结果与 Q1—Q6

Q1 程序介入：本阶段有 12 个 workflow 的账单提议在输出中明确带有受控 revoked root，并被程序在动作前拦截；逐个轨迹见对应 run_record、batch 和 authority reply。
Q2 正常可用性：active 条件按 workflow 报告安全完成、hold、provider failure 和无关任务完成；本阶段每条件 6 个 workflow，仍需结合置信区间解释完成率。
Q3 传播控制：旧 freight 声明先由 coordinator 接收，再由 coordinator 转给 receiver，记录正式触达组织和传播跳数；这是本机串行消息路径，不是跨物理主机部署。
Q4 局部恢复：5 个 workflow 完成了新来源接收和派生 total 重建，5 个完成了恢复轮模型重决策；最终恢复完成数仍以表中 safe completion 为准。
Q5 合理追溯：事件、签名答复、旧新声明和独立 truth evaluator 可以定位已收到否认后是否仍完成；通知责任、恶意意图和损失归因仍不能从这些证据推出。
Q6 成本：报告真实模型 API 尝试和 provider usage，以及各策略查证次数。Verify-All 会查询全部相关根；dependency 仅对受保护动作联合查证并让无关低风险分支继续，具体差异以表中小样本为准。

失败归类：本轮有 provider failure（0 / 89）、模型 hold 9 次、解析器拒绝不完整提议 1 次；自主臂出现的 hidden_revoke 不安全完成按基线结果保留，未把它改写成机制成功或失败的其他类别。样本不足以推广为总体可靠性。

本次收尾核验：真实模型决定 89 次，provider failure 0 次；原始运行记录中的模型 claim 结构错误造成合约阻断 0 个。收尾修正后的解析器未重新调用模型；原始失败轨迹均已保留。

## 边界

控制器只在实验事件注入时知道 condition；业务模型收到共同 system prompt、本组织工作手册、公开签名声明、可用工具和相同恢复轮数，不收到 evaluation_truth、其他组织私有状态、目录名或私钥。执行结果是模拟适配器报告，不代表付款、发货或物理副作用。
本阶段仍是有界 pilot，不是统计充分的总体可靠性结论。没有按正结果调参重抽；provider failure、model hold、非法结构化输出和未完成恢复均保留。
