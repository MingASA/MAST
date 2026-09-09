# Live pilot v1 机制审阅

基于checkpoint `cf504bc`、正式report/metrics、6条run_record及`trust_network/benchmark/live.py`阅读。未重跑模型或测试。审阅开始时HEAD匹配、工作区干净；128 passed是实验代理报告，本次未独立复跑。

## 接受的证据

正式6条workflow、27次模型决定/尝试，无provider失败。frontier_v2有一条真实模型链完成协调器重建、中介重建、接收方重新提出verify，之后程序执行。notice_only同repeat也完成了两个重建，但最终模型hold。v1 dependency保留接口不支持和解析失败，未隐藏负例。

因此两层恢复接口确实已由真实模型走通；尚不足以证明证据绑定优于普通notice。每臂N=2，初始模型提议不同，且两臂在成功重建轨迹中的新声明摘要相同。差异主要在模型是否继续请求后续处理，而不是算出了不同的正确派生事实。

## 优先级一：verify与执行许可混在一起

唯一报告成功的frontier_v2/ repeat_00最终draft.action是verify。`_parse_receiver`对approve和verify都构造operation=approve_invoice；`_apply_actions`只对verify启用force_verify，随后run_batch可执行动作。

现有任务提示将verify描述为请求当前权威状态校验，没有明确声明“查证通过后允许直接批准”。故不能把此轨迹无条件描述为模型明确批准后完整恢复成功。它证明了已重建、模型请求核验和运行时随后执行。在当前runner语义下计COMPLETED可以复现，但该语义本身需要修正或明确预先约定。不要删除或事后改写原始记录，也不要把历史verify重标为approve。

最小机制修正：VERIFY只产生状态证据和下一步可用状态，不触发业务effect；COMMIT/approve显式授权特定动作。若支持“验证后自动批准”，必须单独定义approve_after_verify并在模型输入和程序契约中一致声明。不得靠读reason猜测权限。

## 优先级二：重建资格与动作资格需要分开

frontier_v2/repeat_01中介hold，理由混淆了fresh_status_check_still_required和重建可用性。notice_only/repeat_00接收方也因缺最终状态确认而hold，尽管可以选择verify。不能只归因为模型偶然保守。

`_coordinator_input`有明确“新鲜度检查只约束后续动作”的说明，`_middle_input`则只有action_authorized=false及fresh_status_check_still_required=true，缺少同等阶段语义。这是协议对模型的阶段接口不一致。

应在运行时统一给出：本轮允许的证据重建操作、确切父依赖、已满足的本地验证、下一动作尚需的验证。所有臂保持同样阶段说明；差异仅在是否有可验证任务绑定及对应执行约束。不要对本组单独追加鼓励继续的prompt。

## 范围与成本

fixture拓扑为sources→coordinator→middle→receiver，schedule→receiver。是三跳主链加独立参考任务，不是同一错误进入两个不同receiver的live fan-out。参考任务日志属于订单A的delivery_schedule，报告中的“C任务”应理解为独立任务标签，不能等同离线独立订单C与双接收方拓扑。

所有主链旧证据都传播到receiver后才执行gate，因此本pilot不能证明减少了失效后消息传播距离，更不能证明相对simple gate的containment增量。它是恢复可用性pilot。

封存的scope mismatch运行不混入正式效果指标是正确处理，但实际调用成本不能因此消失。下次总成本表应分别列正式27次与封存22次原始调用（后者由实验代理提供，本次未逐项核验），用量和重试另据原始日志核算。

## 交给实验代理的下一项任务

先不扩大样本，也不新增付费调用：

1. 澄清并实现VERIFY不执行业务effect的协议边界；加入一个必要测试：状态确认成功仍不能触发effect，只有显式approve才可以。
2. 统一三个阶段的操作语义，所有策略臂保持相同措辞；保留签名绑定消融差异。
3. 用已有27次模型输出离线重放并产生修订解释表，分别统计派生重建完成、请求验证、明确批准、实际模拟effect。标明这是新语义反事实重放，不覆盖原正式pilot。
4. 修正文档的拓扑、任务标签和recovery_status：notice_only的recovery_completed只代表重建阶段，不应与最终恢复成功混用。
5. 输出下一轮最小live方案：优先固定同一初始失败轨迹，比较同一阶段的新证据输入；若要证明fan-out，则真实接入两个下游消费者，而不是改报告名称。付费运行前由用户决定。

本轮暂不需要新增算法。最重要的是动作权限与阶段语义足够明确，否则增加样本只会重复测量歧义。
