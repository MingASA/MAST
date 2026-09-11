# 研究日志：假设、证据、反思和下一步

目标是提高真实跨组织Agent协作的正确性与可恢复性，并留下可检测、可追责的证据。工程通过、离线故障注入有效、真实工作流收益和一般化结论是不同层级，不互相替代。

## 2026-09-10：workflow v1 当前代码复现、live 扩大与配对 tape 重放

在争议恢复 pilot 之后，按“冻结核心机制、先观察实验结果和原因”的计划完成了当前代码的统一 workflow benchmark 复现，并进行有界真实模型扩大实验。`results/workflow_v1_current_reproduction_20260910/` 运行 11 条件 × 8 臂共 88 条 scripted memory workflow，0 次模型调用，445 个归档文件完整性通过；`results/workflow_v1_current_process_intermediate_20260910/` 对 root_gate 与 dependency_push 做 2 条实际进程回放，均无 worker error。离线/进程结果仍显示中间撤销时 root_gate 错误完成 2/4，完整依赖 0/4，后者恢复 2/2。

真实 MiniMax-M3 live 归档包括：中间撤销三臂3条、事实缺口 signed_false/conflicting_sources 六条、active四臂4条、中间撤销扩大四臂4条，以及4条独立 autonomous intermediate sample；合计21条 workflow、345次模型调用、346次 provider 尝试、1,250,582 known tokens、6次未知 usage。真实进程 worker error 为0。live 负结果是模型 hold/无效引用使部分任务没有动作机会；`signed_false` 没有 consumer detection，说明 freshness/signature 仍不能证明隐藏事实正确。中间撤销 natural autonomous 样本出现错误完成，但同一提议的五臂固定重放把该增量分离出来：4条 tape、每臂16个任务中 autonomous/root_gate 各错误完成2个，dependency/dependency_push/verify_all均错误完成0个，各阻断6个错误动作。

结果解释、分母、原因分析和所有 raw 目录见 [workflow v1 阶段分析](results/workflow_v1_experiment_analysis_20260910.md)。结论是核心依赖门禁/局部冻结路径已足够冻结；下一研究问题是独立权威事实补证、公开冲突未解决状态和恢复阶段自然模型行为，不再盲目重复同一中间撤销矩阵。

## 2026-09-07：为什么两批真实调用没有给出增量收益

**原假设H1：** 当Agent准备放行不可靠结果时，运行时查证/证据协议能以合理成本阻止错误。它包含两个不同问题：真实流程有多少需要干预的提议，以及协议遇到这些提议时能否改善结果。

第四轮36个run中，Risk-Aware没有非allow干预，模型主动查证承担了阻断；Verify-All则有4次程序查证，其中2次阻止未授权pass。Risk-Aware 0/11不安全完成、成本24，相比Verify-All 0/11、成本33，并不证明前者的增量作用。不同模型采样和提前升级也是成本差异来源。已有低风险漏放离线反例继续保留。

第五轮6个真实网关run中，三组均完成已授权订单并由模型查证后停止未授权订单，协议没有触发修正。此批证明接口能运行，不能证明协议改善了实际结果。每条件只有1次，不能估计稳定错误率或等效性。

**当前解释（待后续实验检验）：** 单一授权事实容易被模型识别为必须查证；共用prompt也明确要求正式授权依据。模型已经按预期完成检查，使程序门禁几乎没有额外干预机会。较长流程中的条件依赖、版本变化、组织承诺边界尚未被充分暴露。不能把这个解释当成已证明的因果机制，也不能为得到正结果故意弱化baseline。

将按日志计算：各组织pass/request/reject/escalate次数，pass时已有证据状态，不符合结构化动作约束的pass次数，程序实际介入次数。数据见results/research/v5_opportunities.json。只有观测到需要干预的提议，才能进一步区分干预后修正成功、误阻断、无效补证和漏放。该条件分析是机制诊断，不替代以所有run为分母的主效应。

## 本轮改进为什么不是简单“让场景更难”

新案例引入供应、买方接受和物流履约三个不同的必要承诺。Agent确实需要沟通并选择方案，程序不直接求出或指定最佳方案。2100成本的早到分批方案和900成本的整批方案均可满足硬条件，不同买方偏好可以产生不同合理选择。

研究焦点由“查一个未知审批布尔值”扩展为“信息转述、计划修改和组织承诺能否保持一致”。这对应真实协作网络中的错误途径，而不是随机增加干扰。具体数据与约束预先保存在examples/negotiation_v6和SCENARIO_v6.md；仍为合成场景，不能据此声称代表真实企业分布。

**H2：** 同一业务方案中，按声明依赖绑定的组织承诺能降低版本错配和无证据执行，同时通过局部重验证保留正常完成率。

已实现基础证据：修改运输报价只使carrier/buyer承诺失效，供应承诺可以复用；旧否认不会因过期被洗掉；执行入口在重启后拒绝同一交易的不同计划重复执行。5项离线回归通过。尚未把这些能力接入真实协商流程，不能提前接受H2。

## 后续实验约束

1. 先运行无故障的真实多组织协商，证明任务有用且能完成，记录Agent选择了什么及其依据。
2. 将自然错误与预注册故障注入分开。注入用于测可恢复性及协议干预，不估计模型自然错误率；列明注入位置、时点、范围和对所有policy是否相同。
3. baseline与机制组共享模型、业务prompt、组织信息、工具和预算。若比较整个协议而非单个policy，明确处理差异，不冒称仅改变风险公式。
4. 主指标保留全部run口径的不安全执行和错误声明传播，补充正常完成率、方案质量、费用与故障状态；不要只报告成功干预子集。
5. 保留不利情形：已有证据足够时机制可能无收益；错误权威、范围遗漏或网关被绕过可能仍失败；额外修正可能增加token/延迟。
6. 不以更换prompt或添加硬编码规则后同一案例通过作为研究终点。记录改动，冻结实验版本，再测新的案例/重复条件；在有清楚干预机会仍无收益时，修订或放弃相应假设。

## 需要持续检验的边界

### V19不扩大传播收益结论

完整依赖可见后，金额错误被模型自主hold，遗漏依赖分支模型调用失败，未获得新的再传播证据。接收前门禁阻断两个受控错误，正常两跳均完成。5次成功调用/4802token另有失败未知用量；失败不计拒绝。模型解释出现分/元混淆，但结构化fact正确，说明保护边界仅覆盖核验声明，不覆盖自由说明。详见results/propagation_v19_visible_dependencies/report.md。

### 传播与追溯Demo已经可查看

claim_v14_active_check/demo.html将真实两跳交接、被动等待通知的失败、主动确认阻断和无关分支继续执行放在同一视图，并可展开签名证据索引。生成前重跑组织事件链审计，5个使用事件通过重建。此为历史证据查看器，不自动发起模型或业务操作；尚未进行浏览器视觉验收。README更新主线入口，历史成本与数学实验仍保留，但不替代安全与合理追溯目标。

