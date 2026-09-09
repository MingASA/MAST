# 给编码Agent（Codex/Claude Code）的实现任务书

将本文件整体作为初始任务描述粘贴给编码agent。本文件是自包含的——不依赖额外背景对话，agent应能仅凭此文件完成实现。

---

## 项目背景（一段话）

我们在研究跨组织多智能体协作网络中，如何通过"验证预算分配"和"事后责任归因"两个机制，最大程度防止错误在协作链中传播导致的非预期结果。核心是一个图上的在线随机控制问题：错误可能由节点自身产生（内生），也可能沿边传播（外生），验证（verify）能以一定成本发现并修复错误，但验证器本身不完美（有检出率和误报率）；协作发生在多个组织之间，每个组织只能控制自己节点上的验证决策，因此这是一个去中心化博弈，而不是单一规划者的最优控制问题；出问题之后还需要一套"责任归因"算法，从观测到的最终损失反推最可能的错误起源和失职验证者，并按此结算各组织的净成本。

请用 Python 实现这一整套模型、求解算法、博弈求解器、责任归因算法、结算规则，以及一个具体的"跨境信用证结算"场景实例和实验脚本。

---

## 技术栈

- Python 3.10+
- `networkx`（图结构）
- `numpy`
- `pytest`（单元测试，见下方"验收标准"，这些测试是交付物的一部分，不是可选项）
- `matplotlib`（出图）
- 用 `dataclasses` 定义所有结构体，不要用裸dict传参

## 建议目录结构

```
trust_network/
  core/
    graph.py          # Node, Edge, Graph, 角色映射
    unroll.py         # 有界重提交环 -> DAG 展开
  sim/
    simulator.py       # 路径采样 + 真实错误过程 + 验证信号模拟
  solve/
    global_dp.py        # Phase2: 全局社会最优DP（含闭式baseline + 数值版）
    attribution.py       # Phase3: 责任归因 forward-backward
    settlement.py         # Phase4: g函数 + share_i + Net_i + J_social
    decentralized_game.py  # Phase5: best-response迭代 + PoA
  scenarios/
    synthetic.py        # 随机图生成器，用于扫描实验
    letter_of_credit.py    # 信用证场景实例
  experiments/
    run_sweep.py       # Phase7扫描实验
    plots.py          # Phase8出图
  tests/
    test_global_dp.py      # 含"退化到完美验证器逼近闭式解"这一关键测试
    test_attribution.py     # 含Monte Carlo校验
    test_settlement.py      # 含Σshare=1、transfer neutrality
    test_decentralized_game.py
  README.md
```

---

## 形式化模型规格（agent必须严格按此实现，不要自行改写符号或简化假设）

### 图结构

节点 `v` 分两类：
- **process节点**：参数 `alpha_v ∈ [0,1]`（自身产生错误的概率），`c_v`（验证成本），`L_v ≥ 0`（若为action节点，corrupted时执行的损失，非action节点 `L_v=0`）
- **verify节点**：参数 `delta_v`（检出率）、`epsilon_v`（误报率）、`mu_v`（检出后修复成功率）、`c_v`（验证成本）、`c_v_fix`（修复成本）、`F_v`（每次flag的摩擦成本，无论flag对错都产生）

每条边 `(u,v)`：`q_uv`（u之后路由到v的概率，Σ_v q_uv=1）、`p_uv`（已有错误从u传播到v的概率）。

每个节点有组织归属 `org(v)`，以及三个角色映射（默认等于`org(v)`，可显式覆盖）：`decision_maker(v)`（谁决定是否verify）、`payer(v)`（谁支付verify成本）、`bearer(v)`（谁默认承担该节点损失，用于归因失败时的兜底）。

**有界重提交环**：若图中存在环（如"审单不符→修改→重新提交"），必须展开：节点标识变为 `(base_id, k)`，`k`为第几次提交，`k`超过预设上限 `K_max` 时强制路由到"流程终止"吸收节点（默认判罚：损失按当前 `bearer` 全额计入）。展开后的图必须是DAG，所有下游算法都假设DAG输入。

### 错误状态与信念更新

