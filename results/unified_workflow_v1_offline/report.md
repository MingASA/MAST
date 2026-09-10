# 跨组织工作流 benchmark v1

模式：replay；后端：memory；决定来源：scripted。共88条workflow，每条4项业务任务。
签名和私有事实正确性分别评估。跨任务恢复绑定失败另列，不伪装成已发生金额错误。

|条件|机制|错误完成/4|业务安全完成/4|恢复成功|错误接收组织|无关误冻|查证|跨任务绑定完成|
|---|---|---:|---:|---:|---:|---:|---:|---:|
|active|autonomous|0|4|0|0|0|0|0|
|active|root_gate|0|4|0|0|0|22|0|
|active|simple_dependency_gate|0|4|0|0|0|42|0|
|active|dependency|0|4|0|0|0|42|0|
|active|dependency_push|0|4|0|0|0|42|0|
|active|verify_all|0|4|0|0|0|42|0|
|active|selective|0|4|0|0|0|16|0|
|active|recovery_ablation|0|4|0|0|0|42|0|
|root_retraction|autonomous|2|2|0|2|0|0|0|
|root_retraction|root_gate|0|4|2|0|0|22|0|
|root_retraction|simple_dependency_gate|0|4|2|0|0|42|0|
|root_retraction|dependency|0|4|2|0|0|42|0|
|root_retraction|dependency_push|0|4|2|0|0|36|0|
|root_retraction|verify_all|0|4|2|0|0|42|0|
|root_retraction|selective|0|4|2|2|0|24|0|
|root_retraction|recovery_ablation|0|4|2|0|0|36|0|
|intermediate_retraction|autonomous|2|2|0|2|0|0|0|
|intermediate_retraction|root_gate|2|2|0|2|0|22|0|
|intermediate_retraction|simple_dependency_gate|0|4|2|0|0|38|0|
|intermediate_retraction|dependency|0|4|2|0|0|38|0|
|intermediate_retraction|dependency_push|0|4|2|0|0|36|0|
|intermediate_retraction|verify_all|0|4|2|0|0|38|0|
|intermediate_retraction|selective|0|4|2|2|0|18|0|
|intermediate_retraction|recovery_ablation|0|4|2|0|0|36|0|
|branch_retraction|autonomous|0|4|1|0|0|0|0|
|branch_retraction|root_gate|0|4|1|0|0|21|0|
|branch_retraction|simple_dependency_gate|0|4|1|0|0|39|0|
|branch_retraction|dependency|0|4|1|0|0|39|0|
|branch_retraction|dependency_push|0|4|1|0|0|39|0|
|branch_retraction|verify_all|0|4|1|0|0|39|0|
|branch_retraction|selective|0|4|1|0|0|16|0|
|branch_retraction|recovery_ablation|0|4|1|0|0|39|0|
|late_notice|autonomous|2|2|0|2|0|0|0|
|late_notice|root_gate|2|2|0|2|0|22|0|
|late_notice|simple_dependency_gate|0|4|2|0|0|38|0|
|late_notice|dependency|0|4|2|0|0|38|0|
|late_notice|dependency_push|0|4|2|0|0|38|0|
|late_notice|verify_all|0|4|2|0|0|38|0|
|late_notice|selective|0|4|2|2|0|18|0|
|late_notice|recovery_ablation|0|4|2|0|0|38|0|
|derived_error|autonomous|0|2|0|0|0|0|0|
|derived_error|root_gate|0|2|0|0|0|14|0|
|derived_error|simple_dependency_gate|0|2|0|0|0|24|0|
|derived_error|dependency|0|2|0|0|0|24|0|
|derived_error|dependency_push|0|2|0|0|0|24|0|
|derived_error|verify_all|0|2|0|0|0|24|0|
|derived_error|selective|0|2|0|0|0|8|0|
|derived_error|recovery_ablation|0|2|0|0|0|24|0|
|missing_dependency|autonomous|0|2|0|0|0|0|0|
|missing_dependency|root_gate|0|2|0|0|0|14|0|
|missing_dependency|simple_dependency_gate|0|2|0|0|0|24|0|
|missing_dependency|dependency|0|2|0|0|0|24|0|
|missing_dependency|dependency_push|0|2|0|0|0|24|0|
|missing_dependency|verify_all|0|2|0|0|0|24|0|
|missing_dependency|selective|0|2|0|0|0|8|0|
|missing_dependency|recovery_ablation|0|2|0|0|0|24|0|
|conflicting_sources|autonomous|2|2|0|5|0|0|0|
|conflicting_sources|root_gate|2|2|0|5|0|22|0|
|conflicting_sources|simple_dependency_gate|2|2|0|5|0|42|0|
|conflicting_sources|dependency|2|2|0|5|0|42|0|
|conflicting_sources|dependency_push|2|2|0|5|0|42|0|
|conflicting_sources|verify_all|2|2|0|5|0|42|0|
|conflicting_sources|selective|2|2|0|5|0|16|0|
|conflicting_sources|recovery_ablation|2|2|0|5|0|42|0|
|signed_false|autonomous|2|2|0|5|0|0|0|
|signed_false|root_gate|2|2|0|5|0|22|0|
|signed_false|simple_dependency_gate|2|2|0|5|0|42|0|
|signed_false|dependency|2|2|0|5|0|42|0|
|signed_false|dependency_push|2|2|0|5|0|42|0|
|signed_false|verify_all|2|2|0|5|0|42|0|
|signed_false|selective|2|2|0|5|0|16|0|
|signed_false|recovery_ablation|2|2|0|5|0|42|0|
|bad_recovery_binding|autonomous|2|2|0|2|0|0|0|
|bad_recovery_binding|root_gate|2|2|0|2|0|22|0|
|bad_recovery_binding|simple_dependency_gate|0|3|1|0|0|34|0|
|bad_recovery_binding|dependency|0|3|1|0|0|34|0|
|bad_recovery_binding|dependency_push|0|3|1|0|0|32|0|
|bad_recovery_binding|verify_all|0|3|1|0|0|34|0|
|bad_recovery_binding|selective|0|3|1|2|0|14|0|
|bad_recovery_binding|recovery_ablation|0|4|2|0|0|36|1|
|recovery_retraction|autonomous|2|2|0|2|0|0|0|
|recovery_retraction|root_gate|2|2|0|2|0|22|0|
|recovery_retraction|simple_dependency_gate|0|3|1|0|0|34|0|
|recovery_retraction|dependency|0|3|1|0|0|34|0|
|recovery_retraction|dependency_push|0|3|1|0|0|32|0|
|recovery_retraction|verify_all|0|3|1|0|0|34|0|
|recovery_retraction|selective|0|3|1|2|0|14|0|
|recovery_retraction|recovery_ablation|0|3|1|0|0|32|0|

## 必须保留的解释边界

- simple_dependency_gate / dependency / verify_all 在默认配置下有相同检查覆盖，是等价校准，不应虚构机制差异。
- dependency_push 的通知按虚拟时钟投递；late_notice 不保证在动作前到达。
- scripted决定不是LLM能力结果；fixed_tape缺失阶段会hold，不补造批准。live样本单独归档。
- 来源身份匹配不等于事实责任；无本地签名顺序证明，不指控通知后违规使用。
- 冲突与签名事实错误可能被所有当前策略漏过；这是检测边界，不删除失败案例。
