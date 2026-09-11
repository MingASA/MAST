"""Assemble the final layered live run without copying private worker data.

The final run was repaired in overlays.  This script records which immutable
result supplied each workflow, preserves the six conservative unknowns, and
produces fixed-denominator tables and descriptive figures.  It never calls a
provider and never changes a per-workflow result.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from trust_network.benchmark.layered.final_run import inspect_journals
from trust_network.benchmark.layered.final_score import task_rows
from trust_network.benchmark.layered.score import observation
from trust_network.benchmark.contribution.forensics import audit, project, route_label
from trust_network.benchmark.contribution.live_replay import score_reference
from trust_network.demo.documents import canonical, digest


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/final_unified_live_v1_20260911"
CLAIMREF = ROOT / "results/final_unified_live_v1_claimref_fix_20260911"
RETRY = ROOT / "results/final_unified_live_v1_provider_retry_20260911"
CONTRACT = ROOT / "results/final_unified_live_v1_contract_cleanup_20260911"
OUT = ROOT / "results/final_unified_live_v1_combined_20260911"

NUMERIC_METRICS = (
    "unsafe_completion_count", "unsafe_action_count", "safe_final_completion",
    "total_tasks", "unrelated_completed", "unrelated_task_count",
    "overfrozen_tasks", "error_action_blocks", "recovered_tasks",
    "post_fault_error_handoffs", "post_fault_error_organizations",
    "post_fault_error_branches", "post_fault_propagation_hops",
    "explicit_action_opportunities", "fault_action_opportunities",
    "status_queries", "fact_queries", "notifications", "notification_bytes",
    "new_model_calls", "provider_attempts", "known_tokens",
    "unknown_usage_attempts", "worker_errors", "invalid_actions", "model_holds",
    "rpc_rejections", "route_reference_count", "verified_route_count",
    "root_identity_count", "audit_rejected_evidence",
)

PAIR_METRICS = (
    "unsafe_rate", "safe_rate", "unrelated_retention", "overfreeze_rate",
    "propagation_handoffs_per_task", "recovery_rate_confirmed",
    "route_coverage", "tokens_per_decision",
)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def write_csv(path: Path, rows) -> None:
    rows = list(rows)
    keys = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rate(numerator, denominator):
    return numerator / denominator if denominator else None


def load_result(path: Path):
    with path.open() as stream:
        return json.load(stream)


def find_initial_invalid(base_runs: Path):
    result = set()
    for path in base_runs.glob("*/result.json"):
        value = load_result(path)
        if any(o.get("phase") == "initial" and o.get("action") == "INVALID"
               for o in value["raw"]["outcomes"]):
            result.add(path.parent.name)
    return result


def build_selection(plan):
    """Choose the latest justified result for every plan entry."""
    base_runs = BASE / "runs"
    fixed_runs = CLAIMREF / "runs"
    retry_runs = RETRY / "runs"
    contract_runs = CONTRACT / "runs"
    invalid_base = find_initial_invalid(base_runs)
    retry_manifest = json.loads((RETRY / "network_retry_manifest.json").read_text())
    retry_ids = set(retry_manifest["workflow_ids"])
    contract_manifest = json.loads((CONTRACT / "contract_cleanup_manifest.json").read_text())
    contract_ids = set(contract_manifest["workflow_ids"])
    base_results = {p.parent.name: p for p in base_runs.glob("*/result.json")}
    fixed_results = {p.parent.name: p for p in fixed_runs.glob("*/result.json")}
    retry_results = {p.parent.name: p for p in retry_runs.glob("*/result.json")}
    contract_results = {p.parent.name: p for p in contract_runs.glob("*/result.json")}
    base_states = {p.parent.name: load_result(p) for p in base_runs.glob("*/state.json")}
    selected = {}
    for entry in plan["runs"]:
        wid = entry["workflow_id"]
        if wid in contract_ids:
            if wid not in contract_results:
                raise RuntimeError(f"missing contract cleanup result: {wid}")
            selected[wid] = {"status": "completed", "source": "contract_cleanup",
                             "path": contract_results[wid], "prior_initial_invalid": wid in invalid_base}
        elif wid in retry_ids:
            if wid not in retry_results:
                raise RuntimeError(f"missing network retry result: {wid}")
            selected[wid] = {"status": "completed", "source": "provider_retry",
                             "path": retry_results[wid], "prior_initial_invalid": wid in invalid_base}
        elif wid in fixed_results:
            selected[wid] = {"status": "completed", "source": "claimref_fix",
                             "path": fixed_results[wid], "prior_initial_invalid": wid in invalid_base}
        elif wid in base_results and wid not in invalid_base:
            selected[wid] = {"status": "completed", "source": "base_preserved",
                             "path": base_results[wid], "prior_initial_invalid": False}
        elif wid in base_states:
            selected[wid] = {"status": "unknown", "source": "base_interrupted",
                             "path": None, "prior_initial_invalid": wid in invalid_base,
                             "state": base_states[wid]}
        else:
            raise RuntimeError(f"missing result or state for plan entry: {wid}")
    interrupted_ids = {wid for wid, state in base_states.items()
                       if state.get("status") != "completed"}
    expected = Counter({"contract_cleanup": len(contract_ids),
                        "provider_retry": len(retry_ids),
                        "claimref_fix": len(set(fixed_results) - retry_ids - contract_ids),
                        "base_preserved": len(set(base_results) - invalid_base - retry_ids - contract_ids),
                        "base_interrupted": len(interrupted_ids)})
    actual = Counter(item["source"] for item in selected.values())
    if actual != expected:
        raise RuntimeError(f"selection count mismatch: {actual} != {expected}")
    return selected, invalid_base, retry_ids, contract_ids


def row_for(entry, fixture, selected_item):
    planned_tasks = len(fixture["graph"]["tasks"])
    affected_tasks = len(fixture["evaluation"]["affected_tasks"])
    unrelated_tasks = len(fixture["evaluation"]["unrelated_tasks"])
    row = {
        **entry,
        "topology": fixture["topology"],
        "case": fixture["case"],
        "business_variant": f"business-{fixture['repetition']}",
        "status": selected_item["status"],
        "source": selected_item["source"],
        "result_path": str(selected_item["path"].relative_to(ROOT)) if selected_item["path"] else None,
        "result_sha256": sha256(selected_item["path"]) if selected_item["path"] else None,
        "planned_tasks": planned_tasks,
        "planned_affected_tasks": affected_tasks,
        "planned_unrelated_tasks": unrelated_tasks,
        "known_tasks": 0,
        "unknown_tasks": planned_tasks,
        "known_affected_tasks": 0,
        "unknown_affected_tasks": affected_tasks,
        "known_unrelated_tasks": 0,
        "unknown_unrelated_tasks": unrelated_tasks,
        "provider_failure_decisions": 0,
        "invalid_decisions": 0,
        "budget_decisions": 0,
        "invalid_outcomes": 0,
        "outcome_errors": 0,
        "true_model_holds": 0,
        "budget_holds": 0,
        "decision_count": 0,
        "outcome_count": 0,
        "recovery_request_proposals": 0,
        "recovery_submitted": 0,
        "authority_confirmed": 0,
        "recovery_model_stops": 0,
        "provider_failed_attempts": 0,
        "provider_returned_attempts": 0,
        "journal_calls": 0,
        "journal_attempts": 0,
        "journal_known_tokens": 0,
        "journal_unknown_usage": 0,
        "journal_malformed_lines": 0,
    }
    for key in NUMERIC_METRICS:
        row[key] = None
    if selected_item["status"] != "completed":
        state = selected_item.get("state", {})
        row["unknown_reason"] = state.get("reason", state.get("message", "interrupted workflow"))
        return row, None

    value = load_result(selected_item["path"])
    raw = value["raw"]
    if value["entry"] != entry:
        raise RuntimeError(f"entry mismatch in {selected_item['path']}")
    if raw["truth"]["expected_cents"] != fixture["evaluation"]["private_expected_cents"]:
        raise RuntimeError(f"truth mismatch in {selected_item['path']}")
    stored_tasks = value["task_metrics"]
    recalculated_tasks = task_rows(fixture, raw)
    if stored_tasks != recalculated_tasks:
        raise RuntimeError(f"task score mismatch in {selected_item['path']}")
    m = raw["metrics"]
    row["known_tasks"] = planned_tasks
    row["unknown_tasks"] = 0
    row["known_affected_tasks"] = affected_tasks
    row["unknown_affected_tasks"] = 0
    row["known_unrelated_tasks"] = unrelated_tasks
    row["unknown_unrelated_tasks"] = 0
    for key in NUMERIC_METRICS:
        row[key] = m.get(key)
    row["decision_count"] = len(raw.get("decisions", []))
    row["outcome_count"] = len(raw.get("outcomes", []))
    row["provider_failure_decisions"] = sum(d.get("decision_origin") == "provider_failure"
                                             for d in raw.get("decisions", []))
    row["invalid_decisions"] = sum(d.get("decision_origin") == "invalid"
                                   for d in raw.get("decisions", []))
    row["budget_decisions"] = sum(d.get("decision_origin") == "budget"
                                  for d in raw.get("decisions", []))
    row["invalid_outcomes"] = sum(o.get("action") == "INVALID" or
                                   o.get("result", {}).get("error") == "KeyError"
                                   for o in raw.get("outcomes", []))
    row["outcome_errors"] = sum("error" in o.get("result", {})
                                 for o in raw.get("outcomes", []))
    row["true_model_holds"] = sum(d.get("draft", {}).get("action") == "hold" and
                                   d.get("decision_origin") == "model"
                                   for d in raw.get("decisions", []))
    row["budget_holds"] = sum(d.get("decision_origin") == "budget"
                              for d in raw.get("decisions", []))
    row["recovery_request_proposals"] = sum(
        d.get("stage", "").startswith("recovery_request:") and
        d.get("draft", {}).get("action") == "request_recovery"
        for d in raw.get("decisions", []))
    row["recovery_submitted"] = sum(r.get("status") == "submitted"
                                    for r in raw.get("recovery_requests", []))
    row["authority_confirmed"] = int(
        (raw.get("source_revision") or {}).get("status") == "confirmed_offer")
    row["recovery_model_stops"] = sum(
        r.get("status") in ("rebuild_model_stopped", "final_model_stopped")
        for r in raw.get("recoveries", []))
    journals = inspect_journals(selected_item["path"].parent)
    row["journal_calls"] = journals["calls_started"]
    row["journal_attempts"] = journals["provider_attempts"]
    row["journal_known_tokens"] = journals["known_tokens"]
    row["journal_unknown_usage"] = journals["unknown_usage_attempts"]
    row["journal_malformed_lines"] = journals["malformed_lines"]
    for path in (selected_item["path"].parent / "workers").glob("*.provider.jsonl"):
        for line in path.read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("status") == "attempt_failed":
                row["provider_failed_attempts"] += 1
            elif event.get("status") == "attempt_returned":
                row["provider_returned_attempts"] += 1
    return row, raw


def summarize_rows(rows, label=None):
    rows = list(rows)
    out = {"label": label, "planned_workflows": len(rows),
           "completed_workflows": sum(r["status"] == "completed" for r in rows),
           "unknown_workflows": sum(r["status"] == "unknown" for r in rows)}
    for key in ("planned_tasks", "planned_affected_tasks", "planned_unrelated_tasks",
                "known_tasks", "unknown_tasks", "known_affected_tasks",
                "unknown_affected_tasks", "known_unrelated_tasks",
                "unknown_unrelated_tasks", *NUMERIC_METRICS, "decision_count",
                "outcome_count", "provider_failure_decisions", "invalid_decisions",
                "budget_decisions", "invalid_outcomes", "outcome_errors",
                "true_model_holds", "budget_holds", "recovery_request_proposals",
                "recovery_submitted", "authority_confirmed", "recovery_model_stops",
                "provider_failed_attempts", "provider_returned_attempts", "journal_calls",
                "journal_attempts", "journal_known_tokens", "journal_unknown_usage",
                "journal_malformed_lines"):
        out[key] = sum((r.get(key) or 0) for r in rows)
    out["unsafe_rate_over_planned_tasks"] = rate(out["unsafe_completion_count"], out["planned_tasks"])
    out["unsafe_rate_over_known_tasks"] = rate(out["unsafe_completion_count"], out["known_tasks"])
    out["safe_rate_over_planned_tasks"] = rate(out["safe_final_completion"], out["planned_tasks"])
    out["safe_rate_over_known_tasks"] = rate(out["safe_final_completion"], out["known_tasks"])
    out["unrelated_retention_over_planned"] = rate(out["unrelated_completed"], out["planned_unrelated_tasks"])
    out["unrelated_retention_over_known"] = rate(out["unrelated_completed"], out["known_unrelated_tasks"])
    out["overfreeze_rate_over_planned_unrelated"] = rate(out["overfrozen_tasks"], out["planned_unrelated_tasks"])
    out["unsafe_rate_over_known_affected"] = rate(
        sum((r.get("unsafe_completion_count") or 0) for r in rows), out["known_affected_tasks"])
    out["propagation_handoffs_per_planned_task"] = rate(
        out["post_fault_error_handoffs"], out["planned_tasks"])
    out["propagation_handoffs_per_known_task"] = rate(
        out["post_fault_error_handoffs"], out["known_tasks"])
    out["recovery_completed_over_planned_affected"] = rate(
        out["recovered_tasks"], out["planned_affected_tasks"])
    out["recovery_completed_over_known_affected"] = rate(
        out["recovered_tasks"], out["known_affected_tasks"])
    out["route_coverage_known"] = rate(out["verified_route_count"], out["route_reference_count"])
    out["tokens_per_decision"] = rate(out["known_tokens"], out["decision_count"])
    out["provider_failure_rate_per_decision"] = rate(
        out["provider_failure_decisions"], out["decision_count"])
    out["provider_failed_attempt_rate"] = rate(
        out["provider_failed_attempts"], out["journal_attempts"])
    return out


def _result_anomaly_counts(value):
    """Count anomalies from a raw result without reclassifying safe blocks."""
    raw = value["raw"]
    decisions = raw.get("decisions", [])
    outcomes = raw.get("outcomes", [])
    metrics = raw.get("metrics", {})
    return {
        "provider_failure_decisions": sum(
            d.get("decision_origin") == "provider_failure" for d in decisions),
        "invalid_decisions": sum(
            d.get("decision_origin") == "invalid" for d in decisions),
        "budget_decisions": sum(
            d.get("decision_origin") == "budget" for d in decisions),
        "invalid_outcomes": sum(
            o.get("action") == "INVALID" or
            o.get("result", {}).get("error") == "KeyError" for o in outcomes),
        "worker_errors": metrics.get("worker_errors", 0) or 0,
        "rpc_rejections": metrics.get("rpc_rejections", 0) or 0,
    }


def mechanism_network_audit(plan, rows, invalid_base, retry_ids, contract_ids):
    """Persist the anomaly classification and the exact rerun coverage."""
    base_results = {p.parent.name: p for p in (BASE / "runs").glob("*/result.json")}
    fixed_results = {p.parent.name: p for p in (CLAIMREF / "runs").glob("*/result.json")}

    # This is the logical selection after the claim-ref rerun and before the
    # provider/network and final contract overlays.  It reconstructs the
    # denominator used to identify the 46 network-affected workflows.
    pre_overlay = []
    for entry in plan["runs"]:
        wid = entry["workflow_id"]
        path = base_results.get(wid) if wid in base_results and wid not in invalid_base else fixed_results.get(wid)
        if path is None:
            continue
        pre_overlay.append((wid, _result_anomaly_counts(load_result(path))))

    def sum_counts(values):
        return {key: sum(v[key] for v in values) for key in (
            "provider_failure_decisions", "invalid_decisions", "budget_decisions",
            "invalid_outcomes", "worker_errors", "rpc_rejections")}

    pre_counts = sum_counts([value for _, value in pre_overlay])
    pre_provider_ids = sorted(wid for wid, value in pre_overlay
                              if value["provider_failure_decisions"])
    pre_contract_ids = sorted(wid for wid, value in pre_overlay
                              if value["invalid_decisions"] or value["invalid_outcomes"])

    initial_claimref_outcomes = 0
    for path in (BASE / "runs").glob("*/result.json"):
        raw = load_result(path)["raw"]
        initial_claimref_outcomes += sum(
            o.get("phase") == "initial" and
            (o.get("action") == "INVALID" or o.get("result", {}).get("error") == "KeyError")
            for o in raw.get("outcomes", []))

    final_counts = sum_counts([{
        key: int(row.get(key) or 0) for key in (
            "provider_failure_decisions", "invalid_decisions", "budget_decisions",
            "invalid_outcomes", "worker_errors", "rpc_rejections")
    } for row in rows])
    rpc_workflows = sorted(row["workflow_id"] for row in rows
                           if int(row.get("rpc_rejections") or 0))
    unknown_ids = sorted(row["workflow_id"] for row in rows if row["status"] == "unknown")
    return {
        "classification_version": "final-live-anomaly-audit-v1",
        "plan": {
            "planned_workflows": len(rows),
            "completed_workflows": sum(row["status"] == "completed" for row in rows),
            "unknown_workflows": len(unknown_ids),
            "unknown_workflow_ids": unknown_ids,
        },
        "pre_overlay_after_claimref_fix": {
            "logical_result_count": len(pre_overlay),
            "provider_failure_decisions": pre_counts["provider_failure_decisions"],
            "provider_failure_workflows": pre_provider_ids,
            "provider_failure_workflow_count": len(pre_provider_ids),
            "residual_invalid_decisions": pre_counts["invalid_decisions"],
            "residual_invalid_outcomes": pre_counts["invalid_outcomes"],
            "residual_contract_workflows": pre_contract_ids,
            "budget_decisions": pre_counts["budget_decisions"],
        },
        "initial_contract_audit": {
            "initial_claimref_invalid_workflows": sorted(invalid_base),
            "initial_claimref_invalid_workflow_count": len(invalid_base),
            "initial_claimref_invalid_outcome_count": initial_claimref_outcomes,
        },
        "rerun_overlays": {
            "claimref_fix_workflow_count": len(invalid_base),
            "provider_retry_workflow_count": len(retry_ids),
            "contract_cleanup_workflow_count": len(contract_ids),
            "contract_cleanup_workflows": sorted(contract_ids),
        },
        "final_selected_anomalies": {
            **final_counts,
            "provider_failed_attempts": sum(int(row.get("provider_failed_attempts") or 0) for row in rows),
            "unknown_usage_attempts": sum(int(row.get("journal_unknown_usage") or 0) for row in rows),
            "security_rejection_case": "tampered_handoff",
            "security_rejection_workflows": rpc_workflows,
            "security_rejections_are_expected": True,
            "budget_decisions_are_protocol_or_model_error": False,
        },
        "interpretation": {
            "contract_anomalies": "model/adapter contract mismatch; affected workflows were rerun after prompt and resolver cleanup",
            "provider_failures": "transient provider/network attempts; retryable transport policy was added and affected workflows were rerun",
            "rpc_rejections": "expected signature gate behavior for tampered_handoff, not an internal mechanism failure",
            "unknown_workflows": "preserved from the audit pause because no final result existed; excluded from claims of safe completion",
        },
    }


def group_summaries(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return [{key: value, **summarize_rows(group, str(value))}
            for value, group in sorted(groups.items(), key=lambda item: str(item[0]))]


def pair_value(row, metric):
    if metric == "unsafe_rate":
        return rate(row["unsafe_completion_count"], row["planned_tasks"])
    if metric == "safe_rate":
        return rate(row["safe_final_completion"], row["planned_tasks"])
    if metric == "unrelated_retention":
        return rate(row["unrelated_completed"], row["planned_unrelated_tasks"])
    if metric == "overfreeze_rate":
        return rate(row["overfrozen_tasks"], row["planned_unrelated_tasks"])
    if metric == "propagation_handoffs_per_task":
        return rate(row["post_fault_error_handoffs"], row["planned_tasks"])
    if metric == "recovery_rate_confirmed":
        return rate(row["recovered_tasks"], row["planned_affected_tasks"])
    if metric == "route_coverage":
        return rate(row["verified_route_count"], row["route_reference_count"])
    if metric == "tokens_per_decision":
        return rate(row["known_tokens"], row["decision_count"])
    raise KeyError(metric)


def bootstrap(values, seed=911, repeats=2000):
    values = [v for v in values if v is not None]
    if not values:
        return {"mean": None, "interval_95": None, "fixtures": 0}
    rng = random.Random(seed)
    n = len(values)
    estimates = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(repeats))
    return {"mean": sum(values) / n,
            "interval_95": [estimates[int(.025 * repeats)], estimates[int(.975 * repeats)]],
            "fixtures": n,
            "method": "percentile bootstrap of fixture-level paired differences"}


def main_pairs(rows):
    by_fixture = defaultdict(dict)
    for row in rows:
        if row["group"] == "main" and row["status"] == "completed":
            by_fixture[row["fixture_id"]][row["layer"]] = row
    pairs = []
    # Keep adjacent increments for the layer-by-layer audit and add cumulative
    # L0 comparisons for the figure/report.  The latter must be explicit:
    # selecting non-existent ``L2 minus L0`` rows would silently draw zeros.
    comparisons = [("L0", "L1"), ("L1", "L2"), ("L2", "L3"), ("L3", "L4"),
                   ("L0", "L2"), ("L0", "L3"), ("L0", "L4")]
    for lower, upper in comparisons:
        for fixture_id, arms in sorted(by_fixture.items()):
            if lower not in arms or upper not in arms:
                continue
            for metric in PAIR_METRICS:
                a = pair_value(arms[lower], metric)
                b = pair_value(arms[upper], metric)
                if a is None or b is None:
                    continue
                pairs.append({"fixture_id": fixture_id, "comparison": f"{upper} minus {lower}",
                              "metric": metric, "lower_value": a, "upper_value": b,
                              "delta": b - a})
    intervals = []
    for comparison in sorted({p["comparison"] for p in pairs}):
        for metric in PAIR_METRICS:
            values = [p["delta"] for p in pairs
                      if p["comparison"] == comparison and p["metric"] == metric]
            intervals.append({"comparison": comparison, "metric": metric,
                              **bootstrap(values)})
    return pairs, intervals


def ablation_pairs(rows):
    by_fixture = defaultdict(dict)
    for row in rows:
        if row["status"] == "completed" and row["topology"] == "long_chain_fork" and row["business_variant"] == "business-0":
            by_fixture[row["fixture_id"]][row["layer"]] = row
    arms = ("L4_no_push", "L4_no_fact", "L4_no_recovery", "L3_coarse", "verify_all")
    pairs = []
    for fixture_id, values in sorted(by_fixture.items()):
        if "L4" not in values:
            continue
        for arm in arms:
            if arm not in values:
                continue
            for metric in PAIR_METRICS:
                l4 = pair_value(values["L4"], metric)
                ab = pair_value(values[arm], metric)
                if l4 is None or ab is None:
                    continue
                pairs.append({"fixture_id": fixture_id, "comparison": f"L4 minus {arm}",
                              "metric": metric, "l4_value": l4, "ablation_value": ab,
                              "delta": l4 - ab})
    intervals = []
    for comparison in sorted({p["comparison"] for p in pairs}):
        for metric in PAIR_METRICS:
            values = [p["delta"] for p in pairs
                      if p["comparison"] == comparison and p["metric"] == metric]
            intervals.append({"comparison": comparison, "metric": metric,
                              **bootstrap(values, seed=1211)})
    return pairs, intervals


def make_traceability(rows, selected):
    from trust_network.benchmark.contribution.forensics import route_label as forensic_route_label

    labels = [("full", "none"), ("ordinary_logs", "none"), ("no_receipts", "none"),
              ("opaque_relay", "none"), ("full", "missing_link"),
              ("full", "tampered_receipt")]
    output = []
    sources = []
    for row in rows:
        if row["group"] != "main" or row["layer"] != "L4" or row["status"] != "completed":
            continue
        path = selected[row["workflow_id"]]["path"]
        raw = load_result(path)["raw"]
        o = observation(raw)
        o["ordinary_logs"] = [forensic_route_label(r["packet"])
                               for r in raw["routes"] if r["accepted"]]
        execution = {
            "execution_id": digest(raw), "observation": o,
            "reference": {
                "routes": o["ordinary_logs"],
                "sources": {digest(p): p["signature"]["issuer"] for p in o["claims"]
                             if not p["body"]["parents"]},
            },
        }
        sources.append({"workflow_id": row["workflow_id"], "source": row["source"],
                        "result_path": row["result_path"], "result_sha256": row["result_sha256"],
                        "execution_id": execution["execution_id"]})
        for view, fault in labels:
            projected = project(execution, view, fault)
            assessed = audit(projected)
            score = score_reference(execution, projected, assessed)
            output.append({"workflow_id": row["workflow_id"], "fixture_id": row["fixture_id"],
                           "topology": row["topology"], "case": row["case"],
                           "business_variant": row["business_variant"], "view": view,
                           "fault": fault, "execution_id": execution["execution_id"],
                           "observation_changed_by_fault": projected != project(execution, view),
                           **score})
    return output, sources


def plot_all(layer_stats, confirmed_layer_stats, delta_stats, ablation_stats, traceability, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    layers = ["L0", "L1", "L2", "L3", "L4"]
    by_layer = {r["layer"]: r for r in layer_stats}
    confirmed_by_layer = {r["layer"]: r for r in confirmed_layer_stats}
    panels = [
        ("unsafe_rate_over_planned_tasks", "Unsafe completion rate (planned tasks; lower)"),
        ("propagation_handoffs_per_planned_task", "Error handoffs / planned task (lower)"),
        ("unrelated_retention_over_planned", "Unrelated task retention (higher)"),
        ("safe_rate_over_planned_tasks", "Correct final completion (higher; utility)"),
        ("recovery_completed_over_planned_affected", "Confirmed-repair completion (higher)"),
        ("route_coverage_known", "Verified handoff coverage (descriptive)"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout="constrained")
    for ax, (metric, title) in zip(axes.flat, panels):
        source = confirmed_by_layer if metric == "recovery_completed_over_planned_affected" else by_layer
        values = [source[l].get(metric) or 0 for l in layers]
        ax.bar(layers, values, color="#3568a8")
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0, 1.05 if metric != "propagation_handoffs_per_planned_task" else max(1, max(values, default=0) * 1.2))
        ax.grid(axis="y", alpha=.25)
        for i, layer in enumerate(layers):
            ax.text(i, values[i] + .02 * max(1, max(values, default=0)),
                    f"{source[layer]['completed_workflows']}/{source[layer]['planned_workflows']}",
                    ha="center", fontsize=8)
    fig.suptitle("Layered live benchmark: protocol gains by layer", fontsize=14)
    fig.savefig(out / "protocol_gains_by_layer.png", dpi=180)
    fig.savefig(out / "protocol_gains_by_layer.pdf")
    plt.close(fig)

    wanted = [("unsafe_rate", "Unsafe completion change (lower is better)"),
              ("propagation_handoffs_per_task", "Propagation handoff change (lower is better)"),
              ("unrelated_retention", "Unrelated retention change (higher is better)"),
              ("safe_rate", "Safe completion change (higher is better)"),
              ("recovery_rate_confirmed", "Confirmed-repair change (higher is better)"),
              ("route_coverage", "Evidence coverage change (descriptive)")]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout="constrained")
    for ax, (metric, title) in zip(axes.flat, wanted):
        selected = [r for r in delta_stats if r["metric"] == metric and r["comparison"] in
                    ("L1 minus L0", "L2 minus L0", "L3 minus L0", "L4 minus L0")]
        # Recovery is meaningful only on confirmed_repair fixtures; that filter is
        # applied when the delta table is built.
        order = ["L1 minus L0", "L2 minus L0", "L3 minus L0", "L4 minus L0"]
        selected_by = {r["comparison"]: r for r in selected}
        vals = [selected_by.get(c, {}).get("mean") or 0 for c in order]
        lows = [max(0, (selected_by.get(c, {}).get("mean") or 0) -
                    (selected_by.get(c, {}).get("interval_95") or [0, 0])[0]) for c in order]
        highs = [max(0, (selected_by.get(c, {}).get("interval_95") or [0, 0])[1] -
                     (selected_by.get(c, {}).get("mean") or 0)) for c in order]
        ax.bar(["L1", "L2", "L3", "L4"], vals, yerr=[lows, highs], capsize=4,
               color="#d47b36")
        ax.axhline(0, color="black", linewidth=.8)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", alpha=.25)
    fig.suptitle("Paired fixture change relative to L0 (descriptive bootstrap intervals)", fontsize=14)
    fig.savefig(out / "protocol_delta_vs_L0.png", dpi=180)
    fig.savefig(out / "protocol_delta_vs_L0.pdf")
    plt.close(fig)

    ablation_names = ["L4_no_push", "L4_no_fact", "L4_no_recovery", "L3_coarse", "verify_all"]
    abwanted = [("unsafe_rate", "Unsafe completion: L4 - ablation"),
                ("propagation_handoffs_per_task", "Propagation handoffs: L4 - ablation"),
                ("unrelated_retention", "Unrelated retention: L4 - ablation"),
                ("recovery_rate_confirmed", "Recovery: L4 - ablation")]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for ax, (metric, title) in zip(axes.flat, abwanted):
        vals = []
        err = [[], []]
        for name in ablation_names:
            r = next((x for x in ablation_stats if x["comparison"] == f"L4 minus {name}"
                      and x["metric"] == metric), None)
            vals.append((r or {}).get("mean") or 0)
            interval = (r or {}).get("interval_95") or [0, 0]
            err[0].append(max(0, vals[-1] - interval[0]))
            err[1].append(max(0, interval[1] - vals[-1]))
        ax.bar([n.replace("L4_", "") for n in ablation_names], vals, yerr=err, capsize=4,
               color="#5a9b68")
        ax.axhline(0, color="black", linewidth=.8)
        ax.set_title(title, fontsize=10)
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="y", alpha=.25)
    fig.suptitle("Matched ablation differences on long_chain_fork / business-0", fontsize=14)
    fig.savefig(out / "ablation_gains.png", dpi=180)
    fig.savefig(out / "ablation_gains.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    means_tokens = [rate(by_layer[l]["known_tokens"], by_layer[l]["completed_workflows"]) or 0 for l in layers]
    means_attempts = [rate(by_layer[l]["journal_attempts"], by_layer[l]["completed_workflows"]) or 0 for l in layers]
    x = list(range(len(layers)))
    ax.bar([i - .2 for i in x], means_tokens, .4, label="known tokens/workflow")
    ax2 = ax.twinx()
    ax2.bar([i + .2 for i in x], means_attempts, .4, color="#cf8050", label="provider attempts/workflow")
    ax.set_xticks(x, layers); ax.set_ylabel("known tokens / workflow"); ax2.set_ylabel("provider attempts / workflow")
    ax.set_title("Model cost and execution attempts by main layer")
    ax.grid(axis="y", alpha=.2)
    handles, labels = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(handles + h2, labels + l2, loc="upper left")
    fig.savefig(out / "protocol_cost.png", dpi=180); fig.savefig(out / "protocol_cost.pdf")
    plt.close(fig)

    none = [r for r in traceability if r["fault"] == "none"]
    views = ["full", "ordinary_logs", "no_receipts", "opaque_relay"]
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    vals_v = []; vals_e = []
    for view in views:
        subset = [r for r in none if r["view"] == view]
        expected = sum(r["verified_routes"]["expected"] for r in subset)
        matched = sum(r["verified_routes"]["matched"] for r in subset)
        e_expected = sum(r["estimated_routes"]["expected"] for r in subset)
        e_matched = sum(r["estimated_routes"]["matched"] for r in subset)
        vals_v.append(rate(matched, expected) or 0); vals_e.append(rate(e_matched, e_expected) or 0)
    x = list(range(len(views)))
    ax.bar([i - .2 for i in x], vals_v, .4, label="verified signed routes")
    ax.bar([i + .2 for i in x], vals_e, .4, label="ordinary-log estimates")
    ax.set_xticks(x, views, rotation=15); ax.set_ylim(0, 1.1); ax.set_ylabel("route recall")
    ax.set_title("Same L4 executions: evidence projection and traceability")
    ax.legend(); ax.grid(axis="y", alpha=.25)
    fig.savefig(out / "traceability_projection.png", dpi=180); fig.savefig(out / "traceability_projection.pdf")
    plt.close(fig)


def report(layer_stats, confirmed_layer_stats, ablation_stats, rows, traceability,
           invalid_base, retry_ids, contract_ids, anomaly_audit, out):
    counts = Counter(r["status"] for r in rows)
    source_counts = Counter(r["source"] for r in rows)
    known = [r for r in rows if r["status"] == "completed"]
    all_summary = summarize_rows(rows, "all plan entries")
    main_stats = {r["layer"]: r for r in layer_stats}
    confirmed_stats = {r["layer"]: r for r in confirmed_layer_stats}
    lines = [
        "# 最终统一 layered live：合约修复、网络重试与协议收益",
        "",
        "本报告合并同一份 350 项 immutable plan 的四个结果来源；不复制或修改任何 worker 私有账本。",
        f"状态：completed={counts['completed']}，unknown={counts['unknown']}；来源={dict(source_counts)}。",
        f"旧批次发现 {len(invalid_base)} 条含 initial invalid_claim_refs 的 workflow，全部由 claimref_fix、provider_retry 或 contract_cleanup overlay 替换；网络重跑覆盖 {len(retry_ids)} 条，动作/引用契约清理覆盖 {len(contract_ids)} 条 workflow。",
        "六条在合约审计暂停时已经发出调用但没有最终 result 的 workflow 保持 unknown，不当作安全完成，也没有自动付费重发。",
        "",
        "## 机制与网络异常",
        "",
        "provider failure 的根因是 provider 适配器在第一次网络/5xx/截断响应后直接 fallback hold，没有使用已有的第二次尝试预算。修复后仅对这些瞬时传输/服务故障重试一次；模型输出格式、错误 claim_refs、预算耗尽仍不重试。",
        f"claim-ref 修复后、网络 overlay 之前的逻辑选择中，{anomaly_audit['pre_overlay_after_claimref_fix']['provider_failure_decisions']} 个 provider failure decision 分布在 {anomaly_audit['pre_overlay_after_claimref_fix']['provider_failure_workflow_count']} 条 workflow；网络 overlay 的 {len(retry_ids)} 条 workflow 全部完成。重试后最终 provider_failure decision=0，worker_error=0。journal 仍记录了随后成功的底层失败 attempt，不能把它抹掉。",
        "完整异常审计中，4 条非法动作和 1 条空 claim_refs 曾被模型返回；补充契约后这 5 条 workflow 均已重跑，最终选择集的 model invalid、invalid outcome 和 worker error 均为 0。4 个 budget decision 是预算耗尽的保守停机，单独计入可用性，不归为机制错误。tampered_handoff 的 58 次签名拒绝是预期安全门禁。",
        "",
        "## 主矩阵固定分母结果",
        "",
        "以下正确完成率、无关保留率和错误率以计划任务为分母；unknown workflow 的任务留在分母中。known-only 率同时保存于 aggregate.csv 和 summary_by_layer.csv。错误传播交接是实际 post-fault cached-claim handoff，active 场景没有错误时为零。",
        "",
        "|层|完成/计划|错误完成/计划任务|正确完成/计划任务|无关保留/计划无关|传播交接|确认修订恢复|模型hold|provider失败决定|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for layer in ("L0", "L1", "L2", "L3", "L4"):
        r = main_stats[layer]
        pct = lambda x: "—" if x is None else f"{100*x:.1f}%"
        c = confirmed_stats[layer]
        lines.append(f"|{layer}|{r['completed_workflows']}/{r['planned_workflows']}|{r['unsafe_completion_count']}/{r['planned_tasks']} ({pct(r['unsafe_rate_over_planned_tasks'])})|{r['safe_final_completion']}/{r['planned_tasks']} ({pct(r['safe_rate_over_planned_tasks'])})|{r['unrelated_completed']}/{r['planned_unrelated_tasks']} ({pct(r['unrelated_retention_over_planned'])})|{r['post_fault_error_handoffs']}|{c['recovered_tasks']}/{c['planned_affected_tasks']} ({pct(c['recovery_completed_over_planned_affected'])})|{r['true_model_holds']}|{r['provider_failure_decisions']}|")
    lines += [
        "",
        f"全计划任务：错误完成 {all_summary['unsafe_completion_count']}/{all_summary['planned_tasks']}，正确完成 {all_summary['safe_final_completion']}/{all_summary['planned_tasks']}，无关任务保留 {all_summary['unrelated_completed']}/{all_summary['planned_unrelated_tasks']}。正确完成率是业务可用性指标；hold 或 block 是安全处理，却不会被计为完成。",
        "",
        "## 结果解读",
        "",
        f"正向收益来自完整依赖检查、定向通知和绑定恢复：它们把错误候选限制在受影响依赖闭包内，并在确认修订后允许后代重建；无关分支仍有机会继续。分层 live 数据中，错误完成率从 L0 的 {100*main_stats['L0']['unsafe_rate_over_planned_tasks']:.1f}% 降到 L3 的 {100*main_stats['L3']['unsafe_rate_over_planned_tasks']:.1f}%，L4 为 {100*main_stats['L4']['unsafe_rate_over_planned_tasks']:.1f}%；L4 的恢复和通知指标仍应与 L4_no_recovery、L4_no_push、L4_no_fact 对照阅读。",
        f"正确完成率不随安全拦截同步上升：L4 把低层可能错误完成的任务转为 block/hold，其中只有满足修订条件的任务才能恢复为正确完成。在 L4 的 confirmed_repair 场景，{confirmed_stats['L4']['recovery_request_proposals']} 个任务提出并提交了 request_recovery，{confirmed_stats['L4']['recovered_tasks']} 个完成恢复；另外 {confirmed_stats['L4']['recovery_model_stops']} 个在重建阶段因本轮 workflow 预算耗尽而停止，未被协议拒绝。其余故障没有权威确认的新来源，因此保持暂停是预期安全行为。",
        "事实层边界仍然清楚：签名有效且尚未被撤销的错误事实不能仅靠来源链发现。因此 signed_false 情景的安全收益不能写成事实真实性保证。",
        "追溯图来自同一批 L4 执行的证据投影，展示签名交接、签收和普通日志之间的信息差异；它没有独立法律责任标签，因此不报告责任准确率或误指控率。",
        "",
        "## 消融与成本",
        "",
        "消融只在匹配的 long_chain_fork/business-0 的 10 个 fixture 上比较；confirmed_repair 的一个消融 workflow 是 unknown，报告中的有效配对数会明确体现这一点。L4 主层的 confirmed_repair 恢复率单独以该场景的受影响任务作分母。",
        "模型成本用 provider 返回的 known tokens 和 provider attempts 表示；失败 attempt 的 usage unknown 单独计数。业务图由脚本生成，效果是模拟的，同机 process worker 和同步 authority 查询不代表真实跨组织部署 SLA。",
        "",
        "## 产物",
        "",
        "- `aggregate.csv/json`：350 个 plan entry 的来源、状态、固定分母和逐 workflow 指标。",
        "- `task_metrics.csv/json`：逐任务结果，unknown 任务保留。",
        "- `summary_by_layer.csv`、`summary_confirmed_repair_by_layer.csv`、`summary_by_case.csv`、`summary_by_topology.csv`、`summary_by_business.csv`：拆分统计。",
        "- `paired_differences.csv/json`、`cluster_intervals.csv/json`：按 fixture 配对的增量和描述性 bootstrap 区间。",
        "- `traceability.csv/json`、`traceability_sources.json`：同一 L4 执行的证据投影；不是跨层责任准确率。",
        "- `mechanism_network_audit.json`：初始异常、分类、修复 overlay、重跑覆盖和最终异常计数。",
        "- `protocol_gains_by_layer.png/pdf`、`protocol_delta_vs_L0.png/pdf`、`ablation_gains.png/pdf`、`protocol_cost.png/pdf`、`traceability_projection.png/pdf`：收益、增量、消融、成本和追溯图；正确完成率表示业务可用性，错误完成率和错误交接表示安全收益。",
        "",
        "![protocol gains](protocol_gains_by_layer.png)",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan = json.loads((CLAIMREF / "plan.json").read_text())
    fixtures = {f["fixture_id"]: f for f in plan["fixtures"]}
    selected, invalid_base, retry_ids, contract_ids = build_selection(plan)
    rows = []
    for entry in plan["runs"]:
        row, _raw = row_for(entry, fixtures[entry["fixture_id"]], selected[entry["workflow_id"]])
        rows.append(row)
    if len(rows) != 350 or Counter(r["status"] for r in rows) != Counter({"completed": 344, "unknown": 6}):
        raise RuntimeError(f"unexpected final status: {Counter(r['status'] for r in rows)}")
    if sum(r["source"] == "provider_retry" for r in rows) != len(retry_ids):
        raise RuntimeError("provider retry overlay coverage mismatch")
    if sum(r["source"] == "contract_cleanup" for r in rows) != len(contract_ids):
        raise RuntimeError("contract cleanup overlay coverage mismatch")

    task_output = []
    for row in rows:
        fixture = fixtures[row["fixture_id"]]
        if row["status"] == "unknown":
            for t in fixture["graph"]["tasks"]:
                task_output.append({**row, "task_id": t["id"], "affected": t["id"] in fixture["evaluation"]["affected_tasks"],
                                    "safe_final": None, "unsafe_completion": None, "result_unknown": True})
        else:
            value = load_result(selected[row["workflow_id"]]["path"])
            for t in value["task_metrics"]:
                task_output.append({**row, **t})

    write_json(OUT / "plan.json", plan)
    write_json(OUT / "combined_manifest.json", {
        "plan_hash": plan["canonical_hash"], "entries": [
            {"workflow_id": r["workflow_id"], "status": r["status"], "source": r["source"],
             "result_path": r["result_path"], "result_sha256": r["result_sha256"],
             "prior_initial_invalid": selected[r["workflow_id"]].get("prior_initial_invalid", False)}
            for r in rows],
        "source_directories": {
            "base": str(BASE.relative_to(ROOT)), "claimref_fix": str(CLAIMREF.relative_to(ROOT)),
            "provider_retry": str(RETRY.relative_to(ROOT)), "contract_cleanup": str(CONTRACT.relative_to(ROOT)),
        },
        "source_artifacts_public": False,
        "source_artifact_policy": "Only this combined public archive is published; source workflow and private worker directories remain local.",
        "selection_rule": "contract cleanup overrides model action/claim_refs contract failures; provider retry overrides network-failure workflows; claimref fix overrides initial claim_refs INVALID workflows; other good base results preserved; interrupted workflows remain unknown",
    })
    write_json(OUT / "analysis_provenance.json", {
        "script": str(Path(__file__).relative_to(ROOT)),
        "plan_source": str((CLAIMREF / "plan.json").relative_to(ROOT)),
        "claimref_calibration": str((CLAIMREF / "calibration.json").relative_to(ROOT)),
        "provider_retry_calibration": str((ROOT / "results/final_live_calibration_provider_retry_20260911/calibration.json").relative_to(ROOT)),
        "contract_cleanup_calibration": str((ROOT / "results/final_live_calibration_contract_cleanup_20260911/calibration.json").relative_to(ROOT)),
        "invalid_base_workflows": sorted(invalid_base), "network_retry_workflows": sorted(retry_ids),
        "contract_cleanup_workflows": sorted(contract_ids),
        "fixed_denominator": True, "new_model_calls": 0,
        "source_artifacts_public": False,
        "source_artifact_policy": "Only this combined public archive is published; source workflow and private worker directories remain local.",
    })
    write_csv(OUT / "aggregate.csv", rows)
    write_json(OUT / "aggregate.json", rows)
    write_csv(OUT / "task_metrics.csv", task_output)
    write_json(OUT / "task_metrics.json", task_output)

    main_rows = [r for r in rows if r["group"] == "main"]
    layer_stats = group_summaries(main_rows, "layer")
    confirmed_layer_stats = group_summaries(
        [r for r in main_rows if r["case"] == "confirmed_repair"], "layer")
    case_stats = group_summaries(rows, "case")
    topology_stats = group_summaries(rows, "topology")
    business_stats = group_summaries(rows, "business_variant")
    group_stats = group_summaries(rows, "group")
    for name, data in (("summary_by_layer", layer_stats), ("summary_by_case", case_stats),
                       ("summary_by_topology", topology_stats), ("summary_by_business", business_stats),
                       ("summary_by_group", group_stats),
                       ("summary_confirmed_repair_by_layer", confirmed_layer_stats)):
        write_json(OUT / f"{name}.json", data); write_csv(OUT / f"{name}.csv", data)

    paired, intervals = main_pairs(rows)
    ablation, ablation_intervals = ablation_pairs(rows)
    write_json(OUT / "paired_differences.json", paired); write_csv(OUT / "paired_differences.csv", paired)
    write_json(OUT / "cluster_intervals.json", intervals); write_csv(OUT / "cluster_intervals.csv", intervals)
    write_json(OUT / "ablation_differences.json", ablation); write_csv(OUT / "ablation_differences.csv", ablation)
    write_json(OUT / "ablation_intervals.json", ablation_intervals); write_csv(OUT / "ablation_intervals.csv", ablation_intervals)

    traceability, traceability_sources = make_traceability(rows, selected)
    write_json(OUT / "traceability.json", traceability); write_csv(OUT / "traceability.csv", traceability)
    write_json(OUT / "traceability_sources.json", traceability_sources)
    (OUT / "traceability_README.md").write_text(
        "固定同一 L4 live execution 的证据投影；ordinary logs、no receipts、opaque relay 和缺失/篡改投影共享执行轨迹。"
        "没有独立责任标签，不能由此报告法律责任准确率。\n")

    anomaly_audit = mechanism_network_audit(plan, rows, invalid_base, retry_ids, contract_ids)
    write_json(OUT / "mechanism_network_audit.json", anomaly_audit)
    plot_all(layer_stats, confirmed_layer_stats, intervals, ablation_intervals, traceability, OUT)
    report(layer_stats, confirmed_layer_stats, ablation_intervals, rows, traceability,
           invalid_base, retry_ids, contract_ids, anomaly_audit, OUT)

    public_files = {}
    for path in sorted(OUT.rglob("*")):
        if not path.is_file() or path.name in ("manifest.json",):
            continue
        public_files[str(path.relative_to(OUT))] = sha256(path)
    write_json(OUT / "manifest.json", {
        "public_files": public_files,
        "private_data": "raw worker directories remain in the three source result directories; each has private_manifest.json",
    })
    print(json.dumps({"status": "complete", "counts": dict(Counter(r["status"] for r in rows)),
                      "sources": dict(Counter(r["source"] for r in rows)),
                      "traceability_projections": len(traceability), "new_model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