真实状态 `X_v ∈ {0,1}`（v输出后是否corrupted）。若 `u→v`：
```
X_v = 1 - (1 - alpha_v) * (1 - p_uv * X_u)     # 真实过程（模拟器用）
```
Belief（defender不知道X_v真值，只知道概率）：
```
phi_uv(r) = alpha_v + (1 - alpha_v) * p_uv * r
```
source: `r_s = alpha_s`。

### 不完美验证器的贝叶斯更新

给定验证前信念 `r`，验证产生信号 `S ∈ {flag, clear}`：
```
P(flag | r)  = delta_v * r + epsilon_v * (1 - r)
r_flag       = delta_v * r / P(flag | r)
r_clear      = (1 - delta_v) * r / (1 - P(flag|r))
r_flag_fixed = (1 - mu_v) * r_flag      # flag后尝试修复,以mu_v概率真正清零
```

### 全局DP（社会最优，作为baseline，Phase2）

```
Q_pass(v,b,r)   = r * L_v + sum_w q_vw * V(w, b, phi_vw(r))
Q_verify(v,b,r) = c_v
    + P(flag|r) * [ F_v + sum_w q_vw * V(w, b-c_v-c_v_fix, phi_vw(r_flag_fixed)) ]
    + P(clear|r)* [        sum_w q_vw * V(w, b-c_v,        phi_vw(r_clear))       ]
    （若 b < c_v，Q_verify = +infinity，即不可行）
V(v,b,r) = min(Q_pass(v,b,r), Q_verify(v,b,r))
```
终止节点（无出边）：`V = r * L_v`（不再有verify可选，或按具体场景配置是否允许终点verify）。

`r` 用网格离散化（默认101个等距点，[0,1]区间），非格点上的 `r` 用线性插值取 `V`。

**必须同时实现闭式baseline**：令 `delta_v=1, epsilon_v=0`（完美验证器），此时上式应退化为
```
Q_verify(v,b,r) = c_v + sum_w q_vw * V(w, b-c_v, alpha_w)     # 不依赖r
```
这与理论上已经证明的分段线性解一致。**数值DP在这一退化设置下的输出，必须与解析解在所有测试点上误差 < 1e-3**，这是最重要的正确性回归测试，写入 `test_global_dp.py`。

完整分布版本 `rho_v(j)`（j为组织索引）：对每个组织分量分别套用上述贝叶斯更新公式（把标量r替换为该组织分量），更新后重新归一化使 `sum_j rho_v(j) = r_v`（边缘和仍等于标量版本的r，用作一致性检验）。

### 责任归因（方向D，Phase3）

给定一条实际路径 `v_1,...,v_T`，设 `j` 为路径中最后一个被verify的节点下标（不存在则 `j=0`），归因片段为 `w_1=v_{j+1},...,w_m=v_T`。

样本空间：`K* ∈ {w_1,...,w_m} ∪ {∅}`（∅表示终点信号是误报，根本没有真实损失）。

生存概率：`S_k = prod_{l=k}^{m-1} p_{w_l, w_{l+1}}`（从第k步起源、一路传播不中断到终点的概率）。

`F` = 路径上被调用过verify、返回clear、但真值实际上是corrupted（即漏检）的节点集合。

要求实现 forward-backward 风格的posterior decoding，输出联合后验 `P(K*, F | 观测)`，观测包括：终点loss-discovery信号（本身也套用上面delta/epsilon模型）、路径上每个verify节点实际的flag/clear记录。

**必须实现的校验**：用模拟器生成 N≥10000 条随机路径及其观测，统计真实 `(K*,F)` 的经验分布，与算法输出的后验做对比，报告KL散度和top-1命中率，写入 `test_attribution.py`，作为可运行的验证脚本而非仅打印数字。

### 结算函数（Phase4）

`g` 函数接口：输入后验 `P(K*,F|观测)`，输出 `share_i(v)`（i为组织，v为发生损失的节点），要求 `sum_i share_i(v) = 1` 对任意输入恒成立。默认实现：`K*` 对应组织获得比例份额（正比于后验概率质量），`F`中每个verify节点对应组织获得可配置比例的"失职份额"，`K*=∅`时全部份额判给 `bearer(v)`。

```
Net_i     = sum_{payer(v)=i} c_v * x_v  +  sum_v L_v * X_v * share_i(v)
J_social  = sum c_v * x_v  +  sum_v L_v * X_v
```

