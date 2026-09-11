> **2026-09-10 历史 live 证据消融已接通：** [报告](results/contribution_live_archive_replay_v1/report.md)。保留三条历史轨迹原始签名批次，完成 84 个证据投影；完整证据可证路线 35/35、来源身份 12/12，诚实普通日志仍可估计路线 35/35。历史缺独立责任标签，责任准确率不计算；没有新模型调用。

> **2026-09-10 协议贡献对照基础设施：** 通知范围与冻结粒度做 2×2 对照；同一签名执行做证据包消融、缺失/乱序/歧义和责任负例审计。原三指标图仅作共享运行时传播诊断，不能以 C=100% 或条件路由召回=100% 证明独立贡献。该受控轴后来纳入最终统一 benchmark 的消融与追溯归档。

> **2026-09-10 协议贡献对照离线实验已完成：** [实验报告](results/contribution_experiment_v1_figures_20260910/report.md)、[冻结四格图](results/contribution_experiment_v1_figures_20260910/freeze_four_cells.png)、[固定分母追溯图](results/contribution_experiment_v1_figures_20260910/traceability_fixed_denominator.png) 和 [原始归档](results/contribution_experiment_v1_20260910/)。8 个冻结条件、140 个证据投影和公开观察审计均已完成，213 项测试通过，新增付费调用为 0。结果支持依赖粒度减少无关分支误冻、完整证据提供可验证路线和来源身份；普通日志在诚实条件下可以估计路线，但不能提供签名可证性。该结果仍是受控机制验证，不代表一般错误率或法律责任准确率。

> **2026-09-10 Contribution Generalization v2 已完成：** [报告](results/contribution_generalization_v2/report.md)、[拓扑/时序图](results/contribution_generalization_v2/freeze_topology_timing.png)、[责任证据图](results/contribution_generalization_v2/responsibility_evidence_ablation.png)。完成 48 条冻结运行和 120 条责任投影，覆盖长链后分叉、汇聚后分叉、组织复用独立依赖，以及 receiver_a/b/c 三个执行组织。按时通知下 unsafe completion 为 0/36；晚通知下保留 26/36 个截止前错误完成；dependency 过度冻结为 0，粗粒度 workload 累计误冻 34 个无关任务；责任负例误指控为 0/96，证据不足正例 9/9 进入待定。全量测试 228 项通过，未调用模型；这些是受控机制结果，不是独立统计样本或现实 Agent 泛化证明。

> **2026-09-10 自然修复入口扩大 live 结果：** [结果与原因分析](results/dispute_live_repair_entry_analysis_20260910/report.md)。上下文修复后的 12 条 MiniMax-M3 workflow 共 24 个 A 分支：24/24 先安全 hold，21/24 提交无副作用 `request_recovery`，20 个进入恢复，40/40 个逐层重建包通过，18/20 个恢复后完成；无 worker error、无效动作或 unsafe 初始完成。该组证明恢复入口和协议闭环可用，不证明一般错误率下降；下一步是 UNKNOWN、source hold、错误修订和错误绑定的负向闭合。

> **2026-09-10实验复核：** [核实结果、四策略图与下一步](REVIEW_EXPERIMENTS_20260910.md)。配对重放2/16→0/16支持完整依赖相对根门禁的增量；三种完整检查臂等价。事实补证/争议恢复已存在，不重复建设。新的真实流程缺口是自然hold缺少修复入口；本轮只生成已有数据图表，未调用模型。

> **2026-09-10 争议 live pilot 已完成：** [五条 pilot 总结](results/dispute_live_pilot_v1_summary.md)。`v1_05` 在真实 MiniMax-M3 + ProcessBackend 上完成两条 A 分支的“候选被门禁阻断、来源模型修订、独立确认、四个派生声明逐层重建、恢复后再动作”闭环；`v1_02` 的自然决策样本中 A 安全 hold、C 两分支完成。五个归档正负结果均保留，当前全量测试 198 项通过。这是接口和受控场景证据，不是策略效果统计。

> **2026-09-10 统一 workflow live 扩大实验已完成：** [阶段分析与正负结果](results/workflow_v1_experiment_analysis_20260910.md)。当前代码的 88 条离线矩阵和实际进程回放均通过完整性核对；真实 MiniMax-M3 共归档 21 条 workflow、345 次模型调用、346 次 provider 尝试。4 条独立真实 intermediate tape 的五臂配对重放中，autonomous/root_gate 各有 2/16 个错误完成，dependency/dependency_push/verify_all 均为 0/16，并各阻断 6 个错误动作。active live 的模型 hold/无效提议和 `signed_false` 的事实缺口同时保留。核心依赖门禁进入冻结状态，下一步转向事实冲突补证和 benchmark 三指标图。

> **事实补证与争议恢复已落地：** [实现、结果和边界](FACT_EVIDENCE_V1.md) 与 [争议传播/恢复](DISPUTE_RECOVERY_V1.md)。16条离线流程、真实进程核验和新的 live pilot 共同显示，独立权威补证、沿交接路径的争议广播、局部冻结和确认后重建均已接通；签名有效但事实错误仍是机制边界。

