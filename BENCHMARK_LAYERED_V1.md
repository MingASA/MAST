# 多层级跨组织协作 Benchmark v1

本实现将已有机制放到统一任务、事件和指标入口中。原有实验作为局部贡献与边界证据保留，不能将旧数据直接拼成新协议层级主图。

## 五层含义

|层|执行机制|应观察的贡献|
|---|---|---|
|L0|普通消息与日志、共享业务合约、模型自主状态/事实查询|无协作可靠性协议基线|
|L1|签名声明、显式依赖、签名交接/签收、本地已知失效保护|完整性阻断与可核验来源/路线|
|L2|L1加动作前远端根声明状态查询|根撤销检测|
|L3|L1加完整依赖闭包状态查询、按依赖阻断|中间撤销检测及局部控制|
|L4|L3加定向通知、权威事实补证、证据绑定恢复|发现时间、隐藏事实错误控制和安全恢复|

L1已有本地保护，不把它重复算成L3收益。Verify-All保留为独立对照；当前配置与L3检查范围等价，不能仅依据名称声称增量。L4无通知、无强制事实补证、无绑定恢复分别消融，另外比较L3组织级冻结。

L0有独立Node消息路径，不创建ClaimGateway或签名证据。所有层使用相同金额、币种、订单与操作授权约束；生产发票入口仍保留原有依赖检查。L0的模型可以verify、hold及使用其他实际本地证据；verify无业务副作用，之后仍需新决定。

## 场景和运行方式

三类既有拓扑：长链分叉、汇聚后分叉、组织复用但依赖独立。十种场景：健康、传输篡改、根撤销、共享中间撤销、分支撤销、迟到通知、签名有效但事实错误、冲突来源、确认修订后恢复、权威UNKNOWN。

主矩阵150条；针对性消融及Verify-All对照60条，共210条。每条先构建相同缓存证据图，再沿实际拓扑的每条边提交故障后转交，最后提交业务动作。上游阻断不删除其他组织原有缓存，这正是后续传播需要控制的对象。

L4的恢复并非靠禁用其他层的修正制造优势。低层可以通过普通重发重建正确图；初始错误完成始终保留，不被后续成功抹去。L4-no-recovery仍允许普通修正。

初始化、故障注入和业务效果为脚本；live模型负责故障后候选转交、审批和修复决定。状态和事实查询是同步RPC，模拟耗时为0 tick；通知通过MessageBus延迟传输。不能外推为已经解决异步查证到执行之间的竞态。

## 指标与因果边界

- 错误完成：从实际执行费用事实和独立失效引用判定；按发生过错误的任务去重，同时保留错误动作次数和全任务分母。
- 错误传播：只统计实际接受的故障后错误交接、对应组织、分支和连续传播距离；缺少动作机会不算成功。
- 阻断：候选费用错误或依赖失效，且模型明确proceed而程序拒绝。模型hold、verify和无效引用单列。
- 可用性：安全最终完成、无关任务完成、误冻和恢复完成；不把“没有被协议冻住”等同于任务完成。
- 追溯：执行自身的路线证明覆盖只作诊断；主证据图使用同一执行、固定分母的证据配置投影。L1–L4可证能力可以持平。
- 责任：复用generalization_v2独立标注病例。新live没有独立责任标签，准确率为null；来源身份不等于事实责任或法律责任。
- 成本：普通/签名状态查询、事实补证、通知和字节、模型调用、provider尝试、已知token与未知usage。

所有拓扑模板、同一轨迹的证据投影与重复动作均不视为独立统计样本。live各层模型路径不同，不将其错误率差直接当配对因果估计。

## 复现入口

所有输出目录必须为新目录。所有工作状态和日志写入仓库路径，不依赖/tmp。

```bash
.venv/bin/python -m trust_network.benchmark.layered.validate --output results/layered_validation_NEW
.venv/bin/python -m trust_network.benchmark.layered --output results/layered_offline_NEW
.venv/bin/python -m trust_network.benchmark.layered.evidence \
  --offline results/layered_offline_NEW --output results/layered_evidence_NEW
```

正式live须同时提供当前代码通过的完整回归/进程验收，以及完成并验hash的210条离线矩阵。默认固定15条，不能自动扩大：

```bash
.venv/bin/python -m trust_network.benchmark.layered --mode live \
  --output results/layered_live_NEW --allow-paid \
  --env-file /home/cjy/cyberagent/.env \
  --preflight results/layered_offline_NEW/metrics.json \
  --validation results/layered_validation_NEW/validation.json
```

健康、迟到通知、确认修订三个场景×五层；每条最多28次模型决定、56次provider尝试，输出2048 token。预算耗尽保留hold，不补造后续动作或扩大预算。模型配置来自现有环境文件，不保存或显示API密钥。

历史terminal提议可通过`layered.tape`转为业务角色映射，再以`--mode tape --tape ...`运行。未映射阶段保持hold，不生成新决定。这是向新拓扑转移终端提议，不是原始签名轨迹原样重放。

## 断点与原始证据

`progress.json`记录工作流边界，逐流程raw及metrics原子写入；`workers/<index>/rpc.jsonl`逐RPC刷盘。各组织状态、owner-local配置和模型调用前后日志也持久保存。workers含签名私钥/私有账本，已从git忽略，不能当公开实验附件发布。

中断后运行：

```bash
.venv/bin/python -m trust_network.benchmark.layered.inspect_run results/layered_live_NEW
```

started但未returned的调用计为未完成，不推断未计费。不自动重跑未完成付费workflow。公开结果manifest与worker私有运行状态分开；代码hash在每条运行前后检查，变化即停止。

## 静态审查与已处理问题

本轮检查了L0签名泄漏、共用业务约束、普通状态查询、verify副作用、组织内RPC重入、拓扑根名称假设、实际篡改目标一致性、控制调度读取truth、候选阻断归因、模型hold误计、原始签名batch被传输篡改连带修改、frontier完成字段类型，以及持久化与付费门禁。

`results/layered_v1_offline`是基础设施未完成时的开发诊断，不得用作正式结果或preflight。正式结果应使用后续独立目录。
