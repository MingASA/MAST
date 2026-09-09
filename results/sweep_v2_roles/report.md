# 优先级2：逐节点角色消融

按展开后的每一个节点分别干预；两个银行节点各4个提交实例，共8处。共24个配置（包括8份相同baseline）、288个起点行。相同baseline只实际求解一次并复用，b/c独立求解。

|节点|决策方|付费方|默认承担方|该节点L|
|---|---|---|---|---:|
|['export_bank_review', 0]|advising_bank|seller|buyer|0.0|
|['issuing_review', 0]|issuing_bank|issuing_bank|buyer|0.0|
|['export_bank_review', 1]|advising_bank|seller|buyer|0.0|
|['issuing_review', 1]|issuing_bank|issuing_bank|buyer|0.0|
|['export_bank_review', 2]|advising_bank|seller|buyer|0.0|
|['issuing_review', 2]|issuing_bank|issuing_bank|buyer|0.0|
|['export_bank_review', 3]|advising_bank|seller|buyer|0.0|
|['issuing_review', 3]|issuing_bank|issuing_bank|buyer|0.0|

所有节点的(a)/(b)/(c)最差已发现均衡PoA均约2.638268，检查比均为0，没有向随机图1.09–1.16靠拢。
但这不意味着所有起点都不变：出口方银行k=0或k=1完全对齐时，selfish全检查起点收敛到更差结果，见下表。其余起点未出现超过1e-9的成本/检查比变化。
关键结构限制：这些审单节点L=0，当前bearer只在loss节点结算时使用。因此(b)是收益函数上的无效干预，不足以识别“决策责任分离”的因果效应。(c)对出口方银行真正改变的是payer：从卖方补贴变为银行自己付费，可能减少验证。不能把没有改善归因于已证实的链条深度影响；链深度等仍未单独消融。

|变化节点|协议|起点/目标|baseline PoA|完全对齐PoA|baseline检查比|完全对齐检查比|
|---|---|---|---:|---:|---:|---:|
|export_bank_review__0|black_box|1/selfish|1.05700626|2.27911897|0.87908317|0.10548998|
|export_bank_review__0|certificate|1/selfish|1.05700626|2.27911897|0.87908317|0.10548998|
|export_bank_review__0|verified_certificate|1/selfish|1.05700626|2.27911897|0.87908317|0.10548998|
|export_bank_review__1|black_box|1/selfish|1.05700626|1.23370308|0.87908317|0.79619819|
|export_bank_review__1|certificate|1/selfish|1.05700626|1.23370308|0.87908317|0.79619819|
|export_bank_review__1|verified_certificate|1/selfish|1.05700626|1.23370308|0.87908317|0.79619819|

以下完整表对每个节点、每个协议与目标给出(a)/(b)/(c)三行：

|节点|协议|目标|消融|observed PoA|检查比|
|---|---|---|---|---:|---:|
|export_bank_review__0|black_box|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__0|black_box|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__0|black_box|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__0|black_box|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__0|black_box|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__0|black_box|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__0|certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__0|certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__0|certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__0|certificate|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__0|certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__0|certificate|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__0|verified_certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__0|verified_certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__0|verified_certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__0|verified_certificate|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__0|verified_certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__0|verified_certificate|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__1|black_box|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__1|black_box|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__1|black_box|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__1|black_box|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__1|black_box|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__1|black_box|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__1|certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__1|certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__1|certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__1|certificate|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__1|certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__1|certificate|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__1|verified_certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__1|verified_certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__1|verified_certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__1|verified_certificate|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__1|verified_certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__1|verified_certificate|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__2|black_box|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__2|black_box|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__2|black_box|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__2|black_box|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__2|black_box|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__2|black_box|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__2|certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__2|certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__2|certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__2|certificate|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__2|certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__2|certificate|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__2|verified_certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__2|verified_certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__2|verified_certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__2|verified_certificate|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__2|verified_certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__2|verified_certificate|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__3|black_box|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__3|black_box|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__3|black_box|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__3|black_box|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__3|black_box|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__3|black_box|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__3|certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__3|certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__3|certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__3|certificate|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__3|certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__3|certificate|selfish|fully_aligned|2.63826841|0.00000000|
|export_bank_review__3|verified_certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|export_bank_review__3|verified_certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__3|verified_certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|export_bank_review__3|verified_certificate|selfish|baseline|2.63826841|0.00000000|
|export_bank_review__3|verified_certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|export_bank_review__3|verified_certificate|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__0|black_box|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__0|black_box|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__0|black_box|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__0|black_box|selfish|baseline|2.63826841|0.00000000|
|issuing_review__0|black_box|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__0|black_box|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__0|certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__0|certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__0|certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__0|certificate|selfish|baseline|2.63826841|0.00000000|
|issuing_review__0|certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__0|certificate|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__0|verified_certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__0|verified_certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__0|verified_certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__0|verified_certificate|selfish|baseline|2.63826841|0.00000000|
|issuing_review__0|verified_certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__0|verified_certificate|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__1|black_box|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__1|black_box|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__1|black_box|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__1|black_box|selfish|baseline|2.63826841|0.00000000|
|issuing_review__1|black_box|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__1|black_box|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__1|certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__1|certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__1|certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__1|certificate|selfish|baseline|2.63826841|0.00000000|
|issuing_review__1|certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__1|certificate|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__1|verified_certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__1|verified_certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__1|verified_certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__1|verified_certificate|selfish|baseline|2.63826841|0.00000000|
|issuing_review__1|verified_certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__1|verified_certificate|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__2|black_box|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__2|black_box|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__2|black_box|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__2|black_box|selfish|baseline|2.63826841|0.00000000|
|issuing_review__2|black_box|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__2|black_box|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__2|certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__2|certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__2|certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__2|certificate|selfish|baseline|2.63826841|0.00000000|
|issuing_review__2|certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__2|certificate|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__2|verified_certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__2|verified_certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__2|verified_certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__2|verified_certificate|selfish|baseline|2.63826841|0.00000000|
|issuing_review__2|verified_certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__2|verified_certificate|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__3|black_box|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__3|black_box|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__3|black_box|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__3|black_box|selfish|baseline|2.63826841|0.00000000|
|issuing_review__3|black_box|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__3|black_box|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__3|certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__3|certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__3|certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__3|certificate|selfish|baseline|2.63826841|0.00000000|
|issuing_review__3|certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__3|certificate|selfish|fully_aligned|2.63826841|0.00000000|
|issuing_review__3|verified_certificate|resp-Proportional|baseline|2.63826841|0.00000000|
|issuing_review__3|verified_certificate|resp-Proportional|bearer_aligned|2.63826841|0.00000000|
|issuing_review__3|verified_certificate|resp-Proportional|fully_aligned|2.63826841|0.00000000|
|issuing_review__3|verified_certificate|selfish|baseline|2.63826841|0.00000000|
|issuing_review__3|verified_certificate|selfish|bearer_aligned|2.63826841|0.00000000|
|issuing_review__3|verified_certificate|selfish|fully_aligned|2.63826841|0.00000000|