> **ee7a12d live 复核：** 完整依赖已阻断两次真实错误转交，push 提早通知后两位中间 Agent 选择 hold；最终错误率下降尚未证明。新增评分区分故障试验与硬门禁机会，并修复 claim_refs 引用漏计。下一阶段见 [事实补证协议规格](NEXT_FACT_EVIDENCE_PROTOCOL.md)；该新协议尚未实现，不自动扩大付费实验。

> **最新状态：** 首个 pilot 01 的 54 次调用全部未实现故障，历史归档不作效果比较。新增 `relay-reference-v1` 后，三条 active live 校准中的最新一条已实现 6 个派生阶段和 4 个中间转交；随后一次 [三臂中间撤销实验](results/workflow_reference_live_intermediate_02/POSTMORTEM.md) 真实注入故障。完整依赖拦截两条错误动作，push 提前 1 tick 发现，根门禁让错误中间证据传播到两个下游组织；最终错误账单均未完成，主要受模型 hold/无效后续动作影响，因此不能声称真实错误率下降。当前全量测试 185 项通过。

> **当前状态：统一 workflow benchmark v1 已落地。** 请优先阅读 [设计与结果解释](BENCHMARK_WORKFLOW_V1.md)、[实验交接](TASK_EXPERIMENTS_WORKFLOW_V1.md)。已归档 11 条件 × 8 臂 = 88 条离线流程、2 条真实进程离线对照、v7 原始 151 文件校验和 6 批重放一致；首个 3 条 live pilot 因故障未实现而无效，修复后又完成 3 条 active 校准和 3 条中间撤销三臂实验。完整依赖在这次 live 运行中拦截了两个错误动作，push 提前发现，但模型行为使最终错误完成样本不足；未撤销事实错误仍未解决。以下较早阶段的“正式矩阵未运行”等描述保留为历史，当前以新 benchmark 报告为准。

> **上一阶段机制记录：** 在 closure v3 之上新增本地交接反向索引、有签收的级联撤销通知，以及恢复证据二次失效的局部处理。见 [机制说明](MECHANISM_DEPENDENCY_NOTICES_V1.md) 和 [实验交接](TASK_EXPERIMENTS_DEPENDENCY_NOTICES_V1.md)；当前 live 结论以 workflow v1 结果为准。

> **上一阶段 closure v3 记录：** 已实现完整依赖查证、中间声明修订、受约束后代恢复与本地签名顺序追溯，158 项测试通过；其正式矩阵与旧 C pilot 的边界记录保留在下方。当前请优先读 workflow v1 的 [机制说明](BENCHMARK_WORKFLOW_V1.md) 与 [实验交接](TASK_EXPERIMENTS_WORKFLOW_V1.md)。

# 当前项目总结：跨组织 Agent 网络的可靠性、传播控制与追溯

更新时间：2026-09-10

本文是当前项目的状态说明和下一阶段工作依据。它以仓库当前代码、任务书和已保存实验原始数据为准；历史 checkpoint 保留原样，不用新结果覆盖旧结果。

> **2026-09-10 安全失败场景已完成：** [live与离线报告](results/dispute_safety_live_pilot_20260910/report.md)。三条真实流程覆盖 authority `UNKNOWN`、source 无当前修订记录和错误修订；分别观察到程序 fail-closed、模型 hold 和程序拒绝，初始A错误完成均为0。离线6个负向场景中5个程序拒绝全部通过，错误任务、过期和重放证据均未改变网关状态。该结果补齐安全失败证据，不支持一般错误率、全面恢复率或法律责任结论。

## 一句话判断

项目已经从一个“有签名声明、依赖检查和动作门禁，但多轮恢复尚未接通”的 V20 实验原型，发展成一个可以由真实模型驱动的、带局部冻结和证据约束恢复的跨组织协作可靠性原型。

它已经具有系统设计上的贡献潜力：在组织私有状态不共享的情况下，把声明依赖、权威状态变化、错误分支冻结、派生声明重建、模型重新决策和证据边界审计串成一个运行时闭环。

它还没有足够证据支持更强的结论：当前尚不能声称已经普遍降低了跨组织网络的错误传播率，也不能声称已经实现了法律意义上的准确责任归因。下一阶段必须用一个公平的 benchmark 测量这些增量，而不是继续在单一账单场景中重复正向 pilot。

## 我接手实验时的起点

接手时的基线是 V20 可靠性实现。它已经具备以下基础：

- 每个组织有自己的声明网关和本地状态；声明、撤销、依赖和派生规则可以验签和重放。
- 接收方可以按动作依赖展开根声明，合并共享根的查证，并在动作前通过 `run_batch` 拦截模型提议。
- `autonomous`、`verify_all` 和 `dependency` 三个策略可以在同一 fixture 上进行程序重放。
- B 阶段固定真实模型提议 pilot 已经完成，能保存真实请求、响应和 usage；C 阶段的多轮 runner 也已经存在。
- 本地 preflight 和基本的签名审计、策略审计、动作合约测试已经完成。

但当时的 C 阶段还不是完整的“模型产生决定、系统按事件恢复、模型再次决定”的闭环。任务书列出的实际缺口是：

