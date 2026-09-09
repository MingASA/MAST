> **无历史上下文的实验代理请先读：[完整实验任务书](TASK_EXPERIMENTS_NEXT_AGENT.md)。**包含研究背景、权限与配置、当前代码边界、真实实验步骤、对照公平性、指标和交付标准。

> **实验执行交接：** [下一位实验执行者任务书](EXPERIMENT_OPERATOR_v20.md)，含一条命令离线贯通、外部模型接入、固定对照边界和待验证研究问题。

> **V20 无付费调用交接：** [批量协议实现与其他模型实验指南](RELIABILITY_HANDOFF_v20.md)。已接入共享补证、局部冻结、动作门禁和公开策略审计；提供固定提议三策略重放。该重放不是完整自主 Agent 效果实验。

> **当前主线：控制错误传播、提高安全性，并保留合理追溯能力。**先查看[传播控制交互 Demo](results/claim_v14_active_check/demo.html)、[安全与追溯目标](SAFETY_AND_ACCOUNTABILITY.md)及[传播协议边界](PROPAGATION_v13.md)。Demo使用真实MiniMax两跳交接，展示通知未送达时主动确认阻断旧授权，以及签名送达证据如何约束责任判断；目前是本机独立进程和模拟动作。
>
> 正向与负向结果同时保留：[18条统一协作对照](results/repair_v10_unified/report.md)中依赖阶段组安全完成4/6、全验证2/6，自主组不安全提交4/6；样本小且条件间差异明显。[配对修正实验](results/paired_repair_v12/report.md)不支持反提案候选增益。后文为历轮历史入口和结论，不代表全部都是当前主实验。

# 跨组织 Agent 可信协作研究原型

当前新增入口：`trust_network.demo.run_reliability`。主指标改为最终`unsafe_completion_rate`；Autonomous、Verify-All和Risk-Aware共用场景、prompt、证据服务与缓存，只替换动作提交前的policy。公开单据表面一致，买方正式批准状态必须经跨组织evidence请求取得；模型提议的pass可被程序撤销。

```bash
# 无模型调用的preflight复现，输出到新目录
.venv/bin/python -m trust_network.demo.preflight_reliability --out results/reliability_v4_preflight_rerun
# 默认只显示预算，不启动MiniMax
.venv/bin/python -m trust_network.demo.run_reliability
```

62项测试通过。真实实验Autonomous/Verify-All/Risk-Aware不安全完成分别1/12、0/11、0/11，查询成本30/33/24。Risk-Aware本批没有触发程序干预，尚未证明增量收益；Verify-All实际阻止两次模型准备放行的未授权提交。已记录95次API请求、125598 token，另有2次失败用量未知。离线低风险漏放反例仍成立。[逐run与结论](results/reliability_v4_minimax/interpretation.md)。后文为前三轮历史实现与结果。

本项目研究组织之间内部状态不可见时，验证预算、检查记录与责任分配如何影响错误传播。包含两个可独立运行的层次：图上的随机控制与博弈实验，以及实际调用 MiniMax 的信用证单证协作 demo。所有业务数据、概率、成本和角色档案都是 synthetic，不代表真实机构或实际业务规则的完整实现。

本轮结果入口：[交付摘要](results/DELIVERY.md)、[MiniMax六组实测](results/minimax_v2/summary.md)、[Docker流程实测](results/minimax_containers/summary.md)。

原始任务文档保留；经用户批准的修正在 [MODEL_DECISIONS.md](MODEL_DECISIONS.md)。不要把检查通过当作错误清零，也不要把签名当作业务结论正确的证明。