### V11反提案获得两条可追溯恢复轨迹

费率变化4run完成，阶段组2/2安全完成，两次均采用程序生成的有签名报价来源的价格候选，每条4查询/5调用；全验证组2次初始自主拒绝，未触发验证，因此不可归因于全验证。总16调用/15588token。下一步应固定错误提议+否认前缀，配对比较修正分支，解决自然采样使机制机会不匹配的问题。见results/counterproposal_v11_rate/report.md。

### V9动态试运行首次观察到实际恢复与查询节省

3条真实MiniMax+受控私有费率变化运行完成。Autonomous旧价不安全提交；full与selective都收到物流否认、取得新报价、第二轮安全完成。查证6对4，但token4651对5231，选择性组更多；模型调用均5。全批13调用/12522token。查询增量有实际干预轨迹支撑，总成本优势未成立，且样本每组仅1。下一步需要dependency-only消融及多方变化反例，不能只重复有利单一变化。见results/rate_v9_pilot/report.md。

### V8调度真实消融没有建立归因

6条自然MiniMax运行结束，两组均安全完成3/3。普通依赖复用出现1次否认，11查询/10调用/9247token；短路组无否认，9查询/9调用/7574token。虽然均值好看，新调度没有实际干预，因此不能称为其收益。19调用/16821token完整保留。停止继续重复静态案例找正向差异，下一步应围绕业务信息依赖和明确外部状态变化设计核心实验，见results/selective_v8_ablation/report.md。

### 动态资源反例与本地原子预留

修复后真实HTTP重跑完成并通过新增独立审计（resource_v7_minimax_audited）：3调用/2521 token/8 HTTP，运费2100，事后三方硬约束均满足。三次尝试合计9调用/7590 token，失败日志保留。下一阶段范围收敛见 RESEARCH_NEXT_SELECTIVE.md：资源正确性作为共同执行基础，核心重新聚焦公平比较下证据依赖复用的成本收益，不把传统预留机制扩展当作研究目标达成。

新增独立资源审计时，真实HTTP pilot未通过模型输入摘要检查：messages共享可变引用导致历史输入被修改。报告签名有效不足以证明逐事件输入真实。已修复HTTP发送前JSON冻结，保留原始失败审计说明；之前的“端到端接通”不升级为完整审计成功。新提交决定增加签名时间，用于事后批准有效期检查，历史决定无此字段不追补。此回归提示新运行器应复用成熟消息记录边界，而不是复制简化版本。

固定真实计划的受控双订单对照完成（results/resource_v7_contention/report.md）：容量一单时，静态全查证不安全1/2、预留0/2，两者安全完成均1/2，调用6/7；容量两单时均安全完成2/2，调用6/10。无新增模型调用，不将新交易的测试签名当作自然模型行为。该结果说明正确性增量及确定的调用成本，也说明不能把现成两阶段提交或比无库存账本的基线更好冒充整体研究创新。

组织服务新增资源准备/决定操作，完成9次真实HTTP请求的本机跨进程验收（results/resource_v7_network_smoke/report.json），含部分终止、持久化恢复、重复请求及容量复用。零模型调用；不把受控终止验收当作真实Agent动态收益。下一步仍需接入买方真实执行计划和提交路径。

后续补充 resource_protocol.py：签名准备票据、持久化唯一决定、组织执行确认和 recovery_pending 状态。6项本地/协议测试通过；其中部分提交后恢复到完成，未用到期自动释放破坏准备承诺。这是经典两阶段提交基础，不是新的创新声明；诚实协调服务、阻塞等待、进程内故障测试以及尚未接入真实runner的限制明确记录在 RESEARCH_v7_RESERVATIONS.md。

确认 V6 静态 owner_check 会批准竞争同一库存/运力的两个不同订单，现有签名和单交易幂等性不解决超分配。新增 reservations.py，以组织本地 SQLite 原子检查/预留，并区分 held、committed、released、expired。三个针对性测试通过，包含真实线程并发争抢和重启后的资源占用。尚未接入跨组织 workflow，不能声称完整修复或自然模型实验收益；下一步必须处理签名预留、部分提交与恢复。设计及边界记录于 RESEARCH_v7_RESERVATIONS.md。

### 三协议主对照：有限的正向结果与新的反思

27个预注册自然输出run完成，82调用/69391 token，257事件核验通过。Autonomous不安全提交1/9，full/dependency均0/9；已授权安全完成5/6、5/6、6/6。查询0/15/18，不能声称dependency本批更便宜。

保护组未出现不合格propose，因此本批组间差异仍混有模型采样差异。所有组都没有选用可用的verify动作；baseline不是被剥夺工具。结合早先真实拒绝/修正轨迹及固定轨迹绑定重放，协议机制有可核对证据，但尚不足以接受强一般化收益结论。详见results/negotiation_v6_protocol_comparison/report.md。

重要汇报错误：中途曾把completed当作安全，误报首轮无不安全提交；完整评估发现baseline把road费用记0仍提交。今后进度也必须以事后约束评估区分完成与安全完成，而非等待最终报告才修正。

下一优先级转向动态网络状态与资源竞争。继续反复静态报价题可能主要测LLM计算/采样；资源快照变化、承诺失效和重复资源分配更直接检验跨组织协议，但需要真正的组织服务状态和明确注入标签，不可以把受控事件伪装成自然错误率。

### 绑定粒度真实对照与主对照准备

预注册12个绑定对照run全部正常结束，146事件核验通过；full/dependency均无不安全提交、已授权完成均4/4。查询15/13，token16051/16800。真实查询低13.33%但token高4.67%，轨迹不同，不能把全部差异归因于协议。

固定全部12条真实轨迹重放，原条件逐run查询数完全复现；相同轨迹全用full为30次，全用dependency为27次，收益集中于2条修正轨迹。该结果支持局部复用机制，不是新的完整模型反事实或总体可靠性增量。见results/negotiation_v6_binding_comparison/report.md。

审计重建还发现早期events中的request持有可变messages引用，后续追加可能改变已记录输入。运行时发送是当时序列化的数据，没有据此认定模型看到了未来消息；但旧pilot日志不足以证明严格输入控制。新版本冻结输入副本、签署input_hash，独立验证计数与提交。旧日志不被伪装成新的审计等级。

接下来按EXPERIMENT_v6_PROTOCOLS.md运行27个三协议主对照。baseline保留同样的可选verify工具，保护协议只增加强制执行门禁/证据绑定。业务接口在各组同时更新，不拿旧轮结果直接横比。

### H2的第一条真实轨迹（尚非对照结论）

