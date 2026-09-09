# C 阶段真实多组织多轮 pilot

运行命令：

```bash
.venv/bin/python -m trust_network.demo.run_reliability_multiround \
  --out results/next_agent_multiround \
  --env-file /home/cjy/cyberagent/.env \
  --repeats 2
```

本次固定规模为 2 个条件 × 2 次重复 × 3 个策略臂，共 12 个策略 workflow；每个 workflow 最多 4 次业务模型决定。原始模型请求/响应在各 run 的 `model_calls/`，签名事件和批次在 `events.json`、`batches/`，独立事件真值在各条件 fixture 的 `evaluation_truth.json`。

本阶段实际记录 24 次模型决定、24 次 provider 尝试，其中 13 次收到响应、11 次 provider failure；没有观察到完整的旧声明程序拦截后恢复成功轨迹。该负结果和收尾修正记录在 [report.md](report.md) 与 [mechanism_cases.md](mechanism_cases.md)。

`raw_integrity_manifest.json` 保存 314 个原始证据文件的哈希。上一阶段 B 的结果仍保存在 [`../next_agent_experiments/`](../next_agent_experiments/)；本目录没有覆盖它。
