# 多跳传播—冻结—恢复统一离线结果

36条脚本workflow，6个条件/位置×6臂。每条含A/C订单×a/b分支，共4个任务；重试不增加任务分母。新增模型调用0。
原有传播矩阵仍保留；本实验在旧证据到达各分支后tick 5撤销，恢复沿用同一批网关和同一消息总线。

|条件/位置|策略|不安全完成/4|安全完成/4|恢复成功/尝试|无关误冻|查询|
|---|---|---:|---:|---:|---:|---:|
|active/coordinator|unmediated|0/4|4/4|0/0|0|0|
|active/coordinator|simple_root_gate|0/4|4/4|0/0|0|14|
|active/coordinator|dependency|0/4|4/4|0/0|0|14|
|active/coordinator|verify_all|0/4|4/4|0/0|0|14|
|active/coordinator|recovery_ablation|0/4|4/4|0/0|0|14|
|active/coordinator|frontier_v2|0/4|4/4|0/0|0|14|
|delayed_revoke/coordinator|unmediated|1/4|2/4|0/0|0|0|
|delayed_revoke/coordinator|simple_root_gate|0/4|2/4|0/0|0|11|
|delayed_revoke/coordinator|dependency|0/4|2/4|0/2|0|12|
|delayed_revoke/coordinator|verify_all|0/4|2/4|0/2|0|12|
|delayed_revoke/coordinator|recovery_ablation|0/4|4/4|2/2|0|16|
|delayed_revoke/coordinator|frontier_v2|0/4|4/4|2/2|0|16|
|derived_error/coordinator|unmediated|0/4|2/4|0/0|0|0|
|derived_error/coordinator|simple_root_gate|0/4|2/4|0/0|0|8|
|derived_error/coordinator|dependency|0/4|2/4|0/0|0|8|
|derived_error/coordinator|verify_all|0/4|2/4|0/0|0|8|
|derived_error/coordinator|recovery_ablation|0/4|2/4|0/0|0|8|
|derived_error/coordinator|frontier_v2|0/4|2/4|0/0|0|8|
|derived_error/middle_a|unmediated|0/4|3/4|0/0|0|0|
|derived_error/middle_a|simple_root_gate|0/4|3/4|0/0|0|12|
|derived_error/middle_a|dependency|0/4|3/4|0/0|0|12|
|derived_error/middle_a|verify_all|0/4|3/4|0/0|0|12|
|derived_error/middle_a|recovery_ablation|0/4|3/4|0/0|0|12|
|derived_error/middle_a|frontier_v2|0/4|3/4|0/0|0|12|
|conflicting_sources/coordinator|unmediated|2/4|2/4|0/0|0|0|
|conflicting_sources/coordinator|simple_root_gate|2/4|2/4|0/0|0|14|
|conflicting_sources/coordinator|dependency|2/4|2/4|0/0|0|14|
|conflicting_sources/coordinator|verify_all|2/4|2/4|0/0|0|14|
|conflicting_sources/coordinator|recovery_ablation|2/4|2/4|0/0|0|14|
|conflicting_sources/coordinator|frontier_v2|2/4|2/4|0/0|0|14|
|signed_false/coordinator|unmediated|2/4|2/4|0/0|0|0|
|signed_false/coordinator|simple_root_gate|2/4|2/4|0/0|0|14|
|signed_false/coordinator|dependency|2/4|2/4|0/0|0|14|
|signed_false/coordinator|verify_all|2/4|2/4|0/0|0|14|
|signed_false/coordinator|recovery_ablation|2/4|2/4|0/0|0|14|
|signed_false/coordinator|frontier_v2|2/4|2/4|0/0|0|14|

## 追溯标签对照

- 协议违约检出：{'detected': 1, 'positive_cases': 1}
- 错误指控：{'count': 0, 'negative_cases': 3}
- 证据不足时不指控：{'correct': 3, 'eligible_cases': 3}
- 篡改/缺失发现：{'detected': 2, 'corrupt_cases': 2}
- 来源/错误转换身份定位：{'correct': 3, 'cases': 3}

这些是极小的预定义协议义务标签，不是生产准确率；来源身份定位不证明事实真假或法律责任。

## 结论与限制

- 同一流程确认：v2可在原状态上完成两层恢复；冻结v1仍受单派生限制。无关C任务继续。
- 普通notice臂在固定正确新事实下也完成恢复，因此没有证据证明v2的模型成功率更高。
- 冲突来源和签名有效但事实错误仍未解决；恢复器不会擅自给这些条件注入修正。
- v7校准仍为4条旧workflow、6个批次结果一致；不把它们当作新拓扑的live样本。
- 延迟撤销可能使已接受的旧声明在本地变为失效。本表不把此前合法接收追认为当时的错误传播；事后错误引用另计。
- 未实施完整live多轮模型pilot，也未进行大规模付费实验。
