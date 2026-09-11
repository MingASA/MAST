# Architecture

MAST models a business workflow as a graph of independent organizations. Each organization has a private state, receives only its local message view, and proposes actions through a shared runtime contract. The runtime controls which claims can be accepted, forwarded, verified, or executed.

## Claim graph

Claims form a directed acyclic graph. A derived claim names its parent claims; a handoff names the recipient and the claims being transferred. In signed mode, an organization signs the claim and the handoff, and the recipient returns a signed receipt. Each organization maintains its own view of received claims, revocations, disputes, and accepted actions.

The source of a business fact remains authoritative for that fact. A valid signature proves who issued a statement and whether the statement was changed. It does not prove that the business fact is true.

## Runtime flow

1. An issuer creates a claim from local business state.
2. The sender transfers the claim set through a recipient-bound handoff.
3. The recipient verifies the handoff, records a receipt, and exposes only its local view to its Agent.
4. The Agent proposes `proceed`, `verify`, or `hold` with a structured action payload.
5. The worker checks the action contract, claim dependencies, authority state, signatures, and recipient binding before applying the simulated business effect.
6. A revocation or dispute updates the local graph and can trigger targeted notices along the registered handoff path.
7. A confirmed source revision can rebuild only the affected descendants, after which each rebuilt action passes a fresh gate.

The Agent is therefore a decision-maker inside the protocol, not the authority that bypasses it. Model decisions, program rejections, transport failures, and budget stops are recorded as separate outcomes.

## Protocol layers

| Layer | Added capability | Purpose |
| --- | --- | --- |
| L0 | Ordinary messages, logs, and model-directed checks | Unmediated baseline |
| L1 | Signed claims, explicit dependencies, signed handoffs, receipts, and local invalidation | Integrity and verifiable provenance |
| L2 | L1 plus remote root-authority queries before action | Detect root revocation |
| L3 | L1 plus dependency-closure queries and dependency-scoped blocking | Detect intermediate failures while limiting freeze scope |
| L4 | L3 plus path-bound dispute notices, authority-confirmed fact repair, descendant rebuilding, and fresh rechecks | Contain propagation and recover safely |

The benchmark also includes matched ablations for notices, fact evidence, recovery, coarse freezing, and an alternate verification policy.

## Main components

- `trust_network/core/`: graph and claim primitives.
- `trust_network/demo/claim_channel.py`: signed claim and handoff gateway using Ed25519.
- `trust_network/demo/propagation_notice.py`: dependency-scoped notice delivery and receipts.
- `trust_network/demo/fact_evidence.py`: authority-bound fact evidence and audit records.
- `trust_network/demo/dispute_protocol.py`: dispute propagation and confirmed revision lifecycle.
- `trust_network/benchmark/layered/`: layered engine, durable worker backend, fixture plan, scoring, and final-run tooling.
- `trust_network/benchmark/contribution/`: freeze-scope, topology, evidence-projection, and responsibility-boundary controls.
- `trust_network/demo/provider.py`: optional OpenAI-compatible MiniMax adapter with bounded retry and sanitized traces.
- `trust_network/tests/`: unit, process-parity, benchmark, adapter, and contract tests.

## Security and accountability boundaries

The protocol limits what an organization may accept and what evidence it can present to another organization. It does not infer intent, prove a fact merely because it is signed, or assign legal blame from a trace alone. When evidence is missing, inconsistent, expired, or ambiguous, the evaluator records an undetermined result rather than manufacturing an attribution.
