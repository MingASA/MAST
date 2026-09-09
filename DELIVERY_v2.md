# 第二轮交付

三个优先级均已完成。用户在成本估算后回复continue，批准的两组各15次MiniMax批次已全部结束；失败run如实保留，没有补跑替换。

原24项测试文件未作修改；当前42项测试通过。第一轮51个已记录文件的SHA-256一致，包括原测试与历史结果。见 [测试记录](results/round2_audit/tests_release.txt)、[保留检查](results/round2_audit/preservation_check.json)。

## 1. 机会性遗漏责任：本次有效，但没有观察到过度验证

新增 `ProportionalWithOmission`、后验遗漏机会推断和精确期望检查次数指标。

本轮144个起点行全部收敛，汇总72组。下表为黑箱协议较差已发现均衡，另外两个协议在本轮汇总数值相同；完整表没有省略任何场景或权重。

| 场景 | w_omit=0：PoA / 检查比 | 0.5 | 1 | 2 |
|---|---:|---:|---:|---:|
| 随机种子7 | 1.159031 / 0.5 | 1.159031 / 0.5 | 1.159031 / 0.5 | 1.000000 / 1 |
| 随机种子11 | 1.122889 / 0.5 | 1.122889 / 0.5 | 1.122889 / 0.5 | 1.122889 / 0.5 |
| 随机种子23 | 1.089577 / 0.5 | 1.089577 / 0.5 | 1.089577 / 0.5 | 1.000000 / 1 |
| 信用证 | 2.638268 / 0 | 1.057006 / 0.879083 | 1.006474 / 1 | 1.006474 / 1 |

PoA弱单调不增，检查比弱单调不减，均存在平台；种子11基本没有变化。全部144个起点检查比最大为1，**本次没有出现超过社会最优参照的过度验证**。信用证w=1的改善伴随从不检查恢复到社会最优的检查数量，而非过度检查。这个结论仅覆盖当前权重、预算和图，不外推更强责任不会有副作用。

`w_omit=0` 与旧Proportional的责任份额、策略、逐起点PoA及检查比精确一致。例：信用证PoA均为2.6382684059797974、检查比均为0；随机种子7的较差均衡PoA均为1.159030562970304、检查比均为0.5。第一轮没有保存检查比，此处是补算，不能称为从旧文件读取。

任务书的原始全局分数公式与“w=0精确退化”有数学冲突。本实现保留旧规则的联合状态加权与空起源兜底，再追加遗漏分数；偏离、反例、可用性判定和分母平局规则见 [MODEL_DECISIONS](MODEL_DECISIONS.md)。这不是未经声明地替换旧结算规则。

输出：

- [完整汇总与结论](results/sweep_v2_omission_final/report.md)
- [144个起点](results/sweep_v2_omission_final/by_start.csv)、[72组汇总](results/sweep_v2_omission_final/summary.csv)
- [逐起点零权重精确回归](results/sweep_v2_omission_final/zero_weight_regression.csv)
- [权重与检查比图](results/sweep_v2_omission_final/omission_tradeoff.png)
- [旧规则新增指标补算](results/sweep_v2_baseline/summary.md)

`results/sweep_v2_omission/`保留首次报告校验未完成的中间输出。当时误将逐起点结果与历史最差均衡汇总比较，校验主动中止；修正后重新写入上述final目录，没有覆盖原结果。

## 2. 角色消融：最差均衡不改善，部分较好起点恶化

实际DAG有8个不一致节点：`export_bank_review`和`issuing_review`各自的k=0、1、2、3。每处分别生成(a)原状、(b)仅bearer对齐、(c)payer与bearer均对齐，其他节点与全部数值参数、拓扑不变。

24个独立配置（包含8份相同baseline），288个起点结果，144组汇总。相同baseline求解缓存复用；16个b/c变体独立求解。

