# 可复现实验摘要

所有参数均为 synthetic。Observed PoA 为多个初始策略找到的纯策略均衡中最差成本与全信息社会最优之比；不是对所有均衡的穷举，也不是一般博弈的全局 PoA 证明。
分母由精确观测树求解，并与 10001 点 DP 对照，误差必须小于 1e-3。协议0的路由和共享预算可见，跨组织检查记录隐藏。

| 场景 | 协议 | 目标 | 均衡成本 | 社会最优 | Observed PoA | 检查比 | 收敛起点 |
|---|---|---|---:|---:|---:|---:|---:|
| synthetic (7) | black_box | selfish | 1.1617 | 1.0023 | 1.1590 | 0.500000 | 2/2 |
| synthetic (7) | black_box | resp | 1.1617 | 1.0023 | 1.1590 | 0.500000 | 2/2 |
| synthetic (7) | certificate | selfish | 1.1617 | 1.0023 | 1.1590 | 0.500000 | 2/2 |
| synthetic (7) | certificate | resp | 1.1617 | 1.0023 | 1.1590 | 0.500000 | 2/2 |
| synthetic (7) | verified_certificate | selfish | 1.1617 | 1.0023 | 1.1590 | 0.500000 | 2/2 |
| synthetic (7) | verified_certificate | resp | 1.1617 | 1.0023 | 1.1590 | 0.500000 | 2/2 |
| synthetic (11) | black_box | selfish | 1.0750 | 0.9574 | 1.1229 | 0.500000 | 2/2 |
| synthetic (11) | black_box | resp | 1.0750 | 0.9574 | 1.1229 | 0.500000 | 2/2 |
| synthetic (11) | certificate | selfish | 1.0750 | 0.9574 | 1.1229 | 0.500000 | 2/2 |
| synthetic (11) | certificate | resp | 1.0750 | 0.9574 | 1.1229 | 0.500000 | 2/2 |
| synthetic (11) | verified_certificate | selfish | 1.0750 | 0.9574 | 1.1229 | 0.500000 | 2/2 |
| synthetic (11) | verified_certificate | resp | 1.0750 | 0.9574 | 1.1229 | 0.500000 | 2/2 |
| synthetic (23) | black_box | selfish | 1.1369 | 1.0434 | 1.0896 | 0.500000 | 2/2 |
| synthetic (23) | black_box | resp | 1.1369 | 1.0434 | 1.0896 | 0.500000 | 2/2 |
| synthetic (23) | certificate | selfish | 1.1369 | 1.0434 | 1.0896 | 0.500000 | 2/2 |
| synthetic (23) | certificate | resp | 1.1369 | 1.0434 | 1.0896 | 0.500000 | 2/2 |
| synthetic (23) | verified_certificate | selfish | 1.1369 | 1.0434 | 1.0896 | 0.500000 | 2/2 |
| synthetic (23) | verified_certificate | resp | 1.1369 | 1.0434 | 1.0896 | 0.500000 | 2/2 |
| letter_of_credit (0) | black_box | selfish | 5.0717 | 1.9224 | 2.6383 | 0.000000 | 2/2 |
| letter_of_credit (0) | black_box | resp | 5.0717 | 1.9224 | 2.6383 | 0.000000 | 2/2 |
| letter_of_credit (0) | certificate | selfish | 5.0717 | 1.9224 | 2.6383 | 0.000000 | 2/2 |
| letter_of_credit (0) | certificate | resp | 5.0717 | 1.9224 | 2.6383 | 0.000000 | 2/2 |
| letter_of_credit (0) | verified_certificate | selfish | 5.0717 | 1.9224 | 2.6383 | 0.000000 | 2/2 |
| letter_of_credit (0) | verified_certificate | resp | 5.0717 | 1.9224 | 2.6383 | 0.000000 | 2/2 |

归因校验 N=12000；条件 KL=0.000712；top-1=0.872833。

这些结果检验指定参数下的机制行为。责任规则不保证改善均衡；协议1/2在无伪造模型下应一致。