## 安装与验收

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q -s
```

四项硬性验收均为可运行测试：

- `test_global_dp.py`：独立连续信念分段线性解析解，对照数值 DP；覆盖节点、预算、网格内外点和阈值，误差必须小于 1e-3。默认网格 101；严格回归和扫描使用 10001 点，并检验网格加密。不能声称默认101点对任何成本尺度都具有1e-3精度。
- `test_attribution.py`：固定种子生成 12000 条随机分支轨迹，按观测分组比较经验联合分布与推断后验；断言条件 KL 与 top-1 校准误差，并输出具体指标。
- `test_settlement.py`：1000 个随机后验上的份额归一；更换分配规则后社会成本完全相同，组织净成本变化。
- 另有图展开、真实过程、最佳响应与穷举对照、震荡返回、证书篡改、版本失效、补证与改单分支测试。测试中的 scripted worker 只用于离线单元测试，实际 demo 遇到 API 错误会停止，不回退到伪造回复。

## 模块与理论概念

| 模块 | 实现与边界 |
|---|---|
| `core/graph.py` | Node、Edge、Graph dataclasses，networkx 承载，参数与路由检查，decision_maker/payer/bearer |
| `core/unroll.py` | 显式 resubmit 边增加计数；其余边必须无环；k=0首次提交，最多3次重提交，之后无条件终止判罚归当前 bearer |
| `sim/simulator.py` | Bernoulli 内生错误、边传播、flag/clear、随机修复、来源 rho 与真实轨迹；ground truth 不提供给策略 |
| `solve/global_dp.py` | V2 线性插值 Bellman DP；V1 独立精确分段线性 baseline；预算可为小数，flag/clear分别扣费 |
| `solve/attribution.py` | 起源和漏检集合的增广隐状态 forward/backward；终点发现误报、路径验证记录、平滑边缘、生存概率 |
| `solve/settlement.py` | 可插拔比例连带与 bearer-only；真实损失及验证/修复/摩擦成本结算；份额与社会成本守恒 |
| `solve/decentralized_game.py` | 有完美回忆的信息集博弈；固定他人策略、按反事实到达概率在信息集上求局部最佳响应；检测循环和 exploitability |
| `scenarios/` | 可复现随机图、信用证展开图、JSON配置加载器 |
| `experiments/` | 六组合扫描、精确观测树与数值DP交叉校验、CSV/JSON/Markdown、PNG/SVG |
| `demo/` | MiniMax API、每组织worker、版本化单据、Ed25519证书、条件返工与人工升级 |

社会最优使用标量 r：这里检出率、传播和社会损失均与错误来源组织无关，因此来源 rho 的边缘是社会目标的充分统计量。责任目标不能只用 r；博弈保留完整起源、漏检集合及观测历史。来源分量按共同似然更新，不采用原文不精确的“分别二元更新再归一化”。

归因选择“最新内生错误覆盖旧起源”的单起源约定。漏检集合仍保留已消失错误对应的历史记录。它是统计变量，不能自动视为法律失职。`Proportional.eligible_checks` 可限制责任检查范围；不同失职权重是待研究的机制参数。

`decode` 对路径和检查动作条件化：固定/公开可推知动作可直接调用。对于依赖未公开观测的策略，动作本身可能提供证据，不能将其当作无信息干预；博弈求解器因此直接积分完整策略观测树，而非错误地套用独立路径解码器。

## 数学实验

```bash
.venv/bin/python experiments/run_sweep.py --seeds 7 11 23 --budget 1.2 --starts 2 --out results
MPLCONFIGDIR=/tmp/wuxing-mpl .venv/bin/python experiments/plots.py
.venv/bin/python -m trust_network.solve.attribution
```

结果：[摘要](results/summary.md)、[PoA表](results/poa.csv)、[图](results/poa.png)、[归因指标](results/attribution_calibration.json)、[起点与震荡详情](results/sweep_details.json)。

每个场景运行协议0/1/2 × selfish/resp，默认从全部不检查、全部检查两个策略起点求解。`--starts` 大于2会额外添加固定种子的随机起点。

这里输出 **observed PoA**：找到的已收敛纯策略均衡中最大成本除以全历史信息社会最优。它没有穷举所有均衡，不能当作严格最坏 PoA；未收敛时不填 PoA，保留振荡及偏离获益。零分母显式处理。分母还用精确观测树校验；DP误差超1e-3就中止扫描。

协议0公开路径和共享预算，隐藏跨组织检查记录；这意味着预算变化可能间接泄露部分动作信息，不是绝对无信息。协议1公开检查行为及信号。协议2在数学模型中与1相同，因为没有伪造；demo另执行签名验证。调度/路由中的信息泄露与策略先验属于模型假设，应在论文中说明。

当前三组随机图的 observed PoA 约1.09–1.16，信用证图约2.6383。当前六组合未表现出责任或证书收益。原因之一是默认规则只分配错误起源与已执行检查的漏检责任，未检查者不会因“不检查”进入漏检集合，因此不保证产生验证激励。这是本轮发现，不是预先设定的机制有效性结论。固定策略下转移中性也不意味着改变均衡后社会成本不变。

精确博弈的树会随检查数、路由和预算指数增长，默认上限250000节点，超过时明确报错；本版本适合小型研究案例。组织范围按 decision_maker 授权，默认等于 org。信用证的出口方审单由 advising_bank 决策、seller支付、buyer承担默认业务损失，专门用于检验决策权与责任分离；不能据这一配置预先断言必定验证不足。

## 实际 MiniMax 单证 demo

案例为10套工业泵出口：正式信用证和实际货物为 MX-40，但发票因一封未获采购授权的技术邮件被改为 MX-40B。组织分别为出口商、货代、检验机构、出口方受托审单银行、开证行和买方。每个组织只有自己的私有档案，以及实际收到的业务消息与证书。数量检查可以用程序完成；型号授权解释、概括描述是否冲突、检查范围、补证和升级决策由实际模型完成。

[公开单据](examples/letter_of_credit/public/bundle.json)、[组织档案](examples/letter_of_credit/organizations)、[评估器真值](examples/letter_of_credit/ground_truth.json)。真值仅由运行后的评估器读取，不进入任何模型上下文。

使用已授权的现有配置，不复制密钥：

```bash
.venv/bin/python -m trust_network.demo.run \
  --env-file /home/cjy/cyberagent/.env \
  --out results/minimax_new
