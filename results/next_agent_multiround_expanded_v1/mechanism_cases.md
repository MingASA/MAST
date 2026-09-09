# 真实多轮机制案例

条件：`hidden_revoke`；重复：`0`；策略：`dependency`。完整 workflow 记录：`/home/cjy/wuxing/results/next_agent_multiround_expanded_v1/hidden_revoke/repeat_00/dependency`。

旧来源摘要：`f62e96c95a439e27accf5b1396f654220edf81b3b135f61ce14c011230459654`；新来源摘要：`6334ffc9d3a887701ae6c3276c603f402812fca4f4c848b7294e4f181a68cd52`；重建 total：`56b39d4172d06671a862ab1d87de4889783d23a8a5c065a4921b7c4183484b52`。

阶段结果：

|阶段|提议/结果|查证次数|
|---|---|---:|
|initial|[{"proposal": "invoice-A", "result": null, "failed_roots": ["f62e96c95a439e27accf5b1396f654220edf81b3b135f61ce14c011230459654", "f82adbc8b3349133d96daf6bf34af4a04c9e41bd8d6d950492b0c8e3444c50a4"], "action": "REQUEST_EVIDENCE"}, {"proposal": "schedule-reference", "result": {"simulated": true, "proposal": "schedule-reference", "operation": "forward"}, "failed_roots": [], "action": "COMPLETED"}]|3|
|recovery|[{"proposal": "invoice-A", "result": {"simulated": true, "proposal": "invoice-A", "operation": "approve_invoice"}, "failed_roots": [], "action": "COMPLETED"}]|4|

恢复链：carrier 签发新来源并签署 replacement_offer → receiver 通过 prepare_recovery 接收信封 → coordinator 在新来源上重新签发派生 total → receiver 重新获得模型决定 → 再次查证和动作合约检查。`action_authorized` 仍为 false，旧 revoked 记录保留。