第六轮可行性试运行3案例、10调用、8203 token。省运费案例出现真实错误：买方模型将bulk运输费用记为0，carrier程序出具否认，模型第二份计划修正为900并完成。修改只影响carrier/buyer范围，供应承诺复用，总查询5次。未批准案例由买方直接拒绝，复产案例直接完成。无故障注入。

因此“真实流程完全没有干预机会”的解释只适用于先前单一授权试运行，不能推广到新多条件协作。H2得到一条机制实际恢复的轨迹支持，但还没有固定对照和重复条件，不能接受总体收益结论。

同时出现反例：省运费案例选了2400而非已知可行900方案；复产案例完整私有资源可达2100但只选到2400，carrier遗漏了road选项。协议修正了报价正确性，没有解决偏好误读或有价值信息未披露。后续分别测硬约束违反、局部恢复、信息覆盖和方案质量，不把最优性差距与不安全执行混为一谈。详细见results/negotiation_v6_pilot/report.md。

签名只证明组织签过什么，不证明事实永远正确；私有资源承诺需要有效期、撤销和最终执行的资源锁定。当前SQLite模拟提交的幂等性不代表外部运输公司已加入原子事务。单机HTTP验收也不等于多个物理设备/行政域已经部署。这些限制不得从最终报告中消失。


### 2026-09-09：closure v3 机制闭环与研究收敛

本轮先解决已被发行者发现并撤回的错误，不扩展到发行者尚未知晓的事实错误。根状态不能代表中间声明状态，因此新增 dependency_closure / verify_all_closure，保留旧根查证策略。中间负面状态携带可验证祖先撤销，避免把整个后代永久标为撤销。

恢复复用 frontier，v3 允许从任意原发行者的合法修订种子出发，绑定失败 batch、精确任务和旧新身份，并由原发行者逐层重建。单分支撤销反例只恢复一分支；共享中间撤销反例恢复两分支，无关订单继续。追溯使用本组织签名 predecessor 链，修正仅凭 controller 顺序或其他消费者通知推断违规的风险。

验收：158 passed，包含实际持久化 worker 接口；零付费调用。新矩阵入口提供35条脚本 workflow，留给实验代理正式执行。完整结果尚不存在，不把测试比例当成总体实验收益。

研究反思：严格完整依赖检查与 Verify-All closure 在默认配置下等价，不应虚构成本优势。另设放宽低风险转发的配置，专门测量少查证是否让错误传播更远。正常证据下 notice-only 可能同样恢复，证据绑定的直接价值应由非法恢复包的接受差异检验；共享派生规则的拦截不能重复算成恢复创新。详见 MECHANISM_CLOSURE_V3.md、TASK_EXPERIMENTS_CLOSURE_V3.md。


### 2026-09-09：主动通知与恢复失效前沿

进一步补齐两个不依赖实验估计的缺口：组织发现撤销后，按已登记交接的完整依赖反向索引，仅向相关直接消费者发送原始撤销证明；消费者登记后沿自己的本地路径继续传播。消息有签收、确定性去重、持久化outbox和有界重试。ACK丢失不删除路径，不因无ACK判定失职。worker暴露完整签名事件序列，避免队列事件造成追溯链缺口。

v3 frontier额外区分签名有效与当前可用的完成证据。二次撤销令受影响映射失效并要求重规划，无关完成成果保留。这是恢复期间持续控制失效范围，尚不能证明真实模型更善于选择新事实。

验收：169项全量测试通过；最后事件导出调整后11项相关测试通过。零新付费调用。已交接固定提议下的及时/迟到通知比较；不默认把通知投递插到所有动作之前来制造收益。只有push+closure保留晚到通知时的查询防线，push-only仅用作失败边界诊断。研究增量应区分主动传播负面证据、查询覆盖和局部恢复，不重复计入共享检查收益。


### 2026-09-09：统一跨组织 workflow benchmark v1 落地与负结果保留

将此前分散的查证、交接通知、恢复前沿与追溯接到一个七组织、三跳双分支、双订单工作流。脚本/tape/live 共用阶段与 RPC；进程后端使用实际 claim_worker，公开输入不带真值，source 私有事实由独立评分器使用。权威 source/buyer 本轮仍为服务，五个下游角色可由模型驱动；物理网络与生产付款尚未接入。

完成 88 条离线脚本工作流、2 条独立进程校准；旧 v7 的 151 原始文件校验、4 流程 6 批次重放一致。交接时 178 tests passed，接口修复后为 180 passed；离线新增付费模型调用 0。固定 tape 缺失后续 approve 时 hold；签名交接、模型展示/引用、实际 gate 结果和独立 truth 评分区分记录。

构造条件汇总中 root_gate 错误完成 12/44，完整依赖 4/44；剩余错误来自冲突和签名事实错误。与 simple_dependency_gate/Verify-All 完整依赖覆盖等价，不能把根门禁弱点充作复杂协议超越强门禁的证据。push 查询总数由 399 到 387，约 3% 的节省；中间撤销检测由 2 tick 到 1 tick，迟到通知不获益。selective 查询 168，本矩阵安全相同，但没有普遍可靠性保证。

恢复消融多完成 1 个任务，但其恢复包绑定其他任务；金额正确与协议合规分开计数。绑定前沿拒绝该包，并保留另一分支恢复。这支持证据绑定边界，不证明法律追责能力。单分支自撤销、结构派生错误被共享检查挡住，所有臂相同，明确不计创新收益。

研究重点应进一步指向“来源尚未撤销的错误”：独立权威补证与冲突解决条件，而不继续增加等价 freshness 门禁。接下来交接 3 条真实模型 pilot 验证接口可用性；该 pilot 已运行并另存归档，未经用户决定不自动重跑、不扩矩阵。详见 BENCHMARK_WORKFLOW_V1.md 和 TASK_EXPERIMENTS_WORKFLOW_V1.md。

### 2026-09-09：workflow v1 首个 live pilot 暴露故障前置状态断裂

按统一 workflow v1 任务书运行 `intermediate_retraction` 的 `root_gate`、`dependency`、`dependency_push` 各一次。三条均使用真实 `claim_worker` 进程和 live MiniMax 决定，共 54 次模型调用、103,570 个已知 token、provider failure 0；原始 trace、truth、audit、metrics、decision tape 和完整性清单保存在 `results/workflow_v1_live_pilot_01/`。

三条运行都在 tick 10 尝试撤销 coordinator 的中间 claim，但模型没有产生可由 coordinator worker 登记的有效派生声明。旧调度路径用离线 fixture fallback 继续构造撤销目标，真实 worker 因本地不存在该 claim 而拒绝，三条都记录 `fault_not_realized`，`truth.faults=[]`。因此 0 unsafe、0 propagation、0 recovery 只说明故障没有发生，不能作为机制比较结果；模型高 hold 率和派生 fact 不符合 relay 精确复制规则也是可复现的接口发现。运行后审阅见 `results/workflow_v1_live_pilot_01/POSTMORTEM.md`。

