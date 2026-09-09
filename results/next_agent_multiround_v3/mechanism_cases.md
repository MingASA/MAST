# 真实多轮机制案例

本阶段没有出现同时满足“模型提交包含受控 revoked root 的有效账单提议、程序初始拦截、并完成补证后派生重建与恢复轮”的完整策略 workflow；没有用脚本结果补造案例。

实际观察到的部分拦截案例：

条件：`hidden_revoke`；重复：`1`；策略：`dependency`。完整记录：`/home/cjy/wuxing/results/next_agent_multiround_v3/hidden_revoke/repeat_01/dependency`。
受控 revoked root：`9c1252836f05d3301302fd4a58f4067bc9cb03209d44df25ece096a560f97dff`。该账单输出带有该 root，程序返回 `REQUEST_EVIDENCE`，没有执行模拟账单动作。
阶段 `initial` 输出：[{"proposal": "invoice-A", "result": null, "failed_roots": ["9c1252836f05d3301302fd4a58f4067bc9cb03209d44df25ece096a560f97dff", "f6577a539542c51decbe6e8b8eaa126f4d6cdfe753c89ff7aaade99f7bda5d77"], "action": "REQUEST_EVIDENCE"}, {"proposal": "schedule-reference", "result": {"simulated": true, "proposal": "schedule-reference", "operation": "forward"}, "failed_roots": [], "action": "COMPLETED"}]；查证次数：3。
恢复结果：replacement source=已签发；派生 total=未重建；恢复轮错误：{"type": "ValueError", "message": "coordinator did not rebuild derived claim"}。

保留的部分恢复尝试：hidden_revoke 中有 1 个 workflow 签发了 replacement source，但未完成派生 total 重建。请从各 workflow 的 `run_record.json`、`events.json`、`model_calls/` 和 `recovery.error` 复核原始失败阶段。