**必须实现的校验**：替换 `g` 为另一个实现（例如全部判给bearer的平凡实现），重新计算 `J_social`，两次结果必须完全一致（transfer neutrality），只有各 `Net_i` 的分布不同，写入 `test_settlement.py`。

### 去中心化博弈（方向B，Phase5）

组织 `i` 的策略 `pi_i` 只能决定 `org(v)=i` 的节点是否verify，其余节点的verify结果由其他组织当前策略给出（作为外生环境传入局部DP）。

两种目标函数：
```
J_i_selfish = E[ sum_{org(v)=i} L_v * X_v ]
J_i_resp    = E[ Net_i ]     # 接入Phase4的share_i
```

跨组织边（`org(u) != org(v)`）上的三种协议：
- **协议0（黑箱）**：v对u是否verify过一无所知，只能用org(u)的历史verify频率做先验
- **协议1（证书）**：v能看到u是否verify过的二元标记，据此精确选择 `phi_uv(r)` 还是 `alpha_v`（若u验证过，等价于r被reset为0后再传播）
- **协议2（可验证证书）**：与协议1效果相同（本版本先不建模伪造，留空接口即可，命名为 `verified_certificate`，实现与协议1相同但预留后续替换点）

Best-response迭代：轮流固定其他组织策略、对组织i的局部节点重新求解局部最优（复用Phase2 DP，把决策空间限制在 `org(v)=i` 的节点上），直到策略不再变化；若检测到策略集合出现循环（连续两轮出现过的历史状态），报告"未收敛"并返回振荡序列，不要死循环。

PoA计算：`PoA = J_equilibrium / J_social_optimal`，对(协议0/1/2) x (selfish/resp) 六种组合分别输出为一个表格。

---

## 场景实例（letter_of_credit.py）

按以下节点序列构建图（具体参数取合理估计值，在代码注释中标注为synthetic，不需要真实数据）：

```
卖方单证准备(process, org=seller)
  -> 货代订舱(process, org=freight_forwarder)
  -> 出口报关(process, org=customs_export)
  -> 通知行初审(verify, org=advising_bank)
  -> 开证行审单(verify, org=issuing_bank)
       -> [分支: 相符 -> 进口清关; 不符点 -> 卖方修改单据重新提交(回到"卖方单证准备"，计入重提交计数)]
  -> 进口清关(process, org=customs_import)
  -> 买方收货(此节点即terminal loss-discovery, org=buyer)
  -> [可选分支: 买方申诉 -> 保险理赔(verify, org=insurer)]
```

角色标注要求：至少显式设置一处 `decision_maker(v) != bearer(v)`（例如：检验费由卖方支付但决定权/受益方是买方，或审单决策在银行但错误放款的最终损失部分转嫁买方），并在README里注明这一处是用来验证"决策权与责任分离处系统性验证不足"这一预测的关键配置。

重提交上限 `K_max=3`。

---

## 交付物与验收标准

1. 上述目录结构完整代码
2. `pytest` 全部通过，其中以下四项测试是硬性验收标准，不能省略或简化：
   - 完美验证器退化情形下数值DP逼近闭式解（误差<1e-3）
   - 归因算法Monte Carlo校验（N≥10000，报告KL散度与top-1命中率的具体数字，不是断言"pass"就行）
   - `sum_i share_i(v) = 1` 恒成立
   - transfer neutrality（更换g实现，J_social不变）
3. `experiments/run_sweep.py` 能跑出Phase7里列出的至少这些结果：协议(0/1/2)×目标(selfish/resp)的PoA表格；信用证场景下的PoA数值
4. `experiments/plots.py` 产出至少一张PoA对比图
5. README.md 说明每个模块对应的理论概念、如何跑测试、如何跑实验、如何解读输出

## 实现顺序（严格按此顺序，不要跳阶段并行开发）

`core → sim → solve/global_dp（含单测）→ solve/attribution（含单测）→ solve/settlement（含单测）→ solve/decentralized_game → scenarios/synthetic → scenarios/letter_of_credit → experiments`

理由：后面每一层都依赖前面正确性已验证的模块，尤其是 `global_dp` 的闭式退化测试必须先通过，否则后续所有结果都不可信。