1. 没有完整恢复控制器按事件顺序调用各接口；
2. 没有基于权威私有业务状态签发新来源声明的 worker 操作；
3. `replacement_offer` 不会自动证明协调器已经登记新来源，需要调度器显式保证；
4. 恢复信封只描述要重建的派生声明，没有通用的按新父声明重建并重新签名的执行器；
5. 恢复后的新证据没有自动交给真实模型重新产生 coordinator/receiver 决定；
6. `run_batch` 可以执行，但前面的新提议还要由外部模型或调度器正确生成。

因此，当时的代码可以证明某些门禁路径能够运行，却不能证明一个真实模型驱动的跨组织流程能够在失效声明出现后完成受约束恢复。

## 从起点到当前版本的重要变化

| 领域 | 接手时的状态 | 当前版本的状态 |
|---|---|---|
| 多轮调度 | 有 bounded runner 和局部接口，恢复提议的生成和顺序不完整 | `WorkflowController` 按事件顺序运行来源发布、传播、模型决定、受控撤销、恢复和再次门禁，并保存 hash-chained controller events |
| 权威新来源 | 没有标准 worker 操作保证新来源来自权威私有状态 | `reliability_replacement_source` 只允许原权威从本地声明状态签发同范围的新根声明 |
| 新旧来源关系 | 有 replacement offer，但登记状态需要外部假设 | 权威签署 replacement offer；调度器让 coordinator 实际 `receive` 新来源；当前版本再生成可验证的 `recovery-evidence-v1` |
| 派生声明 | 信封能列出受影响派生声明，但缺少通用执行器 | `rebuild_derived_claim` 精确检查旧 claim、父列表、替换映射、规则和 `valid_derivation`，由原派生声明发行者重新签名；旧声明和撤销记录保留 |
| 模型恢复 | 新提议需要外部拼接，恢复模型轮没有自动接上 | coordinator 根据新证据重新决定派生 total，receiver 再根据新 total 重新决定 invoice；hold、失败和非法结构不被改写成 approve |
| 恢复证据 | offer 和登记事件作为临时 notice 字段拼装 | `build_recovery_evidence` 在 coordinator 本地验证 envelope、offer、新来源和本地 `received` 事件，用 `evidence_id` 绑定完整任务和签名 artifact；重建 worker 在写入前再次验证 |
| 模型输入绑定 | 需要手工保证模型使用完整父声明 | public claim view 保持签名摘要稳定；coordinator 的 `claims` 必须逐字等于完整 `required_parent_claims`；receiver 的 invoice 提议必须同时引用 authorization 和 total |
| 程序安全边界 | 已有动作门禁，但 C 阶段未覆盖恢复后的再门禁 | 恢复只重建证据，不授权业务动作；新提议必须再次进入查证、局部冻结和动作合约 |
| 责任审计 | 曾把 authority 自己收到撤销误当作消费者通知 | 当前审计区分来源方本地 receipt、消费者正式收到的撤销、实际使用顺序和证据不足；没有通知、义务和损失模型时返回 `undetermined` |
| 实验记录 | 有真实模型 pilot 和离线重放 | 每个 run 保存原始模型请求/响应、解析决定、usage、签名包、批次、事件、评估、accountability 和 hash manifest；已有扩大多轮实验及 v6/v7 独立目录 |
| 回归验证 | 局部测试覆盖基础路径 | 当前代码最近一次全量测试为 `200 passed`，包含争议/事实/恢复和 live adapter 的边界测试；安全失败 live 与离线归档完整性均通过 |

这些变化不是把模型 prompt 改得更容易通过，而是把原来由调度器口头假设的恢复条件变成运行时可验证的接口和事件。

## 当前版本的准确描述

当前系统应描述为：

> 一个面向跨组织、部分可见 Agent 工作流的 evidence-bound、dependency-aware runtime control prototype。每个组织只持有自己的本地状态；公开声明带有签名、来源和父依赖；接收方以动作依赖为单位进行状态查证和程序门禁；发现受控状态变化后，只冻结受影响分支，在权威新来源和签名恢复证据到达后重建派生声明，并要求真实模型重新提交决定；独立审计根据签名和事件顺序报告可证明的来源、通知和义务事实，在证据不足时保持不确定。

这一定义中的几个词有严格边界：

- **跨组织**：当前是 buyer、supplier、carrier、coordinator、middle、receiver 六个组织的独立本地目录/进程和签名消息路径，组织服务不直接读其他组织私有文件；还不是跨物理主机、真实机构系统或公网服务。
- **错误传播**：当前能测量声明被哪些组织正式接收、在模型输入中出现几次、被哪些动作引用以及几跳到达；当前 live fixture 的实际路径是本机串行传播，最大为三跳。
- **恢复**：当前恢复的是声明依赖和新的动作提议，不是撤销历史、外部付款、发货或其他物理副作用的回滚。
- **责任追溯**：当前能定位签署者、父依赖、接收事件、查证答复、使用批次和是否有消费者通知；它能证明某些协议义务事实，但不能仅凭签名证明事实真伪、恶意意图、实际损失或法律责任。
- **autonomous**：当前实验中的 autonomous 是“自主选择 freshness verification 的消融基线”，不是完整能力意义上的 autonomous Agent 基线；任务书和报告都按此限制表述。
- **安全完成**：是独立评估器根据事件序列真值判定的 workflow 结果；模拟 effect 只是 adapter report，不是现实业务动作凭证。

