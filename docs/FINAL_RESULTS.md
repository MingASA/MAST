# Final unified live benchmark

This document is the public result summary for the unified L0–L4 live benchmark. The complete public archive is [`../results/final_unified_live_v1_combined_20260911/`](../results/final_unified_live_v1_combined_20260911/), with the detailed report at [`report.md`](../results/final_unified_live_v1_combined_20260911/report.md).

The benchmark used one immutable plan with 300 main workflows and 50 ablations. It covered three graph topologies, propagation faults, delayed notices, authority-confirmed repair, and fact/evidence ablations. 344 workflows produced final results; 6 remained `unknown` because the audit pause occurred after an attempt had started but before a final result existed. Unknown workflows remain in the fixed denominator and are not counted as safe completion.

The main matrix shows the protocol's central effect:

| Layer | Completed / planned | Unsafe completion | Correct completion | Unrelated retention | Propagated handoffs | Confirmed repair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| L0 | 60/60 | 87/240 (36.2%) | 144/240 (60.0%) | 144/144 (100.0%) | 242 | 0/12 |
| L1 | 59/60 | 87/240 (36.2%) | 141/240 (58.8%) | 141/144 (97.9%) | 236 | 0/12 |
| L2 | 59/60 | 74/240 (30.8%) | 140/240 (58.3%) | 140/144 (97.2%) | 196 | 0/12 |
| L3 | 59/60 | 46/240 (19.2%) | 138/240 (57.5%) | 138/144 (95.8%) | 153 | 0/12 |
| L4 | 58/60 | 0/240 (0.0%) | 144/240 (60.0%) | 138/144 (95.8%) | 0 | 6/12 |

`Unsafe completion` measures a task that completed with a faulty business basis; lower is better. `Correct completion` measures business utility; a hold or block is safe handling but is not a completion. `Unrelated retention` measures how many unaffected tasks kept a completion opportunity.

The final anomaly audit separates protocol behavior from infrastructure failures. After affected workflows were rerun, invalid decisions, invalid outcomes, provider-failure decisions, and worker errors were all zero. Fifty-eight tampered-handoff signature rejections were expected security-gate behavior. Four budget-exhaustion stops were recorded as availability loss. In the L4 confirmed-repair live cases, agents submitted 10 of 12 recovery requests and 6 of 12 affected tasks completed after authority confirmation and descendant rebuilding; the other four stopped when the workflow budget was exhausted.

The evidence supports local dependency containment, signed handoff accountability, and authority-bound recovery. It does not establish factual truth for a valid but false signed claim, legal responsibility accuracy, or production network reliability. Fixtures and business effects are synthetic; the process backend models isolated organizations on one host with virtual time and synchronous authority queries.

The archive contains the fixed plan, aggregate and task-level data, layer/case/topology summaries, paired differences, descriptive intervals, traceability projections, anomaly audit, and PNG/PDF figures. `manifest.json` verifies the 43 public data files by SHA256.
