# 第四轮：Online Reliability交付

已实现运行时Reliability Policy、私有授权证据场景、三组共用业务Agent/查证工具、可执行费用预算和可重放审计。完整定义与执行前预算见[PREFLIGHT_v4.md](PREFLIGHT_v4.md)。用户授权后已完成36个MiniMax真实实验run，34个正常结束、2个失败。[真实实验结论](results/reliability_v4_minimax/interpretation.md)。

核心变化：模型的pass先经过程序gate，只有allow才会转交消息/证书或提交发运记录。Verify-All强制取得有效权威证据；Risk-Aware基于可见风险、潜在损失、验证价格、预算及可选遗漏项选择放行、查证或升级。各policy共享缓存，避免人为制造Verify-All重复查证成本。

公开单据均为MX-40B、数量10；真正批准状态留在买方组织服务中。相同公开视图包含批准与未批准两个世界，公开字段不能决定真假。业务worker、在线policy、authority及事后评估有明确的数据接口；本地模式提供上下文隔离，远程适配器支持组织独立部署，但没有声称单机提供OS安全隔离。

工程验证：原50项加新增12项，共62项通过（4.97秒）。209个历史结果/测试文件哈希保持不变。[验证记录](results/reliability_v4_preflight/validation.json)。复用了Certificate、Bayes更新、attribution及settlement，原DP/game保留。遗漏责任在线项明确为operational approximation，默认主对照关闭；开启可实际改变gate决策。

离线始终PASS夹具的真实服务查证次数为Autonomous 0、Verify-All 4、Risk-Aware 2；不安全完成分别2/4、0/4、1/4。Risk-Aware节约50%查证成本，但放过低风险未授权反例，尚未取得接近Verify-All的不安全完成率。此为实现与边界检查，不能冒称MiniMax行为实验或机制有效性证明。[完整夹具记录](results/reliability_v4_preflight/report.md)。

真实实验中，Autonomous/Verify-All/Risk-Aware不安全完成分别为1/12、0/11、0/11，查询成本30/33/24；已授权完成5/6、4/6、5/6。Risk-Aware查询成本低27.27%，但没有触发程序干预，其阻断由模型完成，尚不能证明policy增量效果。Verify-All实际撤销了两次未授权pass。全批97次业务调用尝试、95次已记录API请求、125598个已记录token；失败用量缺失。36个单元、424条审计事件核验通过，所有匹配单元的首步可见输入一致。没有追加批次或重跑失败。
