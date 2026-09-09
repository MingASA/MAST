# Checkpoint 2026-09-09：标准恢复证据协议与 v7 pilot

本文件记录 `CHECKPOINT_2026-09-09_EXPANDED_V1.md` 之后的协议固化和真实模型小 pilot。
此前实验目录和 checkpoint 均保留不变。

## 实现变更

新增 `recovery-evidence-v1` 协议接口：

- `build_recovery_evidence` 在协调器本地验证签名 recovery envelope、replacement offer、
  replacement source 和 coordinator 的本地 `received` 事件；
- bundle 用 `evidence_id` 绑定 exact recovery task、旧新 root、派生重建要求和四个签名 artifact；
- `rebuild_derived_claim` 在任何写入前强制重新验证 bundle，缺少协调器登记、签名被篡改或任务绑定
  不一致都会 fail closed；
- 调度器通过 `reliability_build_recovery_evidence` 显式完成“新来源已登记”的保证，再把同一 bundle
  交给真实模型和派生声明 worker；
- 离线恢复脚本、单元测试和真实模型 runner 已切换到该接口。

## v7 真实模型小 pilot

固定设置：只用 `hidden_revoke`，autonomous 为基线，dependency 为机制臂；每臂 2 个 workflow，
每个 workflow 最多 4 次模型决定，总上限 16 次；hold、provider failure 和无效结构不重抽。

运行目录：[results/next_agent_recovery_model_pilot_v7](results/next_agent_recovery_model_pilot_v7)

模型为 MiniMax-M3，共 4 个 workflow、12 次模型决定、12 次 provider 尝试、0 次 provider failure。
原始目录 151 个文件，hash 全部有效；4 个事件链和 accountability 报告全部存在且有效。

| 策略 | N | 安全完成 | 不安全完成 | 程序拦截 | 来源替换 | 派生重建 | receiver 重决策 | 恢复成功 | 模型决定 | 查证次数 | 已知 token |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| autonomous | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 11,588 |
| dependency | 2 | 2 | 0 | 2 | 2 | 2 | 2 | 2 | 8 | 16 | 53,916 |

两条 dependency 轨迹均完整执行了：

```text
旧声明被程序拦截
→ 权威签发新来源
→ replacement offer 验证
→ coordinator 本地登记新来源
→ recovery-evidence-v1 生成
→ 真实模型重建 total_charge
→ 新派生声明签发并接收
→ receiver 重新 verify
→ 最终动作安全完成
```

两条 autonomous 轨迹均初始完成账单动作，未触发程序拦截，结果保持为不安全基线。dependency
没有出现模型 hold 或 parser invalid；这说明标准 bundle 消除了 v6 中暴露的恢复输入歧义，
但 N=2 只能证明接口在这两个轨迹中可走通，不能估计生产恢复率。

报告和指标：[report.md](results/next_agent_recovery_model_pilot_v7/report.md)、
[metrics.json](results/next_agent_recovery_model_pilot_v7/metrics.json)。原始模型请求、响应、
usage、运行记录、批次、事件、评估和 accountability 均在该目录中保存。

## 离线与回归验证

标准化后的离线闭环结果：初始账单 `REQUEST_EVIDENCE`，无关交付任务 `COMPLETED`，恢复账单
`COMPLETED`；旧撤销保留、旧 total 仍阻断、新 total 未阻断、事件链有效、责任状态仍为
`undetermined`。临时离线输出的 raw integrity 也通过。

全量测试：`119 passed`。

## 当前判断

目前最有把握的正向结论是：程序 gate 能阻止 revoked 依赖继续触发受保护动作，且标准化签名恢复
证据可以让真实模型在本 pilot 中完成受约束的派生重建和重新决策。机制的主要剩余问题是成本和
模型稳定性：v7 dependency 每个 workflow 使用 8 次模型决定、16 次查证、53,916 token；
样本很小，不能据此宣称普遍改善。

追责方面仍只能准确定位证据链、控制变更和旧声明使用；没有消费者通知时，责任主体和损失归因
仍然是 `undetermined`。

## 下一步边界

协议级接线和小规模真实模型验证已完成。下一步可以在不改变核心方向的前提下设计更严格的
预注册恢复稳定性实验，例如固定更多独立 workflow、预先规定 hold/成功分类和成本指标。该实验
会扩大真实模型调用规模，开始前需要用户作出新的决定；在此之前不再自动扩大付费规模。

仓库根目录 `.git` 不是有效 Git repository，因此本 checkpoint 为文件保存，不能报告为 Git commit。

