# 离线恢复闭环验证

本目录不产生真实模型调用；使用固定脚本决策验证签名证据、撤销、派生重建、receiver 重决策和动作门禁。

- 初始账单结果：REQUEST_EVIDENCE；旧 freight 未执行。
- 无关交付时间任务：COMPLETED，继续完成。
- 恢复账单结果：COMPLETED，新 total 291ada63f2fd604ee1c1d48bf46516ef96f8667258c0aa3ca5026c9c943db045。
- 旧撤销保留：True；旧 total 仍阻断：True。
- 事件账本校验：True；责任结论：undetermined。

该结果证明协议闭环在离线固定决策下可执行，不增加真实模型效果样本，也不证明跨物理主机部署、物理副作用或责任归因。