```

默认六组合均调用实际 MiniMax。读取 `CAI_MODEL`（去除 `openai/` 路由前缀）、`OPENAI_BASE_URL`/`OPENAI_API_BASE`、`OPENAI_API_KEY`，不执行 `.env` 内容。测试时配置为 MiniMax-M3。密钥只用于请求认证，不进入 prompt、日志或输出。API 调用上限为每组24次；重提交最多3次；网络失败和无效响应不会伪造完成。

输出含逐步 JSONL 审计、证书与公钥、检查范围、业务决策、版本、用量、重提交、完成/升级/拒绝结果。本demo由可信编排器在内存中模拟各组织签名私钥；生产部署应把私钥放入各组织自己的签名服务，并独立分发可信公钥。当前不声称抵御编排器伪造。旧版本证书不会被用于新版单据。证书证明记录来源和完整性，不证明检查完整或结论正确。

`results/minimax` 保留首次接口试运行；`results/minimax_v2` 为修正动作类型和版本回执后的运行。不同版本的输出不混合做效果比较。`.jsonl.interrupted` 保留被用户中断的部分调用。Token汇总只覆盖已记录响应（含当前格式重试），中断或早期失败的未记录调用不包含在内，不能据此核对总账单。默认已完成组会跳过；若只有不完整 JSONL 会拒绝覆盖，请用新输出目录重试。

单案例每组一次只验证端到端可运行性，不估计事故概率、LLM能力、责任机制效果或均衡PoA。LLM的selfish/resp当前通过任务目标描述体现，没有训练或求解真实模型的策略均衡；检查条数也不是校准后的检出率。数学参数尚未从这些调用拟合。

私有代码标记用于有限的泄露探针；没有命中标记不等于没有信息泄露。检查记录本身也可能泄露商业信息，实际系统需要披露规则。结果保留这些风险，不把“提示词要求保密”视为安全证明。

## 跨设备部署与隔离

本机已运行的模式为独立 worker 子进程及独立模型上下文，**不声称提供操作系统级安全隔离**。模型没有通用文件读取工具，runner只构造该组织的输入，但本机同用户进程仍有共同文件权限。

提供 `Dockerfile` 和 `compose.yaml`：每个组织容器只挂载自己的私有档案、只读模型配置；只读根文件系统、非root用户、删除capabilities。可将这些worker分别部署到不同机器，并配置各自地址。当前已实测六个组织容器启动，并检查非root身份、只读根文件系统、只读挂载以及其他组织档案不可见；报告见 [Docker验证](results/docker_validation.json)。并完成一组verified_certificate/resp端到端MiniMax调用，共8次组织决策。这验证的是单机Docker部署，尚未实测物理分布式主机。

```bash
MODEL_ENV_FILE=/home/cjy/cyberagent/.env docker compose up --build -d
.venv/bin/python -m trust_network.demo.run \
  --env-file /home/cjy/cyberagent/.env \
  --endpoints examples/letter_of_credit/endpoints.json \
  --out results/minimax_containers