随后修复 live/fixed-tape 路径：未被真实 worker 接受的派生声明不再回退为 fixture，后续阶段明确记录未实现状态；统一模型接口补充 relay fact 必须逐字复制父声明的契约。修复后的全量测试为 180 passed。按照任务书，首次三条完成后不自动补跑；下一次付费运行需由用户决定。


### 2026-09-09：pilot 01 的失败不是可靠性成功，先修执行接口

复核原始模型回复发现：未提供明确 claim digest 索引，模型错把 bundle_hash 当 ID；自由派生 fact 出现串单和改字段，被共享 relay 检查拒绝，后续 hold 形成连锁停滞。前一代理已移除未登记 fixture fallback；本轮进一步加入证据索引和 relay-reference-v1，让明确 proceed 通过 fact_ref 选择父证据，程序在本地解析并再次验证。普通派生和受约束恢复共用接口，旧错误 fact 不自动修复。此改动是执行接口设计，不是事实真实性算法或已证实模型收益。

评分新增故障实现和故障后动作机会，completed 不代表可比较；旧 pilot 独立复评分仍三臂 fault_not_realized。原 overfreeze 混入上游未完成，现分最终程序阻断与所有原因未完成；旧归档不改。下一步先交接 1 条 active live 校准，成功后再由用户决定是否开中间撤销三臂，不自动扩实验。本轮无新付费调用。见 REVIEW_WORKFLOW_PILOT01_REFERENCE_V1.md。

本轮验收：183 tests passed；实际进程脚本核验故障发生、4/4 安全完成、2 次引用绑定恢复，worker error 0、付费调用 0。该结果不代表引用接口已提高真实模型成功率。


### 2026-09-09：类型化声明引用校准与三臂中间撤销 live 结果

active/root_gate 的第一条付费校准仍暴露长 digest 转抄错误：真实派生 A 已登记，但模型把后续 forward 的 ID 末位写错；第二条校准确认 forward 可以成功，却又暴露 derive 的 `claims` 没有按新接口解析。于是把 `claim_refs` 统一到 derive、forward、verify、approve，并允许 `fact_ref` 选择同一 `claim_id_index` 的本地 token。引用 token 是模型明确选择的 typed pointer；无效 token、重复 token、同时提交旧 claims 都拒绝，不由 worker 自动纠正。全量测试为 185 passed。

第三条 active 校准完成 6 个派生阶段和 4 个中间转交，全部由真实 process worker 登记，worker error 0；有 22 次模型调用、22 次 provider attempt、106341 个已知 token。模型仍有 2 个 hold、1 个无效后续动作和 2 个 C 任务未完成，所以该校准只证明接口可用，不证明正常业务完成率。

随后按已授权范围运行 `intermediate_retraction` 的 `root_gate`、`dependency`、`dependency_push` 各一条。三臂都在 tick 10 真实撤销 coordinator 的 A 中间声明，原始归档在 `results/workflow_reference_live_intermediate_02/`，运行后复核在其 `POSTMORTEM.md`。root_gate 的错误证据继续到两个下游组织、两个分支，最大相对距离 2；dependency 在 tick 12 拦住两条错误依赖动作；dependency_push 的通知在 tick 11 让两个消费者发现，提前于普通依赖一 tick。

这次三臂均有真实故障；root_gate 与 dependency 都有故障后 execute 提议，containment 可评估。dependency_push 因通知到达后模型没有再形成故障后 execute 提议，标记 `no_post_fault_action_opportunity`，零错误完成不计作 containment 证据。三臂最终错误账单均为 0，但 root_gate 也没有错误完成，原因是模型 hold/无效动作造成的样本不足；因此结果支持“完整依赖能阻断已撤销中间证据”和“push 提前发现”，不支持真实模型错误率已下降。总计 57 次模型调用、58 次 provider attempt、232059 个已知 token，worker error 0，归档完整性核对通过。下一步停止重复该静态 live 条件，转向签名有效但事实错误的权威补证和冲突解决。


### 2026-09-09：真实中间撤销出现防传播增量，避免按模型动作筛样

审阅 ee7a12d：root gate 的错误证据传至两个接收组织，完整依赖阻断两次明确 execute。push 的两个 middle 在撤销到达后 hold，并在理由中引用撤销；这是可观察的反馈行为，不可因不存在 execute 就排除整条故障试验。新评分区分 fault_trial_evaluable 与 hard_gate_evaluable，legacy containment_evaluable 仅保留原硬门禁口径；不把事后是否提出动作当作全流程纳入条件。该单次 live 非配对因果证明，unsafe 全零仍不足以说明最终安全性改善。

claim_refs 接入后旧评分仍只读 draft.claims，已补按归档 public_input.claim_id_index 精确解析引用，不读 reason 猜测。复评分另存 workflow_intermediate02_review，当前仓库 integrity 清单的84个文件校验通过（旧 POSTMORTEM 记载运行时104个，不混用两个计数），不改旧归档。下一阶段定义有范围的独立结算依据补证和 dispute，不把 active freshness 当真实性。规格见 NEXT_FACT_EVIDENCE_PROTOCOL.md，尚未实现该新协议或启动付费试验。


### 事实补证 v1：从发行者未撤销推进到独立业务依据

新增 settlement_basis_v1 签名请求/答复，绑定声明、动作、批次、nonce、权威、时效和台账版本。runtime 在 freshness 后、effect 前强制检查；两个真实 worker 动作入口均接通。矛盾进入持久化本地 fact_disputes，不伪造 revoke；独立审计另行固定权威信任映射。

16 条脚本矩阵加一条 process 核验：公开一致的未确认依据，closure-only/conflict-triggered 各无依据完成2/4；verify-all/selective均0，但错误触达分别1与5组织，事实查询20与12。这揭示少查的传播代价，不能只报最终零错误。正常任务均4/4完成，权威UNKNOWN强检查保留C并暂停A。未运行MiniMax，未解决任意真实性、权威欺骗、远端状态与effect竞态。

下一步先接独立 dispute 传播与受证据约束的修订恢复，暂不启动付费实验。FACT_EVIDENCE_V1.md 清楚区分本轮已完成的门禁/本地争议和仍未完成的跨组织闭环。

本轮最终验收192 passed，原始trace、独立audit与归档SHA256已保存。


### 争议传播与确认恢复：从局部门禁到事后收敛

复用handoff_index、notification outbox/receipt/ACK/pump，以独立dependency-dispute-v1消息传播原权威否认证据。每跳验证本地信任scope、原请求/答复和相关交接；网关用disputed前缀标识局部阻断，不伪造成原发行者revoke。负面证据不会随证书过期自动恢复旧claim。

