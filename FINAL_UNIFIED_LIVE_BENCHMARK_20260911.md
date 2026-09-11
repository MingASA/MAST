# 最终统一 L0–L4 live benchmark

本报告是 2026-09-11 最终统一 live 实验的发布摘要。完整公开数据、逐任务结果、异常审计、统计表和图表位于 [`results/final_unified_live_v1_combined_20260911/`](results/final_unified_live_v1_combined_20260911/)，其中 [`report.md`](results/final_unified_live_v1_combined_20260911/report.md) 是详细报告。

## 实验范围

同一份 350 项 immutable plan 运行了 300 条主实验和 50 条消融，覆盖 L0–L4 协议层、三类拓扑、故障传播、迟到通知、确认修订恢复和事实/证据消融。由于审计暂停时有 6 条调用没有最终结果，最终统计为 344 条 completed、6 条 unknown；unknown 保留在固定任务分母中，不被当作安全完成。

结果合并遵循逐 workflow overlay 规则：先修复模型 claim-ref 契约，再重跑瞬时 provider/network 失败，最后重跑剩余动作契约异常。原始异常和重跑覆盖记录在 `mechanism_network_audit.json`；worker 私有目录没有复制进公开汇总。

## 主矩阵结果

| 层 | 完成/计划 | 错误完成/计划任务 | 正确完成/计划任务 | 无关任务保留/计划无关 | 传播交接 | 确认修订恢复 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| L0 | 60/60 | 87/240 (36.2%) | 144/240 (60.0%) | 144/144 (100.0%) | 242 | 0/12 |
| L1 | 59/60 | 87/240 (36.2%) | 141/240 (58.8%) | 141/144 (97.9%) | 236 | 0/12 |
| L2 | 59/60 | 74/240 (30.8%) | 140/240 (58.3%) | 140/144 (97.2%) | 196 | 0/12 |
| L3 | 59/60 | 46/240 (19.2%) | 138/240 (57.5%) | 138/144 (95.8%) | 153 | 0/12 |
| L4 | 58/60 | 0/240 (0.0%) | 144/240 (60.0%) | 138/144 (95.8%) | 0 | 6/12 |

错误完成率从 L0 的 36.2% 降至 L4 的 0%；错误交接也从 242 降至 0。L4 的 12 个受影响任务中，10 个真实 Agent 请求了恢复，6 个完成了确认修订后的重建和最终动作；另外 4 个在 workflow 预算耗尽时停止，属于可用性损失，不是协议拒绝。无关分支仍保留了 138/144 个完成机会，其余为模型 hold。

## 异常归因

- 初始 23 条 workflow 的 24 个非法 claim-ref 结果来自模型/适配器契约不一致，修复后重跑；最终 `invalid_decisions=0`、`invalid_outcomes=0`、`worker_errors=0`。
- 46 条 workflow 遇到 54 次瞬时 provider failure；增加一次受限传输重试后全部完成，最终 `provider_failure_decisions=0`。失败 attempt 的 journal 和 2 次未知 usage 仍保留计数。
- 58 次 `tampered_handoff` 签名拒绝是预期安全门禁，属于机制正常工作。
- 4 次 `budget_exhausted` 是保守停机，单独计入可用性，不能解释为安全收益或机制错误。

这些结果支持协议在跨组织依赖闭包、局部冻结、绑定恢复和证据审计上的机制收益；它们没有证明签名有效的错误事实会自动被识别，也没有证明真实网络部署的认证、加密、竞态和持久化 SLA。

## 可复核产物

公开汇总包含 aggregate、task metrics、分层/场景/拓扑拆分、配对差异、描述性区间、追溯投影、异常审计以及 PNG/PDF 图表。`manifest.json` 对 43 个公开文件逐项做 SHA256 校验，最终归档核对无 hash mismatch。代码入口为 [`scripts/analyze_final_live_combined.py`](scripts/analyze_final_live_combined.py) 和 [`scripts/run_final_live_v1.py`](scripts/run_final_live_v1.py)。
