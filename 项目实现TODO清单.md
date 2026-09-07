# 跨组织多跳可信度网络 —— 方向B（去中心化验证博弈）+ 方向D（事后责任归因）实现清单

对应此前讨论确定的默认设定：单次workflow、参数对各自组织自己已知、归因输出为联合分布 `(K*, F)`、结算函数先用比例连带、状态空间先按完整 ρ 分布实现。

标记说明：`[MVP]` = 做一个能跑通、能出图的最小demo所必须的；不标记 = 完整研究范围内需要但可以晚做/作为消融实验补充。

---

## Phase 0：基础设施

- [ ] `[MVP]` 定义 `Node`：`id, type ∈ {process, verify}, org, alpha(仅process), c, L(仅action), delta, epsilon, mu, c_fix, F(仅verify)`
- [ ] `[MVP]` 定义 `Edge`：`(u, v), q_uv, p_uv`
- [ ] `[MVP]` 定义 `Graph`：`nodes, edges, org_of(v)`，用 networkx.DiGraph 承载，节点/边属性挂字典即可
- [ ] `[MVP]` 定义角色映射：`decision_maker(v)`, `payer(v)`, `bearer(v)`（默认都等于 `org(v)`，允许显式覆盖）
- [ ] 有界重提交环处理：节点ID展开为 `(base_id, resubmit_count)`，超过上限的节点直接路由到"流程终止/默认判罚"分支
- [ ] `[MVP]` scenario 配置加载器（YAML/JSON），支持两类场景：`synthetic_random`（用于扫描实验）和 `letter_of_credit`（Phase 6 的demo场景）

## Phase 1：环境与模拟器（贯穿全项目的Monte Carlo校验工具）

- [ ] `[MVP]` 路径采样器：从 source 出发，按 `q_uv` 采样下一跳，验证节点作为图中的普通分支目标（不是外挂动作）
- [ ] `[MVP]` 真实错误过程模拟：按 `X_v = 1 - (1-alpha_v)(1-p_uv*X_u)` 的概率生成真值（source: `X_s ~ Bernoulli(alpha_s)`）
- [ ] `[MVP]` 验证信号模拟：给定真值 `X_v`，按 `delta_v/epsilon_v` 生成 `flag/clear`；`flag` 后按 `mu_v` 决定 fix 是否真的把 `X_v` 拉回 0
- [ ] 终点损失发现节点复用同一套信号模型（把"loss discovery"当成一种特殊verify节点）
- [ ] `[MVP]` 输出完整 ground-truth trace：每个节点的真值、是否被路由到verify、观测信号、fix结果 —— 这是后面所有算法正确性校验的唯一数据来源

## Phase 2：全局（社会最优）DP求解器 —— 不完美验证器版本

- [ ] `[MVP]` 标量 `r` 版本的贝叶斯更新：
  ```
  r_flag  = delta*r / (delta*r + epsilon*(1-r))
  r_clear = (1-delta)*r / ((1-delta)*r + (1-epsilon)*(1-r))
  r_flag_fixed = (1-mu) * r_flag
  ```
- [ ] `[MVP]` `Q_pass(v,b,r)` 和 `Q_verify(v,b,r)`（数值实现，参照修正版公式，含 `F_v` 摩擦成本项）
- [ ] `[MVP]` 完整分布 `ρ_v(j)` 版本的更新（对每个组织来源分量分别做上面的贝叶斯更新再归一化）
- [ ] `[MVP]` backward induction：对展开后的DAG做拓扑排序，逆序填表；`r`/`ρ` 维度做网格离散化（如101个格点）
- [ ] **关键正确性检验（必须做，不可跳过）**：令 `delta=1, epsilon=0`，数值DP的 `V(v,b,r)` 和策略阈值 `tau_v(b)` 必须收敛到V1里已经解出的闭式解——用这个作为整个数值DP实现是否正确的回归测试
- [ ] 记录 `V1`（闭式，作为baseline/单测参照）和 `V2`（数值，不完美验证器）两套实现，不要互相覆盖

## Phase 3：责任归因算法（方向D）

- [ ] `[MVP]` 定义样本空间：`K* ∈ {w_1,...,w_m} ∪ {∅}`，`F ⊆ {路径上被调用过的verify节点}`
- [ ] `[MVP]` 生存概率 `S_k = ∏_{l=k}^{m-1} p_{w_l,w_{l+1}}`
- [ ] `[MVP]` forward-backward posterior decoding：给定观测（终点loss discovery信号 + 路径上各verify节点的flag/clear记录），计算联合后验 `P(K*, F | 观测)`
- [ ] `[MVP]` ∅（无过错/终点信号误报）情形的显式处理，不能与真实起源混算
- [ ] **正确性检验（必须做）**：跑 N≥10000 次Monte Carlo模拟（用Phase1的模拟器生成大量真实路径+观测），统计真实 `(K*,F)` 的经验分布，和算法给出的后验分布做对比 —— 报告 KL散度 和 top-1命中率
- [ ] 记录预算模块：允许在非verify节点上插入低成本"仅记录/签名，不做判断"的动作，量化其对归因后验熵的边际影响