新增明确发行者修订接口：暂存候选，新claim获独立确认后才提交自己签署的撤销与revision offer；失败不部分撤销。fact_resolution绑定旧争议、修订意图、精确新claim和确认答复，接入原closure v3及frontier。batch始终保存已有争议，即便本组织不主动查事实，也不能在后续恢复时丢掉确认约束。

内存与真实process脚本核验均为4个下游签收，A两分支冻结、C两分支继续、A两分支确认重建后完成。195 tests passed，零新付费调用。修订金额为脚本明确提供，不冒称LLM推断或真实模型恢复收益。下一步应停止继续扩机制，按TASK_EXPERIMENTS_DISPUTE_V1.md补薄live调度并小规模验证，保留模型hold和无效阶段。


### 2026-09-10：争议传播与确认恢复 live pilot

按 `TASK_EXPERIMENTS_DISPUTE_V1.md` 补齐 `trust_network.benchmark.dispute_live` 薄适配器，复用真实 `ProcessBackend`、`Workflow.Decisions`、claim_refs/fact_ref、原始 provider trace 和同一 28 决策/56 provider 尝试硬上限。运行了五条小规模 MiniMax-M3 流程，目录为 `results/dispute_live_pilot_v1_01` 至 `v1_05`，总解释见 `results/dispute_live_pilot_v1_summary.md`。

第一条在进入 provider 前暴露授权 packet 被误当 claim ID 的适配器错误，原始失败保留；第二条自然决策得到 A 两分支 hold、C 两分支完成，source 主动提出125并获确认；第三条保留安全 hold和一次 provider timeout；第四条真实验证 A 的 `approve` 候选被 runtime 返回 `REQUEST_EVIDENCE`，并完成两封恢复信封和四个重建包，但最终模型因未看到签名确认而 hold；补入公开 revision offer 的独立确认后，第五条完成两条 A 分支的完整恢复闭环。四个通知均取得签收并通过独立审计；source 的新事实来自 private dossier，controller 未代填；C 的 hold 样本未被改写为程序过冻。

正向结论是争议路由、局部阻断、来源模型修订、独立确认、逐层 `fact_ref` 重建和恢复后再门禁已在真实 process worker 上串通。负向结论是自然模型可能直接 hold、provider 可能 timeout，且一次完整恢复依赖明确的候选提交探针；这不能作为自然恢复率或四策略效果统计。五个归档完整性核对通过，模型输入未包含 evaluator truth 或 buyer 私有台账。全量回归为 `198 passed`。

下一步冻结该机制版本，先做固定前置状态下的 benchmark 回放和少量有针对性的自然负向场景；不把 probe 样本混入自然成功率，也不因这次闭环扩大付费矩阵。


### 2026-09-10：核实配对增量，转向自然修复入口

核实四份真实tape五臂重放：autonomous/root_gate各2/16错误完成，三个完整依赖臂各0/16、拦6次错误动作。任务相关且tape不含恢复阶段，不称总体错误率或自主恢复率。21条live原始metrics的阻断合计5（原报告写3），有6次usage未知，1250582仅为已知token。

已有事实补证四策略矩阵生成PNG/PDF/SVG三指标图，未启动新实验；不因旧signed_false没有启用fact_policy就重复建设已有权威门禁。争议自然pilot揭示更重要的可用性断点：合理hold不会产生blocked batch，因而不能发起恢复。下一步只补显式request_recovery的无副作用入口，沿现有确认/重建闭环运行，不能把hold偷偷变成approve。详见REVIEW_EXPERIMENTS_20260910.md。


### 2026-09-10：自然修复入口扩大 live 实验完成

按上一条复核提出的入口规格，在 `dispute_live.py` 中加入独立 `request_recovery` 阶段。该阶段要求模型精确绑定原任务、按顺序引用本地 `claim_refs` 和已登记争议；controller 只创建 `intent=verify` 的恢复依据，明确记录 `business_effect=false`。没有把自然 hold 改成失败的 approve，也没有改变已有签名、权威确认或 frontier 规则。seed 参数只用于生成独立 workflow ID，并写入 manifest。

先跑 v1_06 诊断 pilot：两条 A 都提交了无副作用修复请求，source 修订确认成功，4/4 派生声明重建成功，但旧恢复上下文下最终 receiver 两次 hold。补入独立确认、envelope/task 绑定和 frontier 完成状态后，完成 v1_07–v1_18 共12条自然 workflow（24个A分支、24个无关C分支）。A 初始 hold 为24/24；修复请求21/24；进入恢复20/24；恢复重建40/40；最终A完成18/20个已进入恢复的分支，另2个在最终动作阶段 hold。source 11/12提出并获确认，C完成22/24，另外两次是模型自己的 hold。没有unsafe初始完成、无效动作、worker error或批次审计错误；48/48争议通知签收审计通过。

后12条使用156次模型决定、159次provider尝试、1136895个已知token，未知usage为0；连同v1_06为170/173和1238668个已知token。13条新归档完整性哈希全部匹配；独立扫描170个模型调用文件、173次provider尝试，没有发现evaluator truth或buyer私有台账进入provider请求。原始目录与汇总报告保留在 `results/dispute_live_pilot_v1_06_natural_repair_20260910`、`v1_07`–`v1_18` 和 `results/dispute_live_repair_entry_analysis_20260910/`。

结论分两层：机制层正向，显式修复入口让安全 hold 可以进入受绑定恢复，且所有到达重建阶段的证据包都通过；模型层仍有自然停机，故18/24不能当作一般恢复率，0/24 unsafe也不能当作错误率改善。主要剩余原因是模型在请求阶段混淆任务 token 与争议根 ID、source 在个别运行中等待额外澄清，以及最终动作对 `business_execution_authorized=false`/fresh check 语义过度保守。下一步转向 UNKNOWN、source hold、错误修订和错误绑定的负向场景，验证无法恢复时的局部冻结和可追溯性。


### 2026-09-10：安全失败场景 live 与离线负向控制完成

按 `TASK_EXPERIMENTS_DISPUTE_V1.md` 的优先顺序，先新增并运行无付费的 `trust_network.benchmark.dispute_failure`。6个离线场景中，authority `UNKNOWN` 返回 `REQUEST_EVIDENCE` 且无业务结果；来源缺失候选、权威否认错误修订、错误恢复任务绑定、过期确认和跨提议重放5个程序拒绝均实际发生，5个异常拒绝前后网关状态保持不变。完整逐例输入、签名候选、错误和摘要保存在 `results/dispute_safety_negative_offline_20260910/`。

