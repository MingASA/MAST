#!/usr/bin/env python3
"""Create the reproducible analysis bundle for the layered benchmark v1.

The script only reads completed benchmark archives.  It does not execute a
workflow or call a model.  Raw workflow directories remain in place; the
output contains tables, figures, provenance and hashes that point back to
those archives.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from trust_network.benchmark.layered.preflight import (  # noqa: E402
    source_hashes,
    verify_offline,
    verify_validation,
)
from trust_network.benchmark.layered.spec import CASES, MAIN  # noqa: E402


OUT = REPO / "results" / "layered_v1_experiments"
OFFLINE = REPO / "results" / "layered_v1_offline_final"
FIXED = REPO / "results" / "layered_v1_fixed_evidence"
LIVE = REPO / "results" / "layered_v1_live_pilot_01"
VALIDATION = REPO / "results" / "layered_v1_validation_final" / "validation.json"
PRIOR = REPO / "results" / "contribution_generalization_v2"
PROBE = REPO / "results" / "layered_v1_live_l4_recovery_probe_20260910"
TAPE_RUNS = {
    "branch_late": REPO / "results" / "layered_v1_historical_terminal_replay_branch_late_20260910",
    "late_push": REPO / "results" / "layered_v1_historical_terminal_replay_late_push_20260910",
}
TAPE_SOURCES = {
    "branch_late": REPO / "results" / "layered_v1_tape_transfer_branch_late_dependency_20260910.json",
    "late_push": REPO / "results" / "layered_v1_tape_transfer_late_push_20260910.json",
}

CASE_ORDER = list(CASES)
FAULT_CASES = [case for case in CASE_ORDER if case != "active"]
EXTRA_LAYERS = ["L4_no_push", "L4_no_fact", "L4_no_recovery", "L3_coarse", "verify_all"]

METRIC_COLUMNS = [
    "unsafe_completion_count",
    "affected_task_count",
    "unsafe_completion_rate",
    "unsafe_action_count",
    "safe_final_completion",
    "total_tasks",
    "unrelated_completed",
    "unrelated_task_count",
    "unrelated_retention",
    "overfrozen_tasks",
    "recovered_tasks",
    "error_action_blocks",
    "post_fault_error_handoffs",
    "post_fault_error_organizations",
    "post_fault_error_branches",
    "post_fault_propagation_hops",
    "explicit_action_opportunities",
    "fault_action_opportunities",
    "status_queries",
    "fact_queries",
    "notifications",
    "notification_bytes",
    "route_proof_coverage",
    "new_model_calls",
    "provider_attempts",
    "known_tokens",
    "unknown_usage_attempts",
    "worker_errors",
    "invalid_actions",
    "model_holds",
    "rpc_rejections",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_metrics(directory: Path) -> list[dict[str, Any]]:
    return read_json(directory / "metrics.json")


def as_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None if value is None else int(value)
    if isinstance(value, (int, float)):
        return value
    return None


def total(rows: Iterable[dict[str, Any]], key: str) -> int | float:
    values = [as_number(row.get(key)) for row in rows]
    return sum(value for value in values if value is not None)


def maximum(rows: Iterable[dict[str, Any]], key: str) -> int | float:
    values = [as_number(row.get(key)) for row in rows]
    return max((value for value in values if value is not None), default=0)


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def count_ratio(numerator: int | float, denominator: int | float) -> str:
    return f"{int(numerator)}/{int(denominator)}" if denominator else "—"


def safe_rate(metrics: dict[str, Any]) -> float | None:
    return ratio(metrics.get("safe_final_completion", 0), metrics.get("total_tasks", 0))


def unrelated_rate(metrics: dict[str, Any]) -> float | None:
    return ratio(metrics.get("unrelated_completed", 0), metrics.get("unrelated_task_count", 0))


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in METRIC_COLUMNS:
        if key in {"unsafe_completion_rate", "unrelated_retention"}:
            continue
        values = [as_number(row.get(key)) for row in rows]
        numeric = [value for value in values if value is not None]
        result[key] = sum(numeric) if numeric else 0
    result["unsafe_completion_rate"] = ratio(result["unsafe_completion_count"], result["affected_task_count"])
    result["unsafe_action_rate"] = ratio(result["unsafe_action_count"], result["fault_action_opportunities"])
    result["unrelated_retention"] = ratio(result["unrelated_completed"], result["unrelated_task_count"])
    result["safe_final_completion_rate"] = ratio(result["safe_final_completion"], result["total_tasks"])
    return result


def row_scope(layer: str) -> str:
    return "main" if layer in MAIN else "ablation"


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return value


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def make_paired_rows(offline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ["topology", "case", "layer", "scope", "file"] + METRIC_COLUMNS + [
        "unsafe_action_rate",
        "safe_final_completion_rate",
    ]
    result = []
    for source in offline_rows:
        metrics = dict(source["metrics"])
        metrics["unrelated_retention"] = unrelated_rate(metrics)
        metrics["unsafe_action_rate"] = ratio(
            metrics.get("unsafe_action_count", 0), metrics.get("fault_action_opportunities", 0)
        )
        metrics["safe_final_completion_rate"] = safe_rate(metrics)
        result.append(
            {
                "topology": source["topology"],
                "case": source["case"],
                "layer": source["layer"],
                "scope": row_scope(source["layer"]),
                "file": source.get("file", ""),
                **metrics,
            }
        )
    return result


def add_long_metrics(
    output: list[dict[str, Any]],
    dataset: str,
    scope: str,
    topology: str,
    case: str,
    layer: str,
    metrics: dict[str, Any],
) -> None:
    definitions = {
        "unsafe_completion_count": ("count", "affected_task_count"),
        "unsafe_completion_rate": ("fraction", "affected_task_count"),
        "unsafe_action_count": ("count", "fault_action_opportunities"),
        "safe_final_completion": ("count", "total_tasks"),
        "safe_final_completion_rate": ("fraction", "total_tasks"),
        "unrelated_completed": ("count", "unrelated_task_count"),
        "unrelated_retention": ("fraction", "unrelated_task_count"),
        "overfrozen_tasks": ("count", ""),
        "recovered_tasks": ("count", "affected_task_count"),
        "error_action_blocks": ("count", "fault_action_opportunities"),
        "post_fault_error_handoffs": ("count", ""),
        "post_fault_error_organizations": ("count", ""),
        "post_fault_error_branches": ("count", ""),
        "post_fault_propagation_hops": ("hops", ""),
        "status_queries": ("count", ""),
        "fact_queries": ("count", ""),
        "notifications": ("count", ""),
        "notification_bytes": ("bytes", ""),
        "route_proof_coverage": ("fraction", "route_reference_count"),
        "new_model_calls": ("count", ""),
        "provider_attempts": ("count", ""),
        "known_tokens": ("tokens", ""),
        "unknown_usage_attempts": ("count", ""),
        "worker_errors": ("count", ""),
        "invalid_actions": ("count", ""),
        "model_holds": ("count", ""),
        "rpc_rejections": ("count", ""),
    }
    augmented = dict(metrics)
    augmented["unsafe_completion_rate"] = ratio(
        metrics.get("unsafe_completion_count", 0), metrics.get("affected_task_count", 0)
    )
    augmented["unsafe_action_rate"] = ratio(
        metrics.get("unsafe_action_count", 0), metrics.get("fault_action_opportunities", 0)
    )
    augmented["unrelated_retention"] = unrelated_rate(metrics)
    augmented["safe_final_completion_rate"] = safe_rate(metrics)
    for metric, (unit, denominator_key) in definitions.items():
        denominator = augmented.get(denominator_key) if denominator_key else ""
        output.append(
            {
                "dataset": dataset,
                "scope": scope,
                "topology": topology,
                "case": case,
                "layer": layer,
                "metric": metric,
                "value": augmented.get(metric),
                "denominator": denominator,
                "unit": unit,
            }
        )


def fixed_long_rows(fixed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in fixed_rows:
        for metric, value, denominator, unit in (
            ("verified_route_recall", row["verified_routes"]["recall"], row["verified_routes"]["expected"], "fraction"),
            ("estimated_route_recall", row["estimated_routes"]["recall"], row["estimated_routes"]["expected"], "fraction"),
            ("source_identity_recall", row["source_identity"]["recall"], row["source_identity"]["expected"], "fraction"),
            ("undetermined", row["undetermined"], row["completed_action_questions"], "count"),
            ("observation_bytes", row["observation_bytes"], "", "bytes"),
        ):
            result.append(
                {
                    "dataset": "fixed_evidence",
                    "scope": "traceability",
                    "topology": row["topology"],
                    "case": "fixed_projection",
                    "layer": row["profile"],
                    "metric": metric,
                    "value": value,
                    "denominator": denominator,
                    "unit": unit,
                }
            )
    return result


def tape_rows() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, directory in TAPE_RUNS.items():
        for source in load_metrics(directory):
            add_long_metrics(
                result,
                f"tape_{name}",
                "historical_terminal_transfer",
                source["topology"],
                source["case"],
                source["layer"],
                source["metrics"],
            )
    return result


def plot_heatmap(ax: Any, data: Any, row_labels: list[str], col_labels: list[str], title: str, percent_mode: bool = False) -> None:
    import numpy as np

    masked = np.ma.masked_invalid(np.asarray(data, dtype=float))
    finite = [float(value) for row in data for value in row if value is not None and not (isinstance(value, float) and math.isnan(value))]
    vmax = 1 if percent_mode else max(finite, default=1)
    if vmax == 0:
        vmax = 1
    image = ax.imshow(masked, aspect="auto", cmap="YlGnBu", vmin=0, vmax=vmax)
    ax.set_xticks(range(len(col_labels)), col_labels)
    ax.set_yticks(range(len(row_labels)), row_labels)
    ax.set_title(title)
    ax.tick_params(axis="x", rotation=35)
    for i in range(len(row_labels)):
        for j in range(len(col_labels)):
            value = data[i][j]
            if value is None or (isinstance(value, float) and math.isnan(value)):
                text = "N/A"
            elif percent_mode:
                text = f"{value * 100:.0f}%"
            else:
                text = f"{value:.0f}"
            ax.text(j, i, text, ha="center", va="center", fontsize=8)
    ax.figure.colorbar(image, ax=ax, shrink=0.75)


def save_figure(fig: Any, stem: str) -> None:
    fig.savefig(OUT / f"{stem}.png", dpi=200, bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.pdf", bbox_inches="tight")


def make_safety_figure(offline_rows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    grouped = {(case, layer): aggregate([r["metrics"] for r in offline_rows if r["case"] == case and r["layer"] == layer]) for case in CASE_ORDER for layer in MAIN}
    unsafe = [[grouped[(case, layer)]["unsafe_completion_rate"] for layer in MAIN] for case in CASE_ORDER]
    safe = [[grouped[(case, layer)]["safe_final_completion_rate"] for layer in MAIN] for case in CASE_ORDER]
    unrelated = [[grouped[(case, layer)]["unrelated_retention"] for layer in MAIN] for case in CASE_ORDER]
    overfrozen = [[grouped[(case, layer)]["overfrozen_tasks"] for layer in MAIN] for case in CASE_ORDER]
    recovered = [[ratio(grouped[(case, layer)]["recovered_tasks"], grouped[(case, layer)]["affected_task_count"]) for layer in MAIN] for case in CASE_ORDER]
    blocks = [[grouped[(case, layer)]["error_action_blocks"] for layer in MAIN] for case in CASE_ORDER]

    fig, axes = plt.subplots(2, 3, figsize=(17, 11), layout="constrained")
    plot_heatmap(axes[0, 0], unsafe, CASE_ORDER, list(MAIN), "Unsafe completion / affected tasks", True)
    plot_heatmap(axes[0, 1], safe, CASE_ORDER, list(MAIN), "Safe final completion / all tasks", True)
    plot_heatmap(axes[0, 2], unrelated, CASE_ORDER, list(MAIN), "Unrelated task retention", True)
    plot_heatmap(axes[1, 0], overfrozen, CASE_ORDER, list(MAIN), "Overfrozen unrelated tasks")
    plot_heatmap(axes[1, 1], recovered, CASE_ORDER, list(MAIN), "Recovered / affected tasks", True)
    plot_heatmap(axes[1, 2], blocks, CASE_ORDER, list(MAIN), "Program-blocked faulty proposals")
    fig.suptitle("Layered benchmark v1: safety and availability (offline main matrix)", fontsize=15)
    save_figure(fig, "layered_safety_availability")
    plt.close(fig)


def make_propagation_cost_figure(offline_rows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fault_rows = [r for r in offline_rows if r["case"] in FAULT_CASES and r["layer"] in MAIN]
    by_layer = {layer: aggregate([r["metrics"] for r in fault_rows if r["layer"] == layer]) for layer in MAIN}
    labels = list(MAIN)
    x = np.arange(len(labels))
    fig, axes = plt.subplots(2, 3, figsize=(17, 10), layout="constrained")

    for ax, key, title in (
        (axes[0, 0], "post_fault_error_handoffs", "Accepted faulty handoffs"),
        (axes[0, 1], "post_fault_error_organizations", "Organizations receiving faulty handoffs"),
        (axes[0, 2], "post_fault_error_branches", "Affected branches"),
    ):
        values = [by_layer[layer][key] for layer in labels]
        ax.bar(x, values, color="#4472c4")
        ax.set_xticks(x, labels)
        ax.set_title(f"{title}\n(sum over 9 fault cases × 3 topologies)")
        ax.set_ylabel("count")
        ax.grid(axis="y", alpha=0.25)

    hop_rows = [r for r in fault_rows if (r["metrics"].get("post_fault_propagation_hops") or 0) > 0]
    hop_values = [
        sum((r["metrics"].get("post_fault_propagation_hops") or 0) for r in hop_rows if r["layer"] == layer) / max(1, sum(r["layer"] == layer for r in hop_rows))
        for layer in labels
    ]
    axes[1, 0].bar(x, hop_values, color="#70ad47")
    axes[1, 0].set_xticks(x, labels)
    axes[1, 0].set_title("Mean maximum propagation hops\n(rows with a propagation path)")
    axes[1, 0].set_ylabel("hops")
    axes[1, 0].grid(axis="y", alpha=0.25)

    status = [by_layer[layer]["status_queries"] for layer in labels]
    facts = [by_layer[layer]["fact_queries"] for layer in labels]
    axes[1, 1].bar(x, status, label="status", color="#5b9bd5")
    axes[1, 1].bar(x, facts, bottom=status, label="fact", color="#ed7d31")
    axes[1, 1].set_xticks(x, labels)
    axes[1, 1].set_title("Remote query cost\n(status + fact queries)")
    axes[1, 1].set_ylabel("queries")
    axes[1, 1].legend()
    axes[1, 1].grid(axis="y", alpha=0.25)

    notice_kb = [by_layer[layer]["notification_bytes"] / 1000 for layer in labels]
    axes[1, 2].bar(x, notice_kb, color="#a5a5a5")
    axes[1, 2].set_xticks(x, labels)
    axes[1, 2].set_title("Targeted notification payload\n(sum over fault cases)")
    axes[1, 2].set_ylabel("kilobytes")
    axes[1, 2].grid(axis="y", alpha=0.25)

    fig.suptitle("Layered benchmark v1: propagation containment and protocol cost", fontsize=15)
    save_figure(fig, "layered_propagation_cost")
    plt.close(fig)


def make_traceability_live_figure(fixed_rows: list[dict[str, Any]], live_rows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    profiles = ["L0", "L1", "L2", "L3", "L4", "ablate_receipts", "opaque"]
    fgroup = {}
    for profile in profiles:
        rows = [row for row in fixed_rows if row["profile"] == profile]
        expected_routes = sum(row["verified_routes"]["expected"] for row in rows)
        expected_sources = sum(row["source_identity"]["expected"] for row in rows)
        fgroup[profile] = {
            "verified": ratio(sum(row["verified_routes"]["matched"] for row in rows), expected_routes),
            "estimated": ratio(sum(row["estimated_routes"]["matched"] for row in rows), expected_routes),
            "source": ratio(sum(row["source_identity"]["matched"] for row in rows), expected_sources),
            "bytes": sum(row["observation_bytes"] for row in rows),
        }

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), layout="constrained")
    x = np.arange(len(profiles))
    width = 0.25
    axes[0, 0].bar(x - width, [fgroup[p]["verified"] for p in profiles], width, label="verified route")
    axes[0, 0].bar(x, [fgroup[p]["estimated"] for p in profiles], width, label="estimated route")
    axes[0, 0].bar(x + width, [fgroup[p]["source"] for p in profiles], width, label="source identity")
    axes[0, 0].set_ylim(0, 1.08)
    axes[0, 0].set_xticks(x, profiles, rotation=35)
    axes[0, 0].set_ylabel("recall")
    axes[0, 0].set_title("Fixed denominator evidence projection")
    axes[0, 0].legend(fontsize=8)
    axes[0, 0].grid(axis="y", alpha=0.25)

    axes[0, 1].bar(x, [fgroup[p]["bytes"] / 1000 for p in profiles], color="#8064a2")
    axes[0, 1].set_xticks(x, profiles, rotation=35)
    axes[0, 1].set_ylabel("kilobytes")
    axes[0, 1].set_title("Evidence projection size")
    axes[0, 1].grid(axis="y", alpha=0.25)

    cases = ["active", "late_notice", "confirmed_repair"]
    live_group = {(case, layer): aggregate([row["metrics"] for row in live_rows if row["case"] == case and row["layer"] == layer]) for case in cases for layer in MAIN}
    unsafe = [[live_group[(case, layer)]["unsafe_completion_rate"] for layer in MAIN] for case in cases]
    safe = [[live_group[(case, layer)]["safe_final_completion_rate"] for layer in MAIN] for case in cases]
    plot_heatmap(axes[1, 0], unsafe, cases, list(MAIN), "Live unsafe completion / affected tasks", True)
    plot_heatmap(axes[1, 1], safe, cases, list(MAIN), "Live safe final completion / all tasks", True)
    fig.suptitle("Layered benchmark v1: fixed traceability and separate live pilot", fontsize=15)
    save_figure(fig, "layered_traceability_live")
    plt.close(fig)


def make_live_figure(live_rows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    cases = ["active", "late_notice", "confirmed_repair"]
    group = {(case, layer): aggregate([row["metrics"] for row in live_rows if row["case"] == case and row["layer"] == layer]) for case in cases for layer in MAIN}
    labels = list(MAIN)
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), layout="constrained")
    unsafe = [[group[(case, layer)]["unsafe_completion_rate"] for layer in labels] for case in cases]
    safe = [[group[(case, layer)]["safe_final_completion_rate"] for layer in labels] for case in cases]
    plot_heatmap(axes[0, 0], unsafe, cases, labels, "Unsafe completion / affected tasks", True)
    plot_heatmap(axes[0, 1], safe, cases, labels, "Safe final completion / all tasks", True)

    x = np.arange(len(labels))
    calls = [sum(group[(case, layer)]["new_model_calls"] for case in cases) for layer in labels]
    tokens = [sum(group[(case, layer)]["known_tokens"] for case in cases) / 1000 for layer in labels]
    axis = axes[1, 0]
    axis.bar(x - 0.18, calls, 0.36, label="model calls", color="#4472c4")
    axis.set_xticks(x, labels)
    axis.set_ylabel("calls")
    axis.set_title("Live model cost (15 rows total by layer)")
    twin = axis.twinx()
    twin.bar(x + 0.18, tokens, 0.36, label="known tokens", color="#ed7d31")
    twin.set_ylabel("known tokens (thousands)")
    axis.grid(axis="y", alpha=0.25)
    handles, names = axis.get_legend_handles_labels()
    h2, n2 = twin.get_legend_handles_labels()
    axis.legend(handles + h2, names + n2, fontsize=8)

    blocks = [sum(group[(case, layer)]["error_action_blocks"] for case in cases) for layer in labels]
    holds = [sum(group[(case, layer)]["model_holds"] for case in cases) for layer in labels]
    invalid = [sum(group[(case, layer)]["invalid_actions"] for case in cases) for layer in labels]
    axes[1, 1].bar(x - 0.25, blocks, 0.25, label="program blocks")
    axes[1, 1].bar(x, holds, 0.25, label="model holds")
    axes[1, 1].bar(x + 0.25, invalid, 0.25, label="invalid actions")
    axes[1, 1].set_xticks(x, labels)
    axes[1, 1].set_ylabel("count")
    axes[1, 1].set_title("Safety behavior attribution")
    axes[1, 1].legend(fontsize=8)
    axes[1, 1].grid(axis="y", alpha=0.25)
    fig.suptitle("Layered benchmark v1: MiniMax live pilot (independent paths)", fontsize=15)
    save_figure(fig, "layered_live_pilot")
    plt.close(fig)


def make_offline_analysis(offline_rows: list[dict[str, Any]], fixed_rows: list[dict[str, Any]], live_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Layered benchmark v1 offline analysis",
        "",
        "本文件复用 `results/layered_v1_offline_final` 的 210 条正式矩阵，不重跑 workflow。矩阵包含三类拓扑、十个场景和 L0–L4 主层级各 150 条运行，另有 60 条消融/对照。所有数值按任务去重的 `unsafe_completion_count` 与动作级 `unsafe_action_count` 分开保存。",
        "",
        "## 归档与评分前提",
        "",
        "- 离线进度为 210/210 completed；代码绑定的 validation 为 passed，248 tests、5 个进程等价病例。正式归档通过 preflight hash 校验。",
        "- active 没有受影响任务，错误完成率写为 N/A；它只用于显示健康工作流的安全最终完成。",
        "- 三个拓扑模板和同一矩阵中的层级运行不是独立抽样；这里报告的是受控机制增量。",
        "- 初始化、故障注入和效果由脚本固定；离线数据证明协议执行语义，不证明一般模型错误率。",
        "",
        "## 主矩阵：错误完成",
        "",
        "|场景|受影响任务分母|L0|L1|L2|L3|L4|",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case in CASE_ORDER:
        row_values = []
        affected = None
        for layer in MAIN:
            metrics = aggregate([r["metrics"] for r in offline_rows if r["case"] == case and r["layer"] == layer])
            affected = metrics["affected_task_count"] if affected is None else affected
            row_values.append(count_ratio(metrics["unsafe_completion_count"], metrics["affected_task_count"]))
        lines.append(f"|{case}|{int(affected or 0)}|" + "|".join(row_values) + "|")

    lines += [
        "",
        "主层级按场景的安全最终完成与无关任务保留如下。`safe_final_completion` 是最终安全完成的全任务计数；它不会把先前的错误完成抹掉。",
        "",
        "|场景|L0|L1|L2|L3|L4|无关任务保留（主层级）|",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for case in CASE_ORDER:
        values = []
        unrelated = []
        for layer in MAIN:
            metrics = aggregate([r["metrics"] for r in offline_rows if r["case"] == case and r["layer"] == layer])
            values.append(count_ratio(metrics["safe_final_completion"], metrics["total_tasks"]))
            unrelated.append(percent(metrics["unrelated_retention"]))
        lines.append(f"|{case}|" + "|".join(values) + "|" + ", ".join(f"{layer} {value}" for layer, value in zip(MAIN, unrelated)) + "|")

    lines += [
        "",
        "## 各层的增量解释",
        "",
        "对 3 个拓扑合计，主矩阵共有 48 个受影响任务。L0 完成了 48/48 个受影响错误任务；L1 为 45/48，少出的 3 个来自 tampered_handoff；L2 为 39/48，额外消除了 6 个 root_retraction；L3 为 24/48，额外消除了 intermediate_retraction、branch_retraction、late_notice 的 15 个错误完成；L4 为 0/48，额外消除了 signed_false、conflicting_sources、confirmed_repair、authority_unknown 的 24 个隐藏事实错误。这个阶梯与每层所实现的能力对应。",
        "",
        "- **L1 的贡献是完整性和交接保护。** 三个拓扑的篡改场景从 L0 的 3/3 错误完成降为 L1 的 0/3；它不是事后把评分结果改成安全，而是在接收篡改包时拒绝了交接。L1 在撤销场景仍不能发现远端状态变化。",
        "- **L2 的贡献是根声明远端查证。** root_retraction 从 L1 的 6/6 降为 L2 的 0/6；对中间和分支撤销，L2 仍保持 6/6 与根以下的低层一致，因为它没有查完整依赖闭包。",
        "- **L3 的贡献是沿依赖闭包局部阻断。** intermediate_retraction、branch_retraction 与 late_notice 在 L2 合计 15/15，L3 降为 0/15，同时主层级的无关任务保留为 100%。这说明冻结对象是受影响任务的依赖，而不是收到通知的整个组织。",
        "- **L4 的新增安全贡献来自权威事实补证。** 四类隐藏事实场景在 L3 合计 24/24，L4 为 0/24；`L4_no_fact` 又回到 24/24。签名和依赖闭包只证明“谁签了、声明是否被撤销”，不能证明签名尚未撤销的金额事实正确。",
        "- **L4 的通知主要增加发现速度与审计材料。** 在当前同步 pull 查询和固定 tick 的离线设置中，`L4_no_push` 与 L4 的错误完成结果持平；L4 多出的通知和字节体现提前发现/传播能力，不能解释成额外的安全率改善。",
        "- **恢复消融需要谨慎解释。** confirmed_repair 的离线 `recovered_tasks` 在 L0–L4 都是 6，因为低层允许普通重发正确声明；L4 的独立新增是先用权威事实挡住错误动作并绑定修订证据，不能仅凭这个脚本把全部恢复收益归给 recovery flag。`L4_no_recovery` 与 L4 的安全结果也持平。",
        "- **粗粒度冻结牺牲可用性。** `L3_coarse` 在 6 条中没有错误完成，但有 9 个无关任务误冻；对应主 L3 的无关任务保留是 100%。`verify_all` 在本轮检查阈值下与 L3 在撤销场景持平，并且对隐藏事实仍有 24/24 错误完成，不应按名称宣称额外贡献。",
        "",
        "## 消融汇总",
        "",
        "|配置|运行数|错误完成/受影响任务|安全最终完成/全部任务|误冻|恢复|状态查询|事实查询|通知字节|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for layer in EXTRA_LAYERS:
        selected = [r for r in offline_rows if r["layer"] == layer]
        metrics = aggregate([r["metrics"] for r in selected])
        lines.append(
            f"|{layer}|{len(selected)}|{count_ratio(metrics['unsafe_completion_count'], metrics['affected_task_count'])}|"
            f"{count_ratio(metrics['safe_final_completion'], metrics['total_tasks'])}|{int(metrics['overfrozen_tasks'])}|"
            f"{int(metrics['recovered_tasks'])}|{int(metrics['status_queries'])}|{int(metrics['fact_queries'])}|{int(metrics['notification_bytes'])}|"
        )

    lines += [
        "",
        "## 传播范围和成本",
        "",
        "在 9 个故障场景（每个 3 个拓扑）的主层级汇总中，L0 接受了最多的故障后错误交接；L1 只处理完整性，不主动查询远端撤销；L2 开始查根；L3 将中间/分支错误限制在局部；L4 在此基础上对事实错误直接阻断。逐条的组织数、分支数、传播跳数、查证次数和通知字节见 `offline_paired_metrics.csv` 与 `chart_data.csv`。",
        "",
        "正式主矩阵的状态/事实查询合计为：L0 0、L1 0、L2 612、L3 1,582、L4 状态 1,481 加事实 1,153。L4 另发送 137 条定向通知、819,111 bytes。查询与通知是可观察成本，需和安全收益一起报告。",
        "",
        "![安全和可用性](layered_safety_availability.png)",
        "",
        "![传播与成本](layered_propagation_cost.png)",
        "",
        "## 原始数据",
        "",
        "逐条正式结果在 [layered_v1_offline_final](../layered_v1_offline_final)，旧的 `results/layered_v1_offline` 未被使用。固定分母追溯与 live 结果在总报告中单列。",
    ]
    (OUT / "offline_analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_report(
    offline_rows: list[dict[str, Any]],
    fixed_rows: list[dict[str, Any]],
    live_rows: list[dict[str, Any]],
    fixed_long: list[dict[str, Any]],
) -> None:
    offline_main = [r for r in offline_rows if r["layer"] in MAIN]
    main_aggregate = {layer: aggregate([r["metrics"] for r in offline_main if r["layer"] == layer]) for layer in MAIN}
    fixed_group = {}
    for profile in ["L0", "L1", "L2", "L3", "L4", "ablate_receipts", "opaque"]:
        rows = [r for r in fixed_rows if r["profile"] == profile]
        fixed_group[profile] = {
            "route_expected": sum(r["verified_routes"]["expected"] for r in rows),
            "verified": sum(r["verified_routes"]["matched"] for r in rows),
            "estimated": sum(r["estimated_routes"]["matched"] for r in rows),
            "source_expected": sum(r["source_identity"]["expected"] for r in rows),
            "source": sum(r["source_identity"]["matched"] for r in rows),
            "undetermined": sum(r["undetermined"] for r in rows),
            "bytes": sum(r["observation_bytes"] for r in rows),
        }

    live_group = {(case, layer): aggregate([r["metrics"] for r in live_rows if r["case"] == case and r["layer"] == layer]) for case in ["active", "late_notice", "confirmed_repair"] for layer in MAIN}
    live_total = aggregate([r["metrics"] for r in live_rows])
    probe_metrics = [read_json(path) for path in sorted(PROBE.glob("probe_*/metrics.json"))]
    probe_total = aggregate(probe_metrics) if probe_metrics else {}

    lines = [
        "# Layered benchmark v1 experiments",
        "",
        "本轮实验支持一个清晰但有边界的结论：协议能力按 L0→L4 增加时，受控故障矩阵中的错误完成逐层被对应机制消除；签名解决交接完整性，根查证解决根撤销，依赖闭包解决中间/分支传播，事实补证解决签名有效但事实错误。代价是远端查询、事实补证、通知字节和模型调用。",
        "",
        "实验没有把离线脚本、历史终端提议转移和真实 MiniMax 运行混成一个错误率。live 层级是独立模型路径；历史 tape 是固定终端提议在新拓扑上的反事实转移；追溯使用同一执行的固定分母投影。",
        "",
        "## 交付物",
        "",
        "- [offline_analysis.md](offline_analysis.md)：210 条正式离线矩阵的逐场景配对分析。",
        "- [offline_paired_metrics.csv](offline_paired_metrics.csv)：每条离线运行的完整配对指标。",
        "- [chart_data.csv](chart_data.csv)：所有图表的长表数据，可独立重画。",
        "- [layered_safety_availability.png](layered_safety_availability.png)、[layered_propagation_cost.png](layered_propagation_cost.png)：离线主结果。",
        "- [layered_traceability_live.png](layered_traceability_live.png)、[layered_live_pilot.png](layered_live_pilot.png)：固定分母追溯与 live 单列结果。每张图同时输出 PDF。",
        "- [provenance.json](provenance.json) 和 [artifact_manifest.json](artifact_manifest.json)：输入来源、代码 hash 和输出完整性。",
        "",
        "## 1. 数据规模与完整性",
        "",
        "|数据|规模|模型调用|用途|",
        "|---|---:|---:|---|",
        "|正式离线矩阵|210 条|0|L0–L4 主比较与消融|",
        "|固定证据投影|21 条|0|3 拓扑 × L0–L4、receipt 消融、opaque relay|",
        "|历史终端 tape|10 条|0|两条历史模型轨迹各转移到五层|",
        "|MiniMax 主 pilot|15 条|257 次决定/257 次 provider attempt|健康、迟到通知、确认修订 × L0–L4|",
        "|L4 恢复补充探针|3 条|51 次决定/51 次 provider attempt|只观察 live 恢复入口，独立于主 pilot|",
        "",
        "正式离线归档为 210/210 completed，validation 为 248 tests passed、5 个进程等价病例；主 pilot 为 15/15 completed。主 pilot 的 257 次调用全部返回，没有 unfinished call 或 worker error；4 次 usage 字段未知，计为未知 usage 而不是未知调用。",
        "",
        "## 2. 离线安全性、传播与可用性",
        "",
        "三拓扑合计的主矩阵共有 48 个受影响任务。错误完成按受影响任务去重：",
        "",
        "|层|错误完成/受影响任务|安全最终完成/全部任务|无关任务保留|状态查询|事实查询|通知字节|",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for layer in MAIN:
        metrics = main_aggregate[layer]
        lines.append(
            f"|{layer}|{count_ratio(metrics['unsafe_completion_count'], metrics['affected_task_count'])}|"
            f"{count_ratio(metrics['safe_final_completion'], metrics['total_tasks'])}|{percent(metrics['unrelated_retention'])}|"
            f"{int(metrics['status_queries'])}|{int(metrics['fact_queries'])}|{int(metrics['notification_bytes'])}|"
        )

    lines += [
        "",
        "主矩阵的增量不是一个平均黑箱分数，而是和故障位置对应的阶梯：L1 在篡改交接的 3/3 任务上阻断；L2 在根撤销的 6/6 任务上阻断；L3 在中间撤销、分支撤销和迟到通知的 15/15 任务上阻断；L4 在签名有效的错误事实、冲突来源、确认修订和权威 UNKNOWN 的 24/24 任务上阻断。L4 主层级仍保留 72/72 个无关任务，正式矩阵没有出现误冻。",
        "",
        "这支持机制设计的核心方向：跨组织错误传播不是单一的签名问题。签名保护“消息没有被改”，依赖闭包保护“当前动作没有依赖已失效的上游”，事实补证保护“仍然有效的签名没有把错误业务事实变成可信事实”。通知带来更早的消费者发现和审计路径；在同步查询设置下，它没有单独改变最终错误计数。",
        "",
        "![离线安全和可用性](layered_safety_availability.png)",
        "",
        "![传播范围和成本](layered_propagation_cost.png)",
        "",
        "## 3. 消融结论",
        "",
        "`L4_no_fact` 在隐藏事实相关的 12 条运行中为 24/24 错误完成，而 L4 为 0/24，事实补证是这一增量的必要部件。`L4_no_push` 在其 9 条对应运行中与 L4 的最终安全性持平，但没有定向通知，说明本 benchmark 的同步 pull 设置还不能把通知的提前发现优势转化为最终错误率差异。`L3_coarse` 没有错误完成，却误冻 9 个无关任务；完整依赖闭包在相同主场景中保持无关任务 100% 保留。`verify_all` 与 L3 的撤销结果持平，并没有解决隐藏事实错误。",
        "",
        "confirmed_repair 的离线结果显示 L0–L4 都能得到 6 个恢复任务，这是因为低层允许普通重发正确声明。L4 的恢复绑定仍然有安全意义：它约束修订、权威确认和派生声明重建必须属于同一来源链；本轮矩阵没有把这条语义单独制造成“只有 L4 才能完成”的可用性差异。",
        "",
        "## 4. 固定分母追溯",
        "",
        "固定证据使用同一执行和同一条路线分母：总路线 68 条、来源身份 14 条、已完成动作问题 51 条。L0 的普通日志可以估计 68/68 条路线，但可验证路线为 0/68、来源身份为 0/14；L1–L4 均达到可验证路线 68/68、来源身份 14/14。receipt 消融仍能估计路线 68/68，但可验证路线降为 0/68；opaque relay 连估计路线也只有 0/68。所有 51 个责任问题在这个固定投影中为 undetermined，因为新执行没有独立责任真值标签。",
        "",
        "|证据配置|可验证路线|普通日志路线估计|来源身份|undetermined|投影字节|",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for profile in ["L0", "L1", "L2", "L3", "L4", "ablate_receipts", "opaque"]:
        group = fixed_group[profile]
        lines.append(
            f"|{profile}|{count_ratio(group['verified'], group['route_expected'])}|{count_ratio(group['estimated'], group['route_expected'])}|"
            f"{count_ratio(group['source'], group['source_expected'])}|{group['undetermined']}/51|{group['bytes']}|"
        )
    lines += [
        "",
        "独立责任标签继续引用 `results/contribution_generalization_v2`：clean own-notice 正例 3/3，四类证据变化后的正例 3/12，负例误指控 0/96，证据不足正例待定 9/9。来源身份只证明来源，不等同于事实责任或法律责任。",
        "",
        "## 5. 历史终端提议转移",
        "",
        "两条历史 trace 各产生 5 个层级结果，共 10 条；没有模型调用，所有结果哈希与 tape 输入一致。它们是明确终端转交/发票提议在新拓扑的反事实角色转移；未映射阶段保持 hold，因此两组结果的安全最终完成均为 0/20，不能解释为模型在五个协议层都失败，也不能作为独立模型样本。L4 两组都显示完整路线证明和通知记录，但 tape 适配没有伪造新的恢复决定。",
        "",
        "|历史源|运行数|错误完成|安全最终完成|L0→L4 错误交接（概览）|",
        "|---|---:|---:|---:|---|",
        "|branch_late|5|0/10|0/20|L0–L2 1，L3–L4 0|",
        "|late_push|5|0/10|0/20|L0–L2 2，L3–L4 0|",
        "",
        "## 6. MiniMax live pilot（单列）",
        "",
        "15 条 live 是 3 个场景 × 5 层的独立模型路径，不能把层间差值当成配对因果估计。active 是健康控制；它的错误分母为 N/A。",
        "",
        "|场景|L0|L1|L2|L3|L4|",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in ["active", "late_notice", "confirmed_repair"]:
        values = []
        for layer in MAIN:
            metrics = live_group[(case, layer)]
            values.append(
                f"unsafe {count_ratio(metrics['unsafe_completion_count'], metrics['affected_task_count'])}; "
                f"safe {count_ratio(metrics['safe_final_completion'], metrics['total_tasks'])}"
            )
        lines.append(f"|{case}|" + "|".join(values) + "|")
    lines += [
        "",
        "观察到的 live 行为与离线机制结果方向一致，但样本是接口校准与小规模行为证据：",
        "",
        "- late_notice 中 L0–L2 各完成 2/2 个受影响错误任务并接受错误传播；L3 和 L4 各为 0/2，且无关任务 2/2 完成。L3 主要通过依赖闭包查证和程序阻断，L4 还产生了 5 条通知和 40 次事实查询。",
        "- confirmed_repair 中 L0–L3 各完成 2/2 个错误任务；L4 为 0/2，发生 8 次程序对错误提议的阻断，且无 unsafe completion。L4 的 source repair 决策在主 pilot 中是 hold，因此没有 live recovery completion；这不是恢复失败率，而是没有形成恢复动作机会。",
        "- active 五层均没有错误完成或误冻；L3 有 1 次模型无效动作，导致 3/4 安全完成，属于模型接口行为，不是协议放行错误。",
        "- 主 pilot 合计 257 次模型调用、257 次 provider attempt、403,839 个已知 token、4 次未知 usage、17 次模型 hold、1 次 invalid action、0 个 worker error、0 个未返回调用。",
        "",
        "![live pilot](layered_live_pilot.png)",
        "",
        "### L4 恢复补充探针",
        "",
        "由于主 pilot 的 L4 在 confirmed_repair 中停在 source hold，我运行了最多 3 条独立补充探针；它们不改变 prompt、工作负载或预算，也不并入 15 条 pilot 的统计。三条都完整返回 17/17 调用，错误完成均为 0，程序阻断分别为 8、8、7，恢复完成均为 0；前两条有 2、1 次模型 hold，第三条没有 hold 但仍未提交恢复动作。结果支持“L4 能安全暂停并拒绝错误动作”，但不支持“真实模型已自主完成修订恢复”。原始数据在 [layered_v1_live_l4_recovery_probe_20260910](../layered_v1_live_l4_recovery_probe_20260910)。",
        "",
        "## 7. 结论与边界",
        "",
        "当前数据正向支持协议的机制级贡献：它能把错误控制从消息完整性逐步扩展到根状态、完整依赖、定向通知和权威事实；在三种拓扑与十类受控故障上，完整 L4 将错误完成从主矩阵的 48/48 降到 0/48，同时保留全部 72 个无关任务。固定分母投影也显示，签名交接和收据让路线、来源身份从普通日志的可估计变成可验证。",
        "",
        "实验规模足以支持这组受控机制判断和论文主线图表，但还不足以声称现实 Agent 的一般错误率、异步竞态下的可靠性、事实真实性或法律责任准确率。主限制是三类脚本拓扑、脚本化初始化/故障、同步 RPC 零延迟、live 模型只参与故障后动作，以及 live recovery 没有被真实模型触发。",
        "",
        "在本任务书范围内，A–D 已完成，数据已保存，下一步应进入收敛写作和失败边界整理。若要扩展研究，最有价值的下一实验是给恢复入口设计可自然到达的 live 任务，并单独测试权威 UNKNOWN、拒绝修订、错误绑定/过期/重放证据；不应把更多健康成功场景当作当前主结论的替代。",
        "",
        "![固定追溯与 live](layered_traceability_live.png)",
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_provenance(
    offline_rows: list[dict[str, Any]], fixed_rows: list[dict[str, Any]], live_rows: list[dict[str, Any]]
) -> None:
    input_paths = [
        REPO / "TASK_EXPERIMENTS_LAYERED_V1.md",
        REPO / "BENCHMARK_LAYERED_V1.md",
        OFFLINE / "progress.json",
        OFFLINE / "metrics.json",
        OFFLINE / "manifest.json",
        FIXED / "metrics.json",
        FIXED / "manifest.json",
        LIVE / "progress.json",
        LIVE / "metrics.json",
        LIVE / "manifest.json",
        VALIDATION,
        PRIOR / "report.md",
        PRIOR / "artifact_manifest.json",
        PROBE / "summary.json",
        PROBE / "artifact_manifest.json",
    ]
    input_paths.extend(TAPE_SOURCES.values())
    input_paths.extend(directory / "metrics.json" for directory in TAPE_RUNS.values())
    input_paths.extend(directory / "manifest.json" for directory in TAPE_RUNS.values())
    input_hashes = {str(path.relative_to(REPO)): sha256_file(path) for path in input_paths if path.exists()}
    validation = read_json(VALIDATION)
    write_json(
        OUT / "provenance.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis_script": str(Path(__file__).relative_to(REPO)),
            "offline_rows": len(offline_rows),
            "fixed_rows": len(fixed_rows),
            "live_rows": len(live_rows),
            "formal_preflight": {
                "offline_progress": read_json(OFFLINE / "progress.json"),
                "validation_status": validation["status"],
                "validation_tests": validation["tests"],
                "validation_process_parity_cases": validation["process_parity_cases"],
            },
            "source_hashes": source_hashes(),
            "input_sha256": input_hashes,
            "interpretation": {
                "offline": "scripted mechanism matrix; topologies and layers are controlled runs, not independent samples",
                "fixed_evidence": "same execution and fixed route denominator; no new responsibility labels",
                "tape": "counterfactual terminal proposal transfer; not exact signature replay or new model decisions",
                "live": "15 independent MiniMax paths; initialization scripted and effects simulated",
                "recovery_probe": "three supplementary L4 probes, excluded from the main pilot summary",
            },
        },
    )


def make_manifest() -> None:
    manifest = {}
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "artifact_manifest.json":
            manifest[path.name] = sha256_file(path)
    write_json(OUT / "artifact_manifest.json", manifest)


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"output already exists: {OUT}")
    OUT.mkdir(parents=True)

    verify_offline(str(OFFLINE))
    verify_validation(str(VALIDATION))
    offline_rows = load_metrics(OFFLINE)
    fixed_rows = load_metrics(FIXED)
    live_rows = load_metrics(LIVE)

    paired = make_paired_rows(offline_rows)
    write_csv(
        OUT / "offline_paired_metrics.csv",
        ["topology", "case", "layer", "scope", "file"] + METRIC_COLUMNS + ["unsafe_action_rate", "safe_final_completion_rate"],
        paired,
    )

    chart_rows: list[dict[str, Any]] = []
    for row in offline_rows:
        add_long_metrics(chart_rows, "offline", row_scope(row["layer"]), row["topology"], row["case"], row["layer"], row["metrics"])
    chart_rows.extend(fixed_long_rows(fixed_rows))
    for row in live_rows:
        add_long_metrics(chart_rows, "live", "main", row["topology"], row["case"], row["layer"], row["metrics"])
    chart_rows.extend(tape_rows())
    for index, path in enumerate(sorted(PROBE.glob("probe_*/metrics.json"))):
        metrics = read_json(path)
        add_long_metrics(chart_rows, "live_recovery_probe", "supplementary", "long_chain_fork", "confirmed_repair", f"L4_probe_{index:02d}", metrics)
    write_csv(
        OUT / "chart_data.csv",
        ["dataset", "scope", "topology", "case", "layer", "metric", "value", "denominator", "unit"],
        chart_rows,
    )

    make_offline_analysis(offline_rows, fixed_rows, live_rows)
    make_safety_figure(offline_rows)
    make_propagation_cost_figure(offline_rows)
    make_traceability_live_figure(fixed_rows, live_rows)
    make_live_figure(live_rows)
    make_provenance(offline_rows, fixed_rows, live_rows)
    make_report(offline_rows, fixed_rows, live_rows, fixed_long_rows(fixed_rows))
    make_manifest()
    print(f"wrote {OUT}")
    print(f"offline rows: {len(offline_rows)}; fixed rows: {len(fixed_rows)}; live rows: {len(live_rows)}")
    print(f"chart rows: {len(chart_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
