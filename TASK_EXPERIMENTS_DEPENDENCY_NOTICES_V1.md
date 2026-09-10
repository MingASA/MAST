# 实验交接：主动通知与恢复二次失效

先读 MECHANISM_DEPENDENCY_NOTICES_V1.md。沿用 TASK_EXPERIMENTS_CLOSURE_V3.md 的研究边界。此任务不授权付费调用，不扩大 MiniMax live 矩阵。

## 实现状态

已完成核心算法、持久化worker、`guarded_handoff`、`pump_notifications`、独立通知审计，以及v3恢复前沿二次失效处理。你主要做实验接线与结果分析，不需要另造撤销/恢复协议。

现有35条 closure v3矩阵没有自动启用通知；应先按原交接完成该矩阵。通知实验用新目录、新协议名，不能覆盖或合并旧结果。

## 离线通知实验

在相同合法初始交接、相同撤销事件和同一固定Agent提议下比较：

1. 完整依赖查证，登记路径但不投递主动通知；
2. 相同查证 + 主动通知；
3. 主动通知 + autonomous freshness，只作“消息迟到时会失败”的诊断消融，不当作生产候选。

所有臂都通过 guarded_handoff 或等价worker操作登记初始与恢复后新声明的路径。停用push时只停用pump，不删除签名依赖、交接证据或共享结构检查。不要让source或coordinator在不同臂拥有不同的私有状态。

两类错误位置：分叉前中间声明、仅单分支中间声明。每类配两种通知时序：在下游动作前到达、在动作后才到达；共12条脚本workflow即可。声明数值可表面一致，错误是发行者已正式撤回的声明仍被使用，不能说模型发现了新的事实错误。

用既有MessageBus控制notice/ACK的投递时间。动作时刻独立固定，**不能总是先完全drain通知，再让Agent行动**。晚到条件应真实保留通知窗口；truth只由评估器读取。对纯接口调通可使用pump；正式delay重放通过call适配器/MessageBus安排接收，原notice的内容、ID和验签规则不能被改写。

记录：撤销时刻→实际签收时刻→下游引用/转发/动作；错误触达组织/分支/距离；被blocked的动作；不安全完成；通知、ACK、重复包、协议RPC和验证查询成本。将模型调用与协议RPC分开：本阶段模型calls/token都为0。

重要预期：通知及时到达时可能让下游无需查询就因本地负面证据阻断；晚到时push-only可能失败，push+closure仍须依靠查询。若通知没有减少传播或只是增加消息，应如实报告，不通过调整动作顺序制造收益。

## 恢复二次失效实验

保持同一恢复提议，在一个后代已重建后，由其发行者再次撤销新claim；另一分支的新claim保持有效。新包交接仍使用guarded_handoff，确保新ID有相应的通知路径。

检查：invalidated_replacements正确定位；失效包不能留在replacement_map；recovery_complete为false；无关usable_completed保留；不重新签出同一已撤销ID；重新修订时必须用新的offer/envelope，最终动作重新进入gate。

不要在看到requires_replan后偷偷生成正确fact或自动批准。脚本修订明确标注controlled/scripted；真实模型判断留待批准的live方案。

## 边界与审计

复用 `test_propagation_notice.py` 的重复、环路、通知先到、丢失ACK重试、重启、非法scope与事务回滚案例，不再做完整网络故障模拟器。将通知receipt与后续local_head结合，检验通知后继续使用能否被追溯。没有ACK只能输出unacknowledged，不能判定某组织漏通知有责。

交付独立report、metrics、mechanism_cases、原始签名交换/事件链与源码hash，说明哪些结论来自固定时序、哪些来自边界反例；不与旧live样本混合。若计划进一步真实模型验证，先提交明确的组织拓扑、操作次序、模型决定上限和token估算，等待用户决定。
