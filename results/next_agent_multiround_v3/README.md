# C 阶段修正后真实多组织多轮 pilot

运行命令：

```bash
.venv/bin/python -m trust_network.demo.run_reliability_multiround \
  --out results/next_agent_multiround_v3 \
  --env-file /home/cjy/cyberagent/.env \
  --repeats 2
```

本轮仍为 2 个条件 × 2 次重复 × 3 个策略臂，共 12 个 workflow；每个 workflow 最多 4 次业务模型决定。实际记录 25 次模型决定、25 次 provider 尝试，其中 24 次收到响应、1 次 provider failure。

正向结果：1 个 hidden_revoke dependency workflow 的真实账单提议带有已撤销 freight 根，并在动作前被程序返回 `REQUEST_EVIDENCE`；同一轮 autonomous 有 1 个不安全完成。active 条件下 Verify-All 和 dependency 各完成 2/2 个账单 workflow。负向结果：恢复轮协调 Agent 选择 hold，未完成派生 total 重建和恢复动作；没有把恢复成功补写进结果。

原始模型轨迹在各 run 的 `model_calls/`，签名事件和批次在 `events.json`、`batches/`，独立真值在条件 fixture 的 `evaluation_truth.json`。`raw_integrity_manifest.json` 保存原始证据哈希；[report.md](report.md) 和 [mechanism_cases.md](mechanism_cases.md) 保存分析结果。v2 的接线失败结果保留在 [`../next_agent_multiround_v2/`](../next_agent_multiround_v2/)，没有混入本轮统计。
