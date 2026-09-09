# Checkpoint 2026-09-09：扩大多轮实验与恢复证据定向 pilot

本 checkpoint 保存当前阶段的代码、实验结果和下一步决策边界。之前的
`CHECKPOINT_2026-09-09_RECOVERY_V5.md` 保留不变；本文件记录其后的扩大实验和 v6 定向 pilot。

## 当前结论

机制的程序控制部分已经出现稳定的正向结果：在本阶段的 6 个
`hidden_revoke` workflow 中，`verify_all` 和 `dependency` 都是 6/6 在动作前拦截受控的
revoked root，autonomous 基线是 0/6 拦截、6/6 不安全完成。恢复链路已经可以被真实模型完整走通，
但真实模型在旧/新来源并存和恢复契约下的 hold 仍是主要瓶颈；当前不能把恢复比例外推成生产可靠性。

责任追踪可以准确报告“收到的控制变更后仍使用旧声明且没有记录到消费者通知”的证据状态，
但现有证据不足以直接判定责任主体、恶意意图或损失归因。因此总体目标中的“降低错误传播、
在错误后控制恢复、保留可审计证据”已有小样本支持；“准确有效追责”目前完成的是证据定位，
还没有完成责任归因。

## 扩大多轮真实模型实验

运行命令：

```text
.venv/bin/python -m trust_network.demo.run_reliability_multiround \
  --out results/next_agent_multiround_expanded_v1 \
  --env-file /home/cjy/cyberagent/.env \
  --repeats 6
```

MiniMax-M3；active 和 hidden_revoke 各 6 个 workflow，分别运行 autonomous、verify_all、
dependency，合计 36 个策略 workflow。共 89 次模型决定、93 次 provider 尝试、0 次 provider
failure。原始目录生成 1097 个文件，hash 完整性检查全部通过；每个 workflow 都有 run record、
evaluation 和 accountability 记录。

| condition | strategy | N | 安全完成 | 不安全完成 | 程序拦截 | 恢复成功 | 模型 hold | 查证次数 | 已知 token |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| active | autonomous | 6 | 6 | 0 | 0 | — | 0 | 0 | 34,884 |
| active | verify_all | 6 | 6 | 0 | 0 | — | 0 | 30 | 37,956 |
| active | dependency | 6 | 5 | 0 | 0 | — | 1 | 20 | 34,214 |
| hidden_revoke | autonomous | 6 | 0 | 6 | 0 | 0 | 0 | 0 | 38,146 |
| hidden_revoke | verify_all | 6 | 3 | 0 | 6 | 3 | 3 | 36 | 82,884 |
| hidden_revoke | dependency | 6 | 1 | 0 | 6 | 1 | 5 | 22 | 65,209 |

策略汇总：

- autonomous：12 个 workflow 中安全完成 6、不安全完成 6；hidden recovery 0/6；73,030 token，0 次查证。
- verify_all：安全完成 9/12；hidden recovery 3/6；120,840 token，66 次查证。
- dependency：安全完成 6/12；hidden recovery 1/6；99,423 token，42 次查证。
- 三种策略的无关任务均为 6/6 完成；旧声明在本地串行 fixture 中最多传播 2 跳。
- accountability 的 36 个结果中，30 个为 `no_fault_conclusion`，6 个识别为
  `used_after_controlled_change_without_recorded_notice`；这 6 个责任状态仍为
  `undetermined`。

原始报告、指标、代表性机制案例和统计 posthoc 分析：

- [扩大实验报告](results/next_agent_multiround_expanded_v1/report.md)
- [扩大实验指标](results/next_agent_multiround_expanded_v1/metrics.json)
- [原始实验目录](results/next_agent_multiround_expanded_v1)
- [代表性完整恢复案例](results/next_agent_multiround_expanded_v1/mechanism_cases.md)
- [Wilson 95% 描述性区间分析](results/next_agent_multiround_expanded_v1_analysis/report.md)

统计分析没有新增模型调用。每个 cell 的 N=6，区间较宽，只用于当前方向判断，不能宣称生产
错误率或跨部署效果。

## v6 恢复证据定向 pilot

扩大实验显示恢复协调器需要看到签名的 replacement offer 和协调器登记新来源的签名事件。
已将这两项证据作为标准恢复输入的一部分接入，然后运行 2 个 autonomous、2 个 dependency
workflow；没有重抽旧结果。

运行目录：[results/next_agent_recovery_model_pilot_v6](results/next_agent_recovery_model_pilot_v6)

- 4 个 workflow，10 次模型决定、10 次 provider 尝试、0 次 provider failure。
- 原始文件 144 个，hash 完整性检查全部通过。
- autonomous：2/2 不安全完成，作为基线符合预期。
- dependency：1/2 完成完整恢复；该条轨迹包含程序拦截、来源替换、派生声明重建、receiver
  重决策和最终安全完成。
- dependency 的另一条轨迹在初始协调阶段 hold，模型把公开 manifest 的来源语义误读为需要
  buyer 提供 component source，因而没有进入恢复；这属于模型可用性失败，不被计为安全完成。

报告：[v6 report](results/next_agent_recovery_model_pilot_v6/report.md)，指标：
[v6 metrics](results/next_agent_recovery_model_pilot_v6/metrics.json)。该 pilot 只证明修正后的
恢复输入在一条符合条件的真实模型轨迹中走通，不能证明恢复率已经改善到稳定水平。

## 已保存的实现与验证

当前实现已经包含：

- 有序的 `WorkflowController` 事件控制和 hash chain；
- 基于权威私有业务状态签发新来源声明的 worker；
- replacement offer 签名及协调器登记新来源的签名事件；
- receiver recovery envelope 校验；
- 按新父声明验证并重新签名派生声明的通用 worker；
- 恢复后的 coordinator 和 receiver 真实模型重决策；
- accountability 对消费者通知、旧声明使用和证据边界的区分；
- 原始模型请求/响应、usage、运行记录、评估、责任审计和 hash manifest 保存。

全量测试最近一次结果：`119 passed`。

仓库没有有效 Git 元数据：根目录的 `.git` 不是可用 Git repository，因此当前 checkpoint 是
文件形式保存，不能报告为 Git commit。

## 下一步边界

下一步应把 v6 已验证的 replacement offer + coordinator registration 固化为恢复协议的标准
公共证据，并针对初始协调器对来源语义的误读做一次预先规定的定向小 pilot。完成该定向修复并
观察到若干独立成功/失败轨迹后，再决定是否值得进行新的大规模付费实验。新的大规模付费扩展或
改变核心研究方向前，需要用户作出新的决定。