```

示例端口仅绑定本机。跨机器部署应使用组织认可的身份认证与加密传输；示例HTTP worker不是公开互联网服务。真实业务组织通常应分别提供自己的模型凭据。

## 研究范围与后续问题

已交付MVP主线及六组合；原TODO中非MVP的全面边界密度/异质性扫描、记录预算优化、rho压缩regret、多根因与证书伪造博弈仍是后续研究，未宣称完成。

图上的固定路由是外生随机基线。demo里的改单、补证和升级由真实观测/动作触发；文档汇合作为业务输入实现，不把这个条件流程冒称为固定路由DP。银行审单不担保实物质量，检验机构只对其声明范围给出结论。第一版优先复现实验与审计，尚未实现真实银行、承运人或海关系统连接。

下一步有研究价值的问题是：如何对可合理阻断却未执行的检查分配责任，如何避免因归因噪声引发过度检查，以及证书应披露多少证据才值得其隐私和验证成本。

业务依据与API参考：

- [美国商务部信用证指南](https://www.trade.gov/letter-credit)：单证准备、专业人员及修改重提交。
- [ICC信用证说明](https://academy.iccwbo.org/trade-finance/article/11-questions-that-will-help-you-master-documentary-credits/)：银行处理单据，不能等同于货物质量担保。
- [MiniMax官方接口](https://platform.minimaxi.com/docs/api-reference/text-chat-openai)：当前模型与Chat Completions协议。

## 第二轮增量工作

[第二轮交付与结论](DELIVERY_v2.md)。原24项测试和历史结果保留；当前42项测试通过。

新增：机会性遗漏责任`ProportionalWithOmission`、基于原forward/backward的遗漏权重、每起点期望检查次数与过度检查比；逐个展开节点的角色对齐JSON配置；需先确认成本的MiniMax重复实验脚本。

本次信用证PoA随遗漏权重0→1从2.638268降至1.006474，检查比从0升至1，未观察到超过社会最优的检查数量。角色消融没有改善最差均衡，部分较好起点反而因改为自己付费而恶化。公式兼容处理与L=0干预限制在MODEL_DECISIONS中明确说明。

重新运行时使用**新的输出目录**，脚本拒绝覆盖已有扫描文件：

```bash
.venv/bin/python -m pytest -q -s
.venv/bin/python experiments/run_round2.py \
  --omission-out results/sweep_v2_omission_rerun \
  --ablation-out results/sweep_v2_roles_rerun
.venv/bin/python experiments/run_sweep.py \
  --seeds 7 11 23 --out results/baseline_metrics_rerun
```

本次已生成[遗漏责任报告](results/sweep_v2_omission_final/report.md)、[角色消融报告](results/sweep_v2_roles/report.md)、[图](results/sweep_v2_omission_final/omission_tradeoff.png)。`by_start.csv`保留每个起点；`summary.csv`取较差已收敛均衡，同时保留检查比起点范围，不能用汇总掩盖多均衡差异。

MiniMax批次默认只估算，不调用API：

```bash
.venv/bin/python -m trust_network.demo.run_batch --repetitions 15
```

第二轮任务书要求在估算之后确认。用户已确认两组各15次，约210次调用/379410 token的估算方案；**30个run已全部执行结束**，22个业务完成、6个人工升级、2个运行报错；[批次结果](results/minimax_batch_v2/interpretation.md)。已授权的执行命令为：

```bash
.venv/bin/python -m trust_network.demo.run_batch \
  --repetitions 15 \
  --combinations black_box:selfish verified_certificate:resp \
  --temperatures 0.2 0.5 0.8 --workers 2 \
  --env-file /home/cjy/cyberagent/.env \
  --out results/minimax_batch_v2 --execute
```

这里复用原子进程worker，并传递温度配置；不使用仍运行的第一轮旧镜像，避免容器代码版本不一致。若批次被终止，确认相关进程已停止后，可仅恢复日志/报表，不重启调用：

```bash
.venv/bin/python -m trust_network.demo.run_batch \
  --out results/minimax_batch_v2 --collect-only