当前核心路径可以画成一条有条件的证据链：

```text
权威来源声明
  → 签名传播与本地依赖图
  → Agent 提交动作提议
  → 程序按根依赖查证和门禁
  → 受控撤销/状态变化
  → 只冻结受影响分支
  → 权威签发新来源 + replacement offer
  → receiver recovery envelope
  → coordinator 登记新来源并生成 recovery-evidence-v1
  → 原派生声明发行者按新父声明重建
  → coordinator/receiver 真实模型重新决定
  → 再查证、再门禁、记录动作和责任证据
```

## 当前实验给出的证据

### 扩大多轮实验

`results/next_agent_multiround_expanded_v1` 运行了 active 和 hidden revoke 两个条件，每个策略每个条件 6 个 workflow，共 36 个策略 workflow；真实 MiniMax 决定 89 次，provider 尝试 93 次，provider failure 为 0。原始目录 1097 个文件的 hash 完整性全部通过。

| 条件 | 策略 | 安全完成 | 不安全完成 | 程序拦截 | 恢复成功 | 模型 hold | 查证次数 |
|---|---|---:|---:|---:|---:|---:|---:|
| active | autonomous | 6/6 | 0/6 | 0 | — | 0 | 0 |
| active | verify_all | 6/6 | 0/6 | 0 | — | 0 | 30 |
| active | dependency | 5/6 | 0/6 | 0 | — | 1 | 20 |
| hidden_revoke | autonomous | 0/6 | 6/6 | 0 | 0/6 | 0 | 0 |
| hidden_revoke | verify_all | 3/6 | 0/6 | 6/6 | 3/6 | 3 | 36 |
| hidden_revoke | dependency | 1/6 | 0/6 | 6/6 | 1/6 | 5 | 22 |

它给出的最可靠方向信号是：程序介入稳定存在，且保护策略可以阻止 autonomous 基线继续执行 revoked 依赖。它同时暴露了 recovery coordinator 在旧/新来源并存时容易 hold，说明模型可用性和恢复证据呈现是瓶颈。

成本不能写成已经节省：扩大实验中 dependency 的查证次数和已知 token 低于 verify_all，但高于 autonomous；恢复成功也低于 verify_all。小样本 Wilson 区间已另存，不能把这些比例外推成生产可靠性。

### v6 到 v7 的恢复证据变化

v6 首次把签名 replacement offer 和 coordinator registration event 直接放入恢复模型输入。v6 中 dependency 的两个 workflow 有一个完整恢复，另一个在初始 coordinator 阶段因模型误读来源语义而 hold；这不是被隐藏的失败，原始轨迹保留。

随后把这两项证据以及 envelope、新来源和精确 rebuild task 固化为 `recovery-evidence-v1`，再运行 v7：

- hidden revoke；autonomous 2 个 workflow，dependency 2 个 workflow；
- 共 12 次模型决定、12 次 provider 尝试、0 次 provider failure；
- autonomous：2/2 不安全完成；
- dependency：2/2 程序拦截、2/2 来源替换、2/2 派生重建、2/2 receiver 重决策、2/2 安全完成；
- 原始目录 151 个文件，hash 全部有效，事件链和 accountability 文件全部有效。

v7 是标准接口已经能被真实模型走通的正向信号，不是恢复率估计。N=2 太小，不能单独支持普遍性结论。

详细原始数据和报告：

- [扩大多轮实验](results/next_agent_multiround_expanded_v1)
- [扩大实验统计分析](results/next_agent_multiround_expanded_v1_analysis/report.md)
- [v6 恢复 pilot](results/next_agent_recovery_model_pilot_v6)
- [v7 标准证据 pilot](results/next_agent_recovery_model_pilot_v7)
- [标准恢复证据 checkpoint](CHECKPOINT_2026-09-09_RECOVERY_EVIDENCE_V1.md)

### 争议传播与确认恢复的真实模型 pilot（2026-09-10）

按 [TASK_EXPERIMENTS_DISPUTE_V1.md](TASK_EXPERIMENTS_DISPUTE_V1.md) 补齐了薄 live adapter，并保存了五条 MiniMax-M3 流程。第一条暴露 receiver claim 引用类型错误，第二条给出自然决策下 A hold/C 完成，第三条记录安全 hold 和一次 provider timeout，第四条验证 A 候选被 runtime 阻断并完成四层重建但最终模型因缺少确认上下文而 hold；补齐签名 revision offer 后，第五条在两条 A 分支完成完整恢复闭环。完整数字和正负解释见 [pilot 总结](results/dispute_live_pilot_v1_summary.md)。

这组数据支持当前协议的真实进程接线、局部冻结、来源自主提出修订、独立确认和按 `fact_ref` 逐层恢复；不支持自然 Agent 恢复率、四策略相对效果或网络级错误率的统计结论。下一步冻结争议 v1 机制，优先进行固定前置状态下的 benchmark 回放和少量有针对性的自然负向场景。

