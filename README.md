# MAST

### Cross-organization Agent safety and accountability

MAST is a research prototype for coordinating autonomous Agents across organizational boundaries. It studies how signed claims, explicit dependencies, scoped notices, authority-bound recovery, and verifiable handoffs can reduce the spread of faulty business decisions while preserving a defensible execution history.

The repository contains a runnable protocol model, isolated organization workers, deterministic benchmark infrastructure, an optional MiniMax live adapter, and the final unified L0–L4 benchmark archive.

## Why this project exists

An Agent can make a locally reasonable decision from a statement that is stale, revoked, misrouted, or factually wrong. In a multi-organization workflow, that statement can be copied into new claims and reach downstream execution before anyone discovers the original problem. Ordinary logs can describe what participants say happened, but they do not necessarily prove which signed statement was transferred, acknowledged, or used.

MAST treats the workflow as a graph of dependent claims. The runtime checks the graph at action boundaries, freezes only the affected dependency closure, and binds recovery to an authoritative replacement fact. The Agent remains responsible for the business choice, while the worker enforces the protocol contract.

## What is implemented

- Signed claims, revocations, recipient-bound handoffs, and receipts.
- Root and complete dependency-closure verification before actions.
- Path-bound dispute notices with delivery and acknowledgment audits.
- Authority-confirmed source revision using a private fact reference.
- Bound descendant rebuilding followed by fresh action checks.
- In-memory and isolated persistent-process backends.
- Deterministic delay, branching, topology, fault, and evidence-projection benchmarks.
- Separate accounting for unsafe completion, safe blocking, model hold, provider failure, budget stop, and unknown outcome.
- Optional MiniMax calls with a bounded retry policy and provider-attempt journals.

## Protocol layers

| Layer | Runtime capability |
| --- | --- |
| L0 | Ordinary messages and logs |
| L1 | Signed claims, explicit dependencies, handoffs, receipts, and local invalidation |
| L2 | L1 plus remote root-authority checks |
| L3 | L1 plus complete dependency-closure checks and local scoped blocking |
| L4 | L3 plus path-bound notices, authority-confirmed repair, descendant rebuilding, and fresh rechecks |

The architecture is described in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Final benchmark snapshot

The final public archive contains 300 main workflows and 50 matched ablations. There were 344 completed workflows and 6 `unknown` workflows. The main matrix reduced unsafe completion from 87/240 (36.2%) at L0 to 0/240 at L4, and reduced faulty propagated handoffs from 242 to 0. L4 retained 138/144 unrelated completion opportunities and completed 6/12 affected tasks after authority-confirmed repair; four additional recovery paths stopped at the workflow budget.

| Layer | Unsafe completion | Correct completion | Unrelated retention | Faulty propagated handoffs |
| --- | ---: | ---: | ---: | ---: |
| L0 | 36.2% | 60.0% | 100.0% | 242 |
| L1 | 36.2% | 58.8% | 97.9% | 236 |
| L2 | 30.8% | 58.3% | 97.2% | 196 |
| L3 | 19.2% | 57.5% | 95.8% | 153 |
| L4 | 0.0% | 60.0% | 95.8% | 0 |

Unsafe completion is the primary safety measure and is lower-is-better. Correct completion measures business utility; blocking a faulty task is safe but does not count as a correct completion. Read the full interpretation, anomaly classification, paired data, and figures in [`docs/FINAL_RESULTS.md`](docs/FINAL_RESULTS.md) and [`results/final_unified_live_v1_combined_20260911/report.md`](results/final_unified_live_v1_combined_20260911/report.md).

## Installation

Python 3.10 or newer is required.

```bash
git clone https://github.com/MingASA/MAST.git
cd MAST
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install -e '.[test]'
```

## Quick start

Run the complete test suite:

```bash
.venv/bin/pytest -q
```

Run the deterministic layered benchmark into a new output directory:

```bash
.venv/bin/python -m trust_network.benchmark.layered \
  --mode offline \
  --output results/local_layered_offline
```

The output directory must not already exist. Offline execution does not call a model. The checked-in final result is already available under `results/final_unified_live_v1_combined_20260911/`.

## Optional live model execution

Live execution is optional and is not required to run the protocol or tests. The MiniMax adapter reads an env-style file containing:

```text
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://...
CAI_MODEL=MiniMax-M3
```

Do not commit the file or provider responses containing credentials. Live runs require a completed offline preflight and validation artifact, use the isolated process backend, and archive every provider attempt. See `scripts/run_final_live_v1.py` and `trust_network/demo/provider.py` before starting a new run.

## Repository layout

```text
trust_network/core/                 graph and claim primitives
trust_network/demo/                 protocol components and model adapter
trust_network/benchmark/layered/    L0–L4 benchmark engine and scoring
trust_network/benchmark/contribution/ controlled topology and evidence controls
trust_network/tests/                automated tests
examples/                           synthetic business fixtures
results/final_unified_live_v1.../   final public aggregate and figures
docs/                               stable architecture and result notes
```

## Scope and limitations

The benchmark uses synthetic fixtures and simulated business effects. The process backend isolates organizations on one host; virtual time and synchronous authority queries do not represent a production network SLA. A valid signature does not establish factual truth, and an evidence trace does not by itself establish legal responsibility. The final archive also preserves `unknown` outcomes and budget stops instead of treating them as successful or unsafe completions.

## Tests and contributions

Changes should preserve the action contract, information boundaries, fixed-denominator scoring, and archive integrity checks. Run `.venv/bin/pytest -q` before submitting a change. For questions or proposed changes, open an issue or pull request in the [GitHub repository](https://github.com/MingASA/MAST).

## License

No license has been declared for this repository yet.