所有节点的(a)/(b)/(c)最差均衡PoA均约2.638268，检查比均为0，**没有向随机图1.09–1.16靠拢**。但是全检查起点的selfish结果有以下变化，三个协议相同：

| 完全对齐节点 | baseline PoA | 对齐后PoA | baseline检查比 | 对齐后检查比 |
|---|---:|---:|---:|---:|
| export_bank_review, k=0 | 1.057006 | 2.279119 | 0.879083 | 0.105490 |
| export_bank_review, k=1 | 1.057006 | 1.233703 | 0.879083 | 0.796198 |

这里不能得出“现实中的责任对齐无效”的因果结论：八个审单节点自身L=0，而当前bearer只在损失发生节点被使用，因此(b)在收益函数上是无效干预。对出口方银行做(c)时，实际生效的是把付费方从卖方改为银行，可能消除原补贴并减少检查。没有把buyer_receipt损失迁移到银行来制造预期效果。链条深度等因素仍未在本轮单独识别。

[节点清单及全部(a)/(b)/(c)对比](results/sweep_v2_roles/report.md) · [独立JSON配置](results/sweep_v2_roles/configs) · [288个起点](results/sweep_v2_roles/by_start.csv) · [变化起点](results/sweep_v2_roles/changed_starts.json)

## 3. MiniMax重复实验：30个run完成执行，分布已产出

保持事故链、组织档案、公开单据与ground truth不变，两组各15次；温度0.2、0.5、0.8各5次。批次内签名密钥固定，全部输入哈希与162份签名校验通过。

|组合|正常返回|运行错误|业务完成|升级人工|拒绝|完成率（正常返回样本）|描述性95%区间|
|---|---:|---:|---:|---:|---:|---:|---|
|protocol0 × selfish|14|1|10|4|0|71.4%|45.4%–88.3%|
|protocol2 × resp|14|1|12|2|0|85.7%|60.1%–96.0%|

共22个业务完成、6个人工升级、2个运行报错。人工升级细分为：无效改单3次、补证未解决2次、模型主动升级1次。未观察到执行器判定的不安全完成或私有标记泄露命中；这不证明真实贸易合规，也不证明没有其他泄露。

第二组的完成次数更多，但样本量小，描述性区间较宽，且同时改变协议与目标，不能据此证明证书或责任机制的独立因果效果。正常返回样本的完成率不把运行错误混入业务结局，可能受API/响应失败选择偏差影响。报告同时给出全部30个run的状态和温度分层。

**resp仍是第一轮的业务目标提示词**，保持场景不变的重复实验没有接入新的遗漏责任提示词，因此本批次不是ProportionalWithOmission在真实Agent上的效果验证。

### 用量与失败处理

执行前已告知两组各15次的预计用量：约210调用/379410 token（按历史六组合均值约195调用/358225 token）；确认记录见[授权记录](results/round2_audit/minimax_batch_authorization.json)。

实际日志记录 **162次组织决策调用、286590 token**。它们包含失败run在报错前已记录的片段，但不包含失败后无法取得usage的请求，不能当作最终账单。2个报错run分别保存错误记录及已有的`.jsonl.interrupted`片段，没有用成功重跑替换。

### 产出

- [批次汇总](results/minimax_batch_v2/report.md) 与 [分层解读](results/minimax_batch_v2/interpretation.md)
- [逐run CSV](results/minimax_batch_v2/runs.csv)、[结局/重提交/调用分布JSON](results/minimax_batch_v2/aggregate.json)
- [检查范围频率CSV](results/minimax_batch_v2/check_frequencies.csv)：按原文计频，不事后合并近义表达
- [行为分布图](results/minimax_batch_v2/behavior_distribution.png)
- [输入与签名验证](results/minimax_batch_v2/validation.json)、[固定配置与输入哈希](results/minimax_batch_v2/manifest.json)

这批结果仍然只是行为分布的经验观测，不是数学模型参数的拟合值，参数校准是后续工作。