## 当前设计是否已经足够构成贡献

答案要分两个层次。

作为系统原型，已经足够形成一个清楚的贡献候选。贡献点不应写成“发明了签名、依赖图、撤销或运行时门禁”，而应写成这些机制在跨组织部分可见网络中的联合运行时协议：动作依赖决定查证范围，已知负面证据沿依赖分支冻结，权威新证据只能通过受约束恢复进入，派生声明必须由原发行者重建，模型必须在恢复后重新决定，审计器只在事件和义务证据足够时下结论。

作为一篇声称“降低网络错误传播并准确追责”的强实证研究，目前还不够。原因不是代码没有完成，而是主张尚未被公平 benchmark 充分区分：

1. 当前真实模型 pilot 仍只覆盖一个受控的 hidden revoke、简化 invoice 和单个三跳链；离线 benchmark 已覆盖分叉和多类错误，但 live 还没有覆盖丢失、重复、乱序和部分通知。
2. 当前的保护效果可能部分来自最基本的“revoked 就阻断”，还没有用 ablation 证明 dependency-aware 冻结、派生重建和标准证据 bundle 各自增加了什么。
3. 当前责任审计能正确地在证据不足时返回 `undetermined`，但这也说明尚未定义并实证验证一套跨组织通知义务、派生义务和使用义务。
4. v7 的 2/2 恢复是接线证据，不是稳定性证据；扩大实验的 recovery 成功率仍受真实模型 hold 影响。
5. 当前系统是本机独立进程和模拟 effect；它还没有证明跨物理设备部署、远程消息可靠性、远程状态和外部动作的原子性。

近期已有工作分别覆盖了 provenance-based 执行前防护、Agent auditability 的 detect/enforce/recover 框架，以及协作图、义务图和证据映射的联合审计。因此本项目的可辩护差异必须落在“跨组织私有状态、动态状态变化、依赖分支控制、恢复再决策和证据受限追溯的联合实证”上，而不是落在单个基础组件上。这里的文献核对是贡献定位用的快速核对，不是完整系统综述：

