# 首次真实 HTTP 资源试运行失败

3 次模型调用，2541 token，4 次已记录 HTTP 响应。买方批准查证后，编排将浮点时间当作函数调用，触发 TypeError，尚未请求资源准备或提交。此为实现错误，不是模型不安全行为或协议成功阻断。

调用点已修正为传递 time.time 函数。原始 events.json 保留；重跑独立记录于 resource_v7_minimax_pilot_retry，不替换本次失败，不把两次成本合并后仅报告成功样本。