随后运行三条MiniMax-M3 + ProcessBackend live流程，目录为 `results/dispute_safety_live_pilot_20260910/authority_unknown`、`source_hold` 和 `wrong_revision`。共21次模型决定、21次provider尝试、116985个已知token、0次未知usage；UNKNOWN场景的A动作均被门禁停在REQUEST_EVIDENCE，source无当前记录时模型主动hold，错误金额修订由模型提出后被worker原始 `ValueError: revision lacks independent confirmation` 拒绝。三条均无初始A错误完成；source hold和错误修订各4/4通知签收审计通过。各目录完整性匹配，21个provider请求trace未发现评估真值或buyer私有台账关键词；该扫描不等同于严格信息流证明。

本次直接支持“UNKNOWN、模型hold、程序拒绝”三类结果应分开计数，并支持错误修订不会在权威不确认时提交。它不支持一般错误率或全面恢复率，也没有把离线恶意输入伪装成live Agent行为。成功场景实验到此收敛，下一步整理论文主线与限制。

## 2026-09-10：从饱和指标转向贡献对照

当前 C 保留和条件化路由召回均为 100%，只能说明共享基础设施未损坏，不能证明独立贡献。新增 contribution 离线入口：相同发现条件下拆开通知范围与冻结粒度；固定签名执行下比较完整证据、无签收、普通日志和 opaque relay。普通日志在诚实条件下仍能正确重建，必须分开报告估计准确率与签名可证率。负例不臆断无责，正例 recall 防止全 abstain 得高分。该基础设施没有生产机制改动、模型调用或历史数据改写；构造对照尚不能代表现实效果，详见 TASK_EXPERIMENTS_CONTRIBUTION_V1.md。

### 2026-09-10：协议贡献对照离线实验完成

按 `TASK_EXPERIMENTS_CONTRIBUTION_V1.md` 在新目录 `results/contribution_experiment_v1_20260910/` 重跑并归档了 8 个冻结条件、5 条固定执行、140 个证据投影和公开观察审计；manifest 共 294 项且路径与内容核对一致，未调用 MiniMax。全量测试为 213 passed，报告、图表、CSV 指标和 provenance 保存在 `results/contribution_experiment_v1_figures_20260910/`，审计结果保存在 `results/contribution_experiment_v1_audit_own_notice_20260910/`。

冻结对照中 8/8 条件均阻断受影响分支、无 unsafe completion；`dependency` 保留所有无关分支，`recipient_workload` 在 coordinator 故障下保留率为 0%，在 `middle_a` 路由场景为 67% 或 0%，说明冻结粒度决定误冻范围；broadcast 只增加通知开销，不改变该安全/隔离结论。固定分母追溯对照的 50 条路线、10 个来源身份和 1 个责任正例/4 个负例显示：完整证据为 50/50 可验证路线、10/10 来源身份和 1/1 责任正例；普通日志为 50/50 路线估计但 0/50 可验证；无签收证据仍可完成本地责任判断；opaque relay 无法提供路线或来源证明。所有负例误指控均为 0/4。

这些结果正向支持协议的机制级主张：依赖粒度提供局部冻结，签名收据和来源链把“能估计”提升为“可验证”，并能在缺证据时保留不确定性。它们不支持一般错误率、真实 Agent 泛化收益或法律责任准确率；140 个投影不是 140 个独立样本，且执行轨迹由脚本固定，后续应将这组结果作为论文主线中的受控贡献验证和边界证据。

### 2026-09-10：Contribution Generalization v2 拓扑时序与独立责任标签完成

按 `TASK_EXPERIMENTS_NEXT_CONTRIBUTION.md` 增加最小参数化拓扑构造器，复用 ClaimGateway、签名 handoff、通知 relay 和 MessageBus，没有改生产协议。先在汇聚后分叉拓扑跑通四格，再完成 `results/contribution_generalization_v2/` 的 48 条冻结运行：长链后分叉、两路汇聚后分叉、组织复用但任务依赖独立，各覆盖 shared-upstream/branch-middle、按时/关键边晚到、routed/broadcast、dependency/recipient-workload。48 条运行中按时通知的 unsafe completion 为 0/36；关键边晚到时为 26/36，错误完成保留在截止时间前的实际状态。dependency 过度冻结为 0，recipient-workload 累计误冻 34 个无关任务；汇聚场景出现重复通知，组织复用场景保留了同组织内独立任务。广播通知次数、字节和到达路径单独记录，没有被解释为冻结粒度收益。

责任轴构造了 receiver_a、receiver_b、receiver_c 三个执行组织各五种独立标签，共 15 条基础执行和 120 条投影。每条执行固定 8 个观察条件：四种证据视图和 full 的缺相关通知、缺顺序节点、观察重排、同一 action ID 冲突记录。完整 clean 的明确正例为 3/3；缺证据或冲突时 9/9 进入 `undetermined`；所有 96 个负例动作误指控为 0。独立标签保存在 `label_*.json`，审计器只接收公开 observation，未使用 truth 或 projection 名称；合法不同 action ID 不被当作冲突。raw manifest 320 项、最终 artifact manifest 332 项均核验一致，全量测试 228 passed，模型调用和 token 为 0。

本轮把结论推进到有限拓扑和独立责任标签下的机制边界：局部冻结对三类结构稳定，关键边延迟暴露了通知时序的真实失败边界，证据链能定位明确的本地义务违约并在材料不足时保持待定。它仍不支持现实网络错误率、Agent 一般化收益或法律责任准确率；48/120 是构造条件与投影，不是独立样本。按任务书在本轮完成后停止扩大实验，下一步可将结果整理进论文主线与限制部分。

## 2026-09-10：连接真实 Agent 历史证据

新增 live_replay 导入器，直接验证原始 reliability_batch 与本地动作顺序，不重签。3 条历史轨迹 84 个投影完成；clean full 路线 35/35，普通日志估计同样 35/35，可证性仍有区分。责任证据没有独立正负标签，不能把现有审计结论作为 oracle；明确 duty_accuracy=null。这一步补真实工作流证据接口，不提供一般错误率或真实责任准确率增量。

### 2026-09-10：分支撤销与迟到通知 MiniMax live pilot

在不重复 v2 离线 48/120 矩阵的前提下，使用真实 MiniMax-M3、ProcessBackend 和固定七组织三跳两分支工作流运行 `branch_retraction` 与 `late_notice`：autonomous/dependency 四条流程，加跑一条 `dependency_push` 的迟到通知补充流程。5 条 workflow 共 98 次模型决定、98 次 provider 尝试、397954 个已知 token，所有 usage 已知，worker error 为 0；两组原始目录完整性索引共 140 项，均核验通过。

`late_notice` 的有效故障条件中，autonomous 让 2/4 个错误任务完成，dependency 和 dependency_push 均为 0/4，并分别留下 1 和 2 次程序阻断。push 通知在 tick 10 发出、tick 18 到达，晚于 tick 14 动作截止；dependency pull 在 tick 12 已发现撤销，说明迟到通知时仍能由依赖闭包阻断。`branch_retraction` 虽成功注入故障，但两臂都没有故障后的动作机会，按规范标为不可比较，不能把 0/4 错误完成当作 containment 成功。可评估流程均无协议无关误冻，但 C 任务仍有模型 hold/无效动作造成的未完成。