- [ProvenanceGuard：基于 provenance 的 Agent 执行前防护](https://arxiv.org/abs/2607.01236)
- [Auditable Agents：auditability、detect/enforce/recover 与责任边界](https://arxiv.org/abs/2604.05485)
- [iCORE：协作图、义务图和证据映射的联合审计](https://arxiv.org/abs/2607.27429)

当前最稳妥的研究表述是“提出并验证一个 evidence-bound、dependency-aware 的跨组织 Agent 可靠性协议原型”，并把网络级效果和责任定位留给 benchmark 验证。

## 下一步任务

下一步不是继续重复同一条静态 live 条件，也不是把本次零错误完成直接当成错误率结论。当前 **causal containment-and-accountability benchmark v1** 已完成离线闭环、进程核验、接口校准、一次有效性分层的三臂 live 实验、争议传播/确认恢复的自然修复 pilot，以及本次安全失败场景验证。

下一阶段的顺序是：

1. 冻结当前机制和实验口径，把“模型自行 hold”“程序拒绝提议”和“程序阻断动作”分开报告；`dispute_live_pilot_v1_05` 的 probe 样本不混入自然成功率。
2. 收敛论文主线，统一呈现预防、局部隔离、自然修复、安全失败和可证明追溯，并把本次 UNKNOWN/source hold/错误修订结果作为负向边界。
3. 仅在写作复核发现明确缺口时做定向离线检查；不再扩大同一成功场景的付费实验。改变核心方向或重新扩大 live 范围前保留用户决策点。

## Benchmark 的内容：它到底要模拟什么

当前 benchmark 已经把“两栋办公室之间的一条走廊”扩展成一张可重放的小型道路网络：7个组织、3跳、双分支、11类条件和8个机制臂。每个组织是一个节点，每条签名消息是沿道路运输的证据包，每个节点只看到自己收到的包和自己的私有状态；错误在每个路口分别记录是否收到、接受、引用、转发和触发动作。

它同时保存脚本化前置图、固定提议 replay 和真实模型 live trace。前置图仍由脚本准备，seed 主要改变 workflow 标识；因此当前结果衡量的是机制和接口在受控图上的行为，不是 Agent 自主生成整个网络的能力。

### 1. 拓扑和消息传输

当前第一版使用确定性的虚拟 message bus，并以独立 ProcessBackend 做进程核验；它支持：

- 三跳或更多跳的 source → coordinator → intermediary → receiver 路径；
- 一个来源被多个协调器或多个 receiver 接收的 fan-out；
- 可预先设定的 delay、drop、duplicate 和 reorder；
- 每个组织独立的 claim store、revocation store 和事件链；
- 传输事件与模型看到的输入分开记录：收到一包消息不等于模型引用过它，模型看到它也不等于动作真的通过门禁。

形象地说，benchmark 要记录一封信经过哪些邮局、哪些邮局盖了收件章、哪些 Agent 读了信、哪些 Agent 把信里的数字写进了申请单。四种记录必须分开，否则“传播了”会被错误地等同为“执行了”。

### 2. 故障场景

当前第一版已覆盖以下受控场景，并为每一类保存独立的事件序列真值：

- **延迟撤销**：旧根已经传播，权威随后撤销；部分组织收到通知，另一部分没有收到。
- **分支传播**：同一旧根进入多个下游分支，只有其中一条分支查证或恢复，测量局部冻结是否真的局部。
- **下游派生错误**：协调器漏掉父声明、改变金额或用旧父声明重建；测试规则校验和责任定位。
- **冲突来源**：同一业务范围出现两个签名来源或新旧来源同时存在；测试 Agent 是否按权威、范围和事件顺序处理，而不是按最后出现的文本选择。
- **传输异常**：撤销或 replacement evidence 延迟、丢失、重复或乱序；测试系统是否安全地 hold/升级，并保留证据不足状态。
- **签名有效但事实错误的负控制**：权威签署了一个语法和范围都正确、事实却错误的声明。这个场景用于明确机制的边界：provenance 能追踪来源和使用，不能仅凭签名证明事实真实。

这些不是为了堆很多攻击类型，而是为了把“错误从哪里来、怎么传播、在哪个节点被看见、哪个节点仍然有义务停止”拆开。

### 3. 对照策略和因果关系

当前第一版已实现四个主策略臂和恢复绑定消融：

1. unmediated freshness baseline：允许 Agent 自主选择是否查证，准确标注为消融基线，不称为完整 autonomous 能力基线；
2. simple root gate：发现直接 revoked root 就阻断，但不提供 dependency-aware 局部恢复；
3. 当前 dependency：使用依赖展开、共享查证、局部冻结、标准恢复证据和恢复后再门禁；
4. verify-all：对相关根全面查证，作为安全和成本的参考上界。

还应有一个针对性 recovery ablation：保留当前 gate，但移除 `recovery-evidence-v1` 的标准绑定，观察模型能否仅凭普通 notice 完成同一恢复。这样才能知道 v7 的正向结果来自协议证据，还是仅仅来自更清楚的文字提示。

因果比较要分两层：

- **固定 trace replay**：同一份真实模型提议、同一组签名包、同一事件序列在不同策略下重放，用来测机制本身的增量；
- **live model pilot**：各策略让真实模型独立决定，用来测完整系统的模型可用性、hold 和 token 成本。

如果只做 live model，各组模型偶然提出不同决定，就无法判断结果是模型差异还是机制差异；如果只做 replay，又无法知道真实模型是否能使用恢复协议。两层都需要，但目的不同。

### 4. 动态真值和责任标签

benchmark 不能只有一个最终 `allowed=true/false` 标签。它需要像一部逐帧的监控录像，在每个事件之后记录：

- 哪些 root 和 derived claim 在该时刻有效、撤销或未知；
- 哪些组织已经正式收到声明或撤销；
- 哪些组织的 Agent 已经在输入中看到声明；
- 哪些动作依赖哪些父声明；
- 哪些 branch 应当冻结，哪些无关 branch 可以继续；
- 哪个组织承担发布、转发、登记、重建或使用的协议义务。

责任输出也要分层：

1. **provenance localization**：能否定位声明来源和传播路径；
2. **protocol duty violation**：是否有签名事件证明某组织在收到明确通知后仍使用旧声明，或用撤销父声明生成派生声明；
3. **causal/legal blame**：是否足以判定事实错误、恶意意图、损失因果和责任比例。

当前系统能稳定做第一层，能在证据充分时做第二层，第三层仍应保持 `undetermined`，除非 benchmark 明确定义通知时限、业务义务和损失模型。正确地不下结论本身是审计指标，不是失败行。

### 5. Benchmark 主指标

当前报告同时回答四个问题，而不是只报最终 unsafe rate：

- **错误走了多远**：正式接受组织数、模型暴露组织数、引用/转发次数、最大传播跳数、fan-out 分支数；
- **错误造成了什么**：程序拦截数、模型自行 hold 数、最终不安全完成数、结果未知数、无关任务被错误阻断数；
- **错误之后能否修复**：replacement source、offer 验证、coordinator 登记、derived rebuild、receiver redecision、最终恢复和无关任务继续率；
- **审计是否说得恰当**：来源定位准确率、协议违约检出率、无证据时 abstain 率、错误指控率、事件篡改/缺失发现率。

成本作为约束单列：模型 API attempts、provider responses、known/unknown token、verification queries、recovery round 数和传输消息数。当前数据没有证明 dependency 的总体成本优势，benchmark 必须让安全性和正常完成能力先可比较，再讨论成本。

## Benchmark 的实现难点：难在哪里，为什么难

代码工作量是中等，且大部分基础设施已经存在；研究工程难度偏高，难点集中在以下几处。

### 难点一：同一件事在不同组织眼里不是同一张地图

中心化模拟器可以直接查看全局状态，然后说“这个声明已经撤销”。跨组织系统不能这样做：carrier 知道自己的撤销，coordinator 可能只知道新来源已经收到，receiver 可能只知道某次查询返回 revoked，另一个分支可能什么都不知道。

因此 message bus 必须为每个组织维护不同的可见事件流和本地 claim store。任何把全局 truth 直接塞给 Agent 的便利写法都会让 benchmark 失去研究意义。这个难点要求先设计事件快照，再写网络代码。

### 难点二：时间顺序就是安全语义

撤销在消息传播前发生、传播后发生、只送达一条分支、送达后又收到旧包，这几种情况不能用一个最终状态替代。它们决定了某个组织是在“没有机会知道”时使用，还是在“已经收到通知”后仍使用。

因此每个消息和动作都必须有序号、前驱 hash、发送者、接收者、批次和阶段；评估器根据事件序列重放，而不是只读取最后一个 JSON 字段。

### 难点三：要把机制效果和模型偶然性分开

真实模型可能在看到错误时自己 hold，也可能在证据完整时误解 schema。若策略之间各自重新调用模型，unsafe rate 的差异不能直接归因于机制；若把所有模型决定固定，又测不到恢复输入对真实模型可用性的影响。

所以必须同时保存 live trace 和 replay trace，并明确两种结果不能混成一个样本量。这是 benchmark 设计中最容易被忽略、却直接决定结论可信度的地方。

### 难点四：责任标签不能由结果倒推

如果最终发生了不安全动作，不能反过来说发布者一定有错；如果最终没有发生动作，也不能说接收方一定尽职。需要先声明每个组织的协议义务和通知条件，再由独立审计器检查签名事件是否满足这些条件。

形象地说，审计员可以证明“这封挂号信在 10:03 被 receiver 签收，10:05 receiver 仍把旧编号写进申请单”；审计员不能仅凭这两枚邮戳证明原寄件人故意造假，或证明造成了多少经济损失。benchmark 要把这两个层次分开计分。

### 难点五：故障越多，越容易把安全和拒绝混为一谈

全部 hold 看起来很安全，却没有完成协作任务；把无关分支一起冻结又损害网络可用性；把 `EFFECT_UNKNOWN` 当成普通失败并自动重试可能造成重复副作用。

因此 benchmark 必须同时有高风险动作和低风险无关任务，并把安全完成、合理 hold、错误拦截、过度阻断、结果未知和恢复失败分别记账。当前 `run_batch`、action contract 和恢复接口已经提供这些分类，benchmark 主要需要扩展拓扑和真值，而不是重新发明动作门禁。

## 已完成的 Benchmark 工作包与剩余难点

第一版 benchmark 已按以下五个工作包落地：

1. **协议和场景生成器**：用配置描述节点、边、私有权威、声明图、故障注入位置、通知规则和预期义务；每次生成保存 fixture manifest 和动态 truth。
2. **确定性 message bus**：实现 delay/drop/duplicate/reorder/fan-out，给每个组织生成独立可见事件和本地状态；所有传输行为可用固定 seed 重放。
3. **策略适配层**：把 unmediated、simple gate、dependency、verify-all 和 recovery ablation 接入同一事件控制器，保持同一动作合约和同一信息边界。
4. **独立序列评估器**：按事件时刻重建有效声明、通知和义务，计算传播、动作、恢复、责任和成本指标；评估器不能被组织 worker 或模型输入调用。
5. **实验归档和回归套件**：先用 v7 raw trace replay，再用脚本构造边界反例，最后运行小规模真实模型；保存每个原始请求/响应、来源 hash、事件链、truth、metrics、report 和 mechanism case。

尚未完成的是跨物理主机的生产级网络验证。虚拟网络已经回答传播、局部冻结和责任时序问题；物理部署属于下一层验证，还需要单独测试认证、加密、网络失败、持久幂等和远程状态一致性。

## 当前如何判断贡献是否成立

如果在相同模型 trace 下，当前 dependency 相对于 unmediated 和 simple gate：

- 减少错误正式触达、错误引用或不安全动作；
- 在错误分支冻结时保留无关任务完成；
- 能稳定完成受约束恢复；
- 在缺少通知或损失证据时保持低错误指控和适当 `undetermined`；
- 安全和正常完成能力相近时再显示合理成本；

那么可以较有把握地声称贡献来自“跨组织依赖调度 + 局部冻结 + 证据绑定恢复 + 受限追溯”的联合协议。

如果 benchmark 只显示最简单的 revoked gate 已经得到全部安全收益，而 dependency 和 recovery 没有额外增量，结论也应如实收窄为“运行时门禁和证据审计原型”，不把更多接口包装成额外创新。

## 当前停止边界

当前 v7、dispute v1、自然修复入口和安全失败场景均已完成接线与受控验证。下一步是冻结机制、整理论文和限制；新的大规模真实模型调用、扩大付费实验或改变核心研究方向，都应在重新写清具体规模、调用上限、停止规则和待解决不确定性后，再由用户决定。

仓库根目录的 `.git` 已初始化为有效 Git repository，已有 checkpoint `02b8892` 保留接手时的可靠性实验状态；本阶段的 benchmark 代码、原始结果和本总结将在本轮验证后提交新的本地 checkpoint。


## 后续执行补充：离线 benchmark 已接入统一闭环

后续按用户收敛优先级完成了三跳双分支、四类错误（派生错误含两处位置）的离线矩阵，并由该矩阵暴露出v1仅允许单派生重建的限制。新增候选`recovery-frontier-v2`，保留原v1和历史结果。

目前统一闭环入口为`trust_network.benchmark.closed_loop`，36条脚本workflow在同一组织状态和事件链中完成传播、失效、局部冻结和恢复评分；另有追溯标签对照和v7真实历史决定回放。结果见`results/containment_closed_loop_v1_final/report.md`，协议见`BENCHMARK_PROTOCOL_V1.md`。

能够支持的离线增量是多层恢复能力：v2在两条分支完成恢复，原v1失败。尚不能支持v2优于普通notice的真实模型可用性、当前dependency优于强简单门禁的拦截能力，或解决冲突来源/签名事实错误。

## 三跳分叉真实模型 pilot 结果

按 `BENCHMARK_PROTOCOL_V1.md` 完成了有界的 C pilot：只运行 hidden-revoke 条件，三种恢复臂各 2 个 workflow，共 6 个；每条 workflow 最多 6 次模型决定，正式上限为 36 次模型决定和 72 次 provider 尝试。实际使用 27 次模型决定、27 次 provider 尝试，所有已返回决定的 usage 均已知，provider failure 为 0。

|恢复臂|安全完成|不安全完成|两层派生重建|恢复成功|C任务完成|模型 hold/解析拒绝|
|---|---:|---:|---:|---:|---:|---:|
|dependency|0/2|0/2|0/2|0/2|2/2|0/1|
|frontier_v2|1/2|0/2|1/2|1/2|2/2|1/0|
|notice_only|0/2|0/2|1/2|0/2|2/2|2/0|

正向结果是：旧 freight 已沿 source → coordinator → middle → receiver 三跳正式接收；5/6 条 workflow 的有效账单提议在 gate 前被 revoked root 拦截；无关 C 任务 6/6 继续；frontier-v2 有 1 条完整经过新来源、两层派生重建、模型重新决定和再次 fresh gate 的恢复链。

负向结果同样保留：冻结 dependency 在两层任务上按协议记录 `protocol_unsupported`；另 1 条 dependency 初始模型没有提交完整 invoice claims；frontier-v2 的另 1 条和 notice-only 的两条在恢复阶段由模型选择 hold。普通 notice 在固定正确的新事实下没有显示真实模型可用性优势。所有 6 条 workflow 不安全完成为 0，但样本太小，不能外推总体错误率或证明 frontier-v2 优于 notice-only。

完整原始请求、响应、签名状态、事件链、批次审计和完整性清单见 [C pilot report](results/containment_live_pilot_v1/report.md)、[metrics](results/containment_live_pilot_v1/metrics.json) 和 [机制案例](results/containment_live_pilot_v1/mechanism_cases.md)。一次因误把 active 条件加入 live 矩阵而中止的运行保留在 [scope-mismatch archive](results/containment_live_pilot_v1_scope_mismatch_aborted/SCOPE_NOTE.md)，不计入正式样本。

当前最有信息量的下一步是收敛论文主线：把“已撤销错误”的传播/恢复证据、“尚未撤销但相互冲突事实”的补证边界，以及本轮 UNKNOWN、source hold、错误修订的安全失败证据放在同一套指标口径下。恢复阶段的模型可用性继续单独记录，不能用 hold 产生的低错误完成替代恢复成功。新的大规模付费实验或核心方向改变仍需用户决定。


## 2026-09-10：统一L0–L4 benchmark实验交接

已实现独立普通消息L0、累计协议层、三类多跳拓扑、十类场景及单项消融，共210条离线配置；同一节点接口可在持久组织进程中运行。完整代码绑定回归248 passed，其中5个进程等价病例。正式离线矩阵210/210完成，原始manifest及代码绑定验收通过，见`results/layered_v1_offline_final/`。新增MiniMax调用为0。

[实现说明](BENCHMARK_LAYERED_V1.md)记录 L0–L4 接口与限制；最终统一 live 的主结果、消融和追溯投影见 [最终报告](FINAL_UNIFIED_LIVE_BENCHMARK_20260911.md)。结果区分模型 hold、程序阻断、网络失败和恢复停止。


## 2026-09-11：最终统一 L0–L4 live benchmark

最终统一 live 实验完成 300 条主实验和 50 条消融，共 350 项固定计划；344 条有最终结果，6 条保留为 unknown。主矩阵错误完成率由 L0 的 36.2% 降至 L4 的 0%，错误传播交接由 242 降至 0；L4 的真实恢复请求为 10/12，最终恢复为 6/12，另外 4 条在 workflow 预算耗尽时停止。无关任务保留 138/144。

实验过程中发现并修复了模型 claim-ref 契约、瞬时 provider/network 失败和 5 条剩余动作契约异常，并只重跑受影响 workflow。最终非法决定、非法结果、provider failure decision 和 worker error 均为 0；58 次篡改交接签名拒绝属于预期安全门禁。详细结果和图表见 [最终统一 live 报告](FINAL_UNIFIED_LIVE_BENCHMARK_20260911.md) 及 [公开归档](results/final_unified_live_v1_combined_20260911/report.md)。