## Phase 4：结算函数与净成本

- [ ] `[MVP]` `g` 函数默认实现（比例连带）：`share_i(v)` 正比于 `(K*,F)` 后验里"i 被认定负责"的概率质量；`K*=∅` 时全部退回 `bearer(v)` 自留
- [ ] `[MVP]` 单测：任意随机后验分布下，`Σ_i share_i(v) = 1` 恒成立
- [ ] `[MVP]` `Net_i = Σ_{payer(v)=i} c_v·x_v + Σ_v L_v·X_v·share_i(v)`
- [ ] `[MVP]` `J_social = Σ c_v·x_v + Σ L_v·X_v`
- [ ] **正确性检验（必须做）**：更换 `g` 的实现（比如全额判给bearer、或均分），`J_social` 数值必须保持不变（transfer neutrality），只有各 `Net_i` 的分布会变——这是验证Phase3/4接口设计正确的核心单测
- [ ] `g` 做成可插拔接口（策略模式），方便后续换不同结算规则做对比实验

## Phase 5：去中心化博弈（方向B）

- [ ] `[MVP]` org-scoped策略接口：组织 `i` 的策略只能决定自己 `org(v)=i` 的节点是否verify，其余节点的决策来自其他组织当前的策略（作为环境的一部分传入）
- [ ] `[MVP]` "自私版"目标：`J_i^selfish = E[Σ_{org(v)=i} L_v X_v]`（不接责任分摊）
- [ ] `[MVP]` "责任版"目标：`J_i^resp = Net_i`（接入Phase4）
- [ ] `[MVP]` 局部best-response求解器：固定其他组织策略，对组织 `i` 局部节点跑Phase2式DP（只是决策空间限制在自己节点上，其余节点的verify结果作为外生环境）
- [ ] `[MVP]` best-response主循环：轮流更新各组织策略直到收敛；加震荡检测（连续两轮策略集合出现循环 → 报告"未收敛/多均衡"而不是死循环）
- [ ] `[MVP]` 协议0/1/2实现：作为跨组织边（`org(u)≠org(v)`）上"下游能不能看到上游是否verify过"这一信息可见性的开关，直接影响下游贝叶斯更新时用哪个先验
- [ ] `[MVP]` PoA计算：`J_equilibrium(protocol, objective) / J_social_optimal`，对(协议0/1/2) × (自私/责任) 六种组合分别输出

## Phase 6：场景实例化（信用证demo）

- [ ] `[MVP]` 定义节点/组织清单：卖方单证准备 → 货代订舱 →（可选：出口报关）→ 通知行初审 → 开证行审单 →（分支：相符/不符点争议，触发重提交）→ 进口清关 → 买方收货（=终点loss discovery节点）→（可选：保险理赔分支）
- [ ] `[MVP]` 三角色标注：明确标出所有 `decision_maker(v) ≠ bearer(v)` 的节点/边（例如：检验费买方要求但卖方委托支付、审单决策在银行但错误放款损失部分转嫁买方等），这是用来验证B的核心预测"责任与决策分离处系统性验证不足"的关键配置
- [ ] `[MVP]` 参数默认值：先用"看起来合理"的synthetic数值（不需要真实数据源），在README里注明这些是估计值
- [ ] 不符点重提交上限（如3次）配置进图展开逻辑

## Phase 7：实验

- [ ] `[MVP]` 扫描实验：协议(0/1/2) × 目标(自私/责任) → PoA，先在synthetic随机图上跑，再在信用证场景上跑一遍作为对照
- [ ] 扫描：组织边界密度、α/p异质性对PoA的影响
- [ ] 消融：责任项对PoA的边际压缩效果（验证"责任机制是Pigouvian transfer，只改变博弈不改变社会最优"这条结论在数值上成立）
- [ ] 归因熵 vs 记录预算 曲线
- [ ] 充分统计量探索：完整 `ρ` 分布 DP vs 只用标量 `r` 近似的DP，在不同参数regime下的regret对比（为"何时可以压缩成低维统计量"提供数值证据，作为后续定理候选的输入）

## Phase 8：可视化与产出

- [ ] `[MVP]` PoA vs 协议强度 柱状/折线图
- [ ] 归因熵 vs 记录预算 曲线图
- [ ] regret vs ρ异质性 图
- [ ] 汇总一份结果摘要（可直接摘录进申报书/demo讲解）

---

## 建议的最小可跑通路径（如果时间紧，先做这条主线）

Phase0(基础结构) → Phase1(模拟器) → Phase2(全局DP，含退化验证单测) → Phase3(归因，含MC校验) → Phase4(结算，含中性单测) → Phase5(仅协议0和1、仅责任版目标，先不做协议2和自私版对照) → Phase6(信用证场景跑一遍) → Phase8第一张图(PoA vs 协议)。

其余标记为非MVP的部分作为第二轮补充实验。