该 live pilot 正向支持“依赖门禁控制错误传播，通知是及时暴露而非唯一安全路径”的接口级判断，同时保留 autonomous 的真实失败、模型停机和固定拓扑边界。它不足以估计一般错误率、通知策略统计收益、Agent 泛化或责任准确率；详细原始目录与解释见 `results/workflow_v1_live_branch_late_analysis_20260910.md`。


## 2026-09-10：统一L0–L4 benchmark实验交接

已实现独立普通消息L0、累计协议层、三类多跳拓扑、十类场景及单项消融，共210条离线配置；同一节点接口可在持久组织进程中运行。完整代码绑定回归248 passed，其中5个进程等价病例。正式离线矩阵210/210完成，原始manifest及代码绑定验收通过，见`results/layered_v1_offline_final/`。新增MiniMax调用为0。

[统一任务书](TASK_EXPERIMENTS_LAYERED_V1.md)安排离线分析、固定分母证据对照、历史终端提议转移和15条有界live，由实验端统一执行；[实现说明](BENCHMARK_LAYERED_V1.md)记录接口与限制。结果不预设各层单调提升，模型hold与程序阻断分开，真实模型与固定提议比较分开。所有状态持久保存在仓库内。

### 2026-09-10：L0–L4 layered benchmark 实验完成

按 `TASK_EXPERIMENTS_LAYERED_V1.md` 完成并保存 A–D。A 直接复用通过 hash 校验的正式 210 条离线矩阵，没有使用旧的 `results/layered_v1_offline/`；C 复用 21 条固定分母证据投影，并将两条历史模型终端 trace 各转移到 L0–L4，新增 10 条 tape 结果，均为 0 次模型调用且保留 source SHA256。D 的汇总、逐条 paired CSV、长表 chart data、PNG/PDF、provenance 和 artifact manifest 保存在 `results/layered_v1_experiments/`。

正式主矩阵中，三拓扑合计 48 个受影响任务的错误完成从 L0 的 48/48，经 L1 45/48、L2 39/48、L3 24/48，降到 L4 的 0/48；72/72 个无关任务保留。增量分别对应交接篡改完整性、根撤销远端查证、中间/分支依赖闭包和签名有效但事实错误的权威补证。`L4_no_fact` 回到 24/24 错误完成；`L3_coarse` 无错误完成但误冻 9 个无关任务；`verify_all` 与 L3 在本轮撤销条件下持平，对隐藏事实仍无效。confirmed_repair 的离线 recovered_tasks 在低层也为 6，原因是低层允许普通重发，因此没有把普通修订成功冒称为 L4 独有恢复收益。

固定分母追溯共 68 条路线、14 个来源身份和 51 个动作问题。L0 普通日志能估计 68/68 条路线但可验证路线为 0/68、来源身份为 0/14；L1–L4 均为可验证路线 68/68、来源身份 14/14。无签收配置保留估计路线但失去可验证路线，opaque relay 两者均失去；新执行没有独立责任真值，51 个问题均保留为 undetermined。独立责任标签继续引用 `contribution_generalization_v2`，不与本轮追溯投影合并。

按任务书运行 15 条 MiniMax-M3 live pilot（active、late_notice、confirmed_repair × L0–L4），共 257 次模型决定和 provider attempt、403839 个已知 token、4 次未知 usage，全部调用返回，worker error 和 unfinished call 均为 0。late_notice 中 L0–L2 各完成 2/2 个受影响错误任务，L3/L4 为 0/2；confirmed_repair 中 L0–L3 为 2/2，L4 为 0/2，并发生 8 次程序对错误提议的阻断。L4 的 source repair 在主 pilot 中安全 hold，没有形成恢复动作机会，不能报告 live recovery success rate。

为判断这是否只是一次随机 hold，另做 3 条独立 L4 recovery-entry 补充探针，不修改 prompt、工作负载或预算，也不并入 15 条主 pilot。三条均 17/17 调用返回、unsafe completion 为 0、程序阻断为 8/8/7、recovered_tasks 均为 0；前两条有模型 hold，第三条无 hold 但仍未提交恢复动作。该结果支持 live L4 的安全暂停和错误动作门禁，但不支持真实 Agent 已自主完成修订恢复。所有主结果、补充探针和私有 worker 日志均保存在仓库内；worker 目录由 `.gitignore` 排除，不作为公开附件。

本轮全仓库回归为 `248 passed`，正式归档和汇总 manifest 逐项匹配。机制级结论是正向的，但受控矩阵不是独立统计样本，live 层级不是配对因果实验；仍需在论文中保留脚本初始化、同步零延迟 RPC、事实真实性、异步竞态以及 live recovery 未触发等边界。下一步停止扩大成功场景，进入主线写作与失败边界整理。

### 2026-09-10：跨拓扑 MiniMax live 扩展

应用户要求，在原 `long_chain_fork` 的 15 条 live pilot 之外，使用相同 MiniMax-M3、ProcessBackend、prompt、2048 token 上限和每条最多 28 次模型决定的配置，补跑 `converge_then_fork` 与 `reused_org_independent` 两种拓扑的 `active / late_notice / confirmed_repair × L0–L4`，共 30 条。运行器和原始归档保存在 `scripts/run_layered_live_expanded.py` 与 `results/layered_v1_live_expanded_topologies_20260910/`，没有修改 layered benchmark 机制代码。

30 条全部完成，551/551 个 started provider calls 返回或失败并有 journal，已知 token 739245，22 次 usage 未知，worker error、unfinished call、malformed journal 和自动重试均为 0。两种新拓扑的 `late_notice` 均表现为 L0–L2 各 2/2 unsafe、L3/L4 各 0/2；两种新拓扑的 `confirmed_repair/L4` 均为 0/2 unsafe，而低层通常为 2/2。新增流程没有 overfreeze；`converge_then_fork/L1 confirmed_repair` 的 0/2 同时伴随 0/4 完成和 6 次模型 hold，不计为协议安全收益。

与原 15 条合并后，45 条 live 在 12 个受影响任务上的 L0–L4 错误完成为 12/12、10/12、12/12、6/12、0/12；L1 的两个差异都来自汇聚拓扑的模型 hold，层间数值只作描述性观察。实际接受的故障后错误交接为 32、31、25、20、0，说明 L3/L4 的传播阻断方向在三种拓扑上复现。L4 合计执行333次事实查询、37条通知、226891 bytes；模型 hold、invalid action 和安全最终完成分别单独记录。

