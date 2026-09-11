# 多层级 benchmark 实现恢复说明

当前状态（2026-09-10，重启后）：**机制与基础设施实现完成；代码绑定完整回归248 passed，包含5个进程等价病例。正式离线矩阵210/210完成，原始manifest及当前代码hash校验通过。已有历史终端提议五层重放完成。尚未新增MiniMax调用。**

最新交付入口是最终统一 live 报告：[FINAL_UNIFIED_LIVE_BENCHMARK_20260911.md](FINAL_UNIFIED_LIVE_BENCHMARK_20260911.md)。以下旧开发检查项为历史记录，最终验收以公开归档的 manifest 和异常审计为准。

用户已确认：L0–L4 五层加 L4 分项消融；首版含 15 条有界新 live（健康/迟到通知/隐藏事实修复 × 五层），每条最多28次模型决定/56次尝试。但须先完成基础设施静态审查及离线验收。用户随后要求不要使用 /tmp 存任务文件，以便关机后继续。

## 已落地在仓库

- `trust_network/benchmark/layered/`：独立 L0 普通消息 Node、签名层 Node、内存/持久进程 RPC、五层配置、拓扑适配、注入/通知/查证/恢复主链、评分、绘图、固定证据消融、历史提议适配。
- `trust_network/demo/claim_action_contract.py`：提取共享业务规则 `validate_invoice_facts`，生产包装仍保留依赖门禁。
- `trust_network/tests/test_layered.py`：初步的分层、恢复、L0隔离、进程等价检查。最近修改尚未正式验收，旧通过结果不能代表当前完成。
- 持久存储：runner 的 worker 配置、状态和逐RPC日志放在 output/workers；进度、metrics 原子替换，逐RPC日志 fsync。签名密钥仅存权限600的 worker配置，workers已忽略git。没有新增MiniMax调用。
- `.local/layered_implementation/`：本轮已应用的辅助编辑脚本备份，非运行依赖。

## 静态审查已发现并修改

1. 同组织状态查询导致进程回调重入：worker直接处理本地查询，并回传本地交换日志。
2. 组织复用拓扑没有 root_C，实际是 root_C_a/root_C_b：账本和授权改从实际根声明订单生成。
3. L0自主verify只有事实查询：补普通发行者状态查询；verify不执行效果，后续需模型新决定。
4. 恢复调度直接用评价真值筛选任务：改为按公开修订的业务订单筛选。
5. 篡改目标硬编码receiver_a、不同层篡改不同字段：改为固定逻辑任务A_a的声明，在初始和故障后指定转交处篡改。
6. 部分结果按场景名称判错或把repair阶段当成功：改为实际执行事实+独立expected_cents/invalid_claim_ids评分；仍需检查计数去重和误冻定义。
7. 只执行故障后最后一跳：已改为沿拓扑所有边实际提交转交，缓存证据可继续被提议；需核对新距离与分支计数。
8. 历史引用角色@total/@authorization已接入choose映射；需检查不修复原本非法引用。

## 旧开发运行（不是正式结果）

`results/layered_v1_offline`：早期版本完成140/210后因root_C假设中止。该目录只作诊断，不能作为preflight或主实验结果。
旧全量测试曾在修改期间运行，不能视为当前版本正式验收。之前针对进程的代表测试通过；随后还有静态修改。

## 继续工作优先顺序

1. 完整静态检查，再补必要问题。重点：评分中的错误动作/模型hold/验证请求分离、普通L0无签名泄漏、拓扑命名无硬编码、故障后全路径传播、恢复不能直接读truth、历史tape不补造动作、缺证据时不指控。
2. CLI正式live门禁还需增强：目前只检查210条metrics和fault_realized，不足。应绑定当前代码hash、正式preflight状态、进程检查和原始manifest；同一批次禁止运行期间改代码。
3. 持久恢复：运行中已有每工作流进度和逐RPC原始日志；尚未实现自动resume。不得自动重跑关机前未完成的付费workflow。先从rpc.jsonl核对已发生调用，明确中断状态，避免重复计费。
4. 最小静态/代表场景验证完成后，重新运行正式210条离线矩阵到新目录，完成旧回归。不要覆盖诊断目录。
5. 跑固定证据消融；复用generalization_v2责任标签，不给新执行伪造责任真值；历史late_notice提议迁移单列“终端提议转移”，不是原始签名执行重放。
6. 输出preflight、静态审查结果、实现说明；再按计划运行15条live（需/env配置存在性检查，不输出密钥）。使用仓库内持久目录。
7. 最后输出报告、图、manifest、原始数据、成本和边界。不能为了层级递增而隐藏持平项。

用户原计划中的重要限制：所有层共享业务约束；L1已有本地保护；L3增量是完整远端依赖；L4无恢复消融仍允许普通重发；通知RPC与实际业务异步竞态不能被零延迟模拟冒充解决；所有业务效果为模拟，初始化图是脚本构建而非模型生成。

补充：已新增preflight.py，对完成状态、210条唯一矩阵、原始文件manifest、共同输入hash和当前代码hash做live门禁；runner已加入批次代码变化检查。仍需代表进程/测试验收记录绑定及正式验证。每次provider调用前后均在workspace的owner.provider.jsonl保存started/returned/failed，未完成调用不得自动重跑。

最后静态修正：原始签名batch中的handoff先复制后再模拟传输篡改，避免污染原始动作签名记录；verify参数与proposal.intent不一致直接拒绝；恢复frontier缺remaining字段不再被误当恢复完成。
仍需检查：error_action_blocks的候选错误归因应依据实际费用事实/失效引用，避免仅因共享授权引用而误计；进程异常保存/未完成调用恢复需验收；tests中的进程等价须覆盖组织复用拓扑与修复场景。不要引用旧测试数为当前验收通过。

重启后修正与验收：见 BENCHMARK_LAYERED_V1.md 及 results/layered_v1_validation_final/STATIC_REVIEW.md。静态问题候选归因、接收状态、恢复remaining数量字段、live门禁/日志已处理。代表性运行曾发现remaining字段类型误配并修正；不能引用早期focused.log作为最终通过结果。


## 2026-09-11：最终统一 L0–L4 live 结果

最终统一计划包含 300 条主实验和 50 条消融；344 条完成，6 条因审计暂停时没有最终调用结果而保留为 unknown。错误完成率从 L0 的 36.2% 降至 L4 的 0%，错误传播交接从 242 降至 0；L4 恢复请求 10/12，最终恢复 6/12，4 条因 workflow 预算耗尽停止。完整公开汇总见 [`FINAL_UNIFIED_LIVE_BENCHMARK_20260911.md`](FINAL_UNIFIED_LIVE_BENCHMARK_20260911.md) 和 `results/final_unified_live_v1_combined_20260911/`。