```

温度循环产生的是混合设置下的行为分布，报告同时分层；同一批次的初始资料、ground truth和签名密钥固定。私有标记命中按所有正常返回run累计，失败片段单列；原文检查范围不进行未声明的语义合并。本轮不拟合数学模型参数。

第二轮批次实际记录162次组织决策调用、286590 token，全部162份签名与场景哈希验证通过。两组的业务完成数为10与12（各14个正常返回、1个运行报错），不能据小样本或联合条件对照断言独立机制有效。[行为分布图](results/minimax_batch_v2/behavior_distribution.png)与[全部原始分布](results/minimax_batch_v2/aggregate.json)均已保存；两次错误保留、不以补跑替换。

## 第三轮增量工作

[第三轮交付与执行状态](DELIVERY_v3.md)。新增银行专用resp-omission框架、统一的事后冲突检出评估和各组6次的单变量对照入口；其余组织均为原resp，协议固定verified_certificate。完整银行任务原文和逐句diff已在[MODEL_DECISIONS](MODEL_DECISIONS.md)预注册。当前48项测试通过，历史结果保持原样。

**原自然流程MiniMax批次未执行，修订后的暴露受控批次已执行。**执行前估算为12次工作流约68次调用、144683 token，加责任文字和事后抽取预留合计约80次调用、183683 token。默认命令只显示预算，不读取密钥或请求API：

```bash
.venv/bin/python -m trust_network.demo.run_framing
```

修订受控批次使用已授权的MiniMax环境文件，实际结果写入新的 `results/framing_v3_controlled_retry`；原始沙箱网络失败记录保留在 `results/framing_v3_controlled`：

```bash
.venv/bin/python -m trust_network.demo.run_framing \
  --env-file /home/cjy/cyberagent/.env \
  --out results/framing_v3 --execute
```

自动报告以flagged_invoice_discrepancy为唯一主指标，输出两组检出次数/有效run、Wilson描述性区间及观察差；错误单列不计分母。bank_exposed记录是否实际面对原始未修正冲突。完成/升级/拒绝、重提交、检查范围作为背景。证据、语义抽取响应与校验后标签保存以供复核；真值只由事后评估读取。N=6/组不支持因果或显著性结论。这是遗漏责任机制第一次在真实agent上做的小规模检验，不是决定性证据，更大样本或更多场景变体是后续工作。

**预检查发现重要限制：**第二轮30个run、44次银行决策中，银行面对原始未修正冲突的次数为0（卖方在前面已修正，或流程提前停止）。沿用原流程的新批次可能仍无检测机会；此时零检出不能说明机制无效，暴露条件下检出率为NA。预检查与完整提示词快照见[审查资料](results/framing_v3_preflight/prompt_review.md)。无需API即可重新生成：

```bash
.venv/bin/python -m trust_network.demo.preflight_framing \
  --out results/framing_v3_preflight_rerun
```

次线复用原4张图与第二轮PoA结果，新增[下游价值集中度分析](results/structure_v3/report.md)：C是经过节点后严格下游期望损失占全路径期望损失的比例，按到达概率加权，在所有节点pass的共同参照下积分。四图最大C都约1，但仅信用证在w=0→1明显改善，所以现有n=4不能据集中度预测机制效果。没有新图、没有新sweep；复现命令：

```bash
.venv/bin/python -m trust_network.experiments.round3_structure \
  --source results/sweep_v2_omission_final/summary.csv \
  --out results/structure_v3_rerun
```


### 第三轮修订：暴露受控补丁

固定[冲突输入包](examples/letter_of_credit/controlled_bank_input.json)从银行阶段启动，沿用真实补证、修改和重审逻辑，修改后不重置旧错误；其他组织的行为及角色相对顺序保留。出口方银行先处理，开证行看到其实际下游状态，不强迫两银行均作相同处理。完整口径见MODEL_DECISIONS.md末节。

默认只输出修订预算（约80次调用/183683 token），不会请求API：

```bash
.venv/bin/python -m trust_network.demo.run_framing
```

仅在确认本次固定输入和预算后执行；原自然流程批次不要运行：

```bash
.venv/bin/python -m trust_network.demo.run_framing \
  --env-file /home/cjy/cyberagent/.env \
  --out results/framing_v3_controlled_retry --execute
```

新增报告明确标记“暴露受控”，并列历史银行暴露0/44，汇总温度分层；N=6/组仅描述观察结果，不能代表自然流程遇到冲突的概率。

实际批次结果：A组有效5/6、检出5/5；B组有效6/6、检出6/6。两组有效检出率均100%，B−A为0个百分点，主指标达到天花板，不能说明resp-omission带来增量检出效果。A组一个run在出口方银行请求补证后失败，未计入分母；其余run均在出口方银行首个决策时检出并升级，开证行没有独立决策机会。实际12个工作流调用、11个评估调用，共23521 token。完整结果见[受控批次目录](results/framing_v3_controlled_retry)。