30 条新增流程没有触发 recovered_tasks，连同旧 pilot 仍无真实模型自主修订恢复成功证据。汇总分析、逐条 CSV、图表、provenance 和 manifest 保存在 `results/layered_v1_live_expanded_analysis_20260910/`；结论增强了跨拓扑的机制方向证据，但不改变 live recovery 未触发、脚本初始化、同步零延迟 RPC 和非独立统计样本等边界。

### 2026-09-10：confirmed_repair live 入口诊断

针对 6 条 L4 `confirmed_repair` 原始运行（主 pilot 1 条、跨拓扑扩展 2 条、recovery probe 3 条）核对 source 的真实模型输入、权威查询结果和 RPC 顺序。6/6 条的控制器日志都包含旧 `root_A=100` 被权威判为 `CONTRADICTED` 的证据，但没有一次生成新 `125` 候选的 `CONFIRMED` 证据，因为 `revision` 入口从未被调用。

source 修复决定为 `hold` 5 条、`verify` 1 条、`proceed` 0 条。模型输入在 6/6 条中都只有空 `task_claims`、脚本提供的 `own_business_revision=125`、本地 disputed/blocked 旧声明和 `bound_recovery=true`；没有 fact evidence reply、recovery offer、recovery envelope 或 `request_recovery` 动作。当前 system schema 只允许 `proceed / verify / hold`，而 `repair()` 对 source 的 `verify` 和 `hold` 都直接返回，不执行查询后的第二轮决定。

因此这些 hold/verify 是“模型没有看到可执行恢复入口时的安全暂停”，不是“模型在满足模型可见前提后拒绝请求恢复”。控制器隐藏地把 source 的 `proceed` 解释为启动 `revision`，再自动进入 envelope/frontier/rebuild；这可以验证程序闭环，但不能证明真实 Agent 自主请求恢复。诊断报告与逐条审计在 `results/layered_v1_confirmed_repair_diagnosis_20260910/`，审计脚本为 `scripts/audit_layered_confirmed_repair.py`。下一次 live 前应先修正 repair action/schema、传入绑定的权威证据和结构化恢复任务，并让 `verify` 有真实后续回合。

### 2026-09-10：confirmed_repair live 适配器修复与真实模型复核

本轮由当前实验执行端独立完成修复。首先在 `trust_network/benchmark/layered/engine.py` 增加显式的 `request_recovery` 控制平面阶段、source 私有 `fact_ref` 修订入口、权威确认后的 recovery envelope/frontier/rebuild 调度和最终审批上下文；`backend.py` 只允许 source 从本地私有 fact index 解析修订事实，派生 worker 只允许从恢复父声明解析 `fact_ref`。随后根据第一轮 live 原始输出修正两处适配语义：接受与上下文完全一致且顺序正确的真实 claim ID，明确 `CONTRADICTED` 是启动恢复的依据；再根据第二轮真实输出明确新父事实已由权威确认、可以替代旧事实，并要求派生签发者使用本轮 `task_claims` 中的父声明，不能等待一个本阶段本来就要生成的派生声明。模型不能提供金额 JSON，金额始终由 source 私有索引和 worker 产生。

修复期间的失败和中断目录均保留，未混入最终统计。最终版本先通过 250 项回归和 5 个 ProcessBackend parity case，完成 210 条离线矩阵并通过源码哈希 preflight；再运行 6 条 MiniMax-M3 / ProcessBackend `L4/confirmed_repair` replication，覆盖 `long_chain_fork`、`converge_then_fork`、`reused_org_independent` 三种拓扑各两次。12/12 个受影响任务均由模型选择 `request_recovery`，12/12 个 verify-only 恢复基础提交成功；6/6 次 source 选择 `propose_revision`，6/6 个修订 offer 获 buyer 权威 `CONFIRMED`。25 个 frontier 重建步骤中 19 个完成，6 个因模型 hold 停止；最终完整恢复 6/12 个受影响任务，已完成恢复的 6/6 个最终动作完成。6 条 workflow 全部为 0 unsafe completion，合计 0 次 RPC rejection、0 次 worker error；无关任务完成 9/12。共 149 次模型调用、152 次 provider attempt、309384 个已知 token、1 次 usage 未知，所有 provider journal 已返回且无 malformed line 或 unfinished call。

修复前 3 条正式 L4 `confirmed_repair` live workflow 共 0/6 个受影响任务恢复；旧数据没有恢复阶段字段，不能反推出当时模型是否发起过请求。该前后结果是适配器修复的受控比较，不是随机化因果估计。当前证据支持：协议的安全门禁在真实模型流程中保持 0/12 unsafe，模型已经能够在安全暂停后主动进入恢复入口，source 权威确认和绑定重建可以在真实多跳流程中完成；恢复可用性仍为 6/12，`converge_then_fork` 两次均在多跳重建阶段停止，不能宣称所有受影响任务自动恢复。

最终原始数据、worker journal、manifest、分析报告和图表保存在 `results/layered_v1_live_confirmed_repair_final_v2_20260910/`；复现脚本为 `scripts/run_layered_confirmed_repair_live.py`，分析脚本为 `scripts/analyze_layered_confirmed_repair_live.py`。第一轮入口修复和重建 prompt 的失败边界分别保存在 `results/layered_v1_live_repair_request_fix_pilot_20260910/` 与 `results/layered_v1_live_confirmed_repair_replication_20260910/`。


## 2026-09-11：最终统一live基础设施与交接

最终统一 live 计划随后完成 300 条主实验和 50 条消融；完整结果、公开汇总和异常审计见 `FINAL_UNIFIED_LIVE_BENCHMARK_20260911.md` 及 `results/final_unified_live_v1_combined_20260911/`。本条之前的交接状态仅保留为时间线记录。

### 2026-09-11：最终统一 live 实验完成

最终统一 live 计划完成 300 条主实验和 50 条消融。344/350 条 workflow 有最终结果，6 条在审计暂停时没有最终调用结果，保留为 unknown 并继续留在固定分母。L0–L4 主矩阵的错误完成率分别为 36.2%、36.2%、30.8%、19.2% 和 0%；错误传播交接分别为 242、236、196、153 和 0。L4 无关任务保留 138/144，确认修订恢复请求 10/12，最终恢复 6/12；其余 4 条在 workflow 预算耗尽时停止。

最终异常审计区分了模型/适配器契约异常、瞬时 provider/network 失败、预期安全拒绝和预算停机。claim-ref 与动作契约异常及 46 条 network overlay 均只重跑受影响 workflow；最终非法决定、非法结果、provider failure decision 和 worker error 均为 0，58 次篡改交接签名拒绝属于预期门禁。公开 aggregate、逐任务指标、差异、追溯投影、异常审计和图表保存在 `results/final_unified_live_v1_combined_20260911/`，摘要见 `FINAL_UNIFIED_LIVE_BENCHMARK_20260911.md`。
