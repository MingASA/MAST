# 真实多轮机制案例

本阶段没有出现同时满足“模型提交包含受控 revoked root 的有效账单提议、程序初始拦截、并完成补证后派生重建与恢复轮”的完整策略 workflow；没有用脚本结果补造案例。

保留的部分恢复尝试：hidden_revoke 中有 0 个 workflow 签发了 replacement source，但未完成派生 total 重建。请从各 workflow 的 `run_record.json`、`events.json`、`model_calls/` 和 `recovery.error` 复核原始失败阶段。
