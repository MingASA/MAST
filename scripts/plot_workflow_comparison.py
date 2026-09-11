"""Plot the four-strategy summary from the archived workflow benchmark.

The source is scripted replay data only.  This script never calls a model and
does not alter the archived runs.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


STRATEGIES = [
    ("autonomous", "Autonomous", "#5f7890"),
    ("root_gate", "Simple Gate", "#d88b1f"),
    ("dependency", "Dependency", "#2f78a8"),
    ("verify_all", "Verify-All", "#238b68"),
]


def final_c_retention(base: Path, arm: str) -> tuple[int, int]:
    completed = total = 0
    for metrics_path in sorted(base.glob(f"*__{arm}/metrics.json")):
        trace = json.loads(metrics_path.with_name("trace.json").read_text())
        ends = [event for event in trace["events"] if event.get("kind") == "task_end"]
        latest = {event["task"]: event for event in ends}
        c_tasks = [event for event in latest.values() if event.get("order") == "C"]
        total += len(c_tasks)
        completed += sum(event.get("action") == "COMPLETED" for event in c_tasks)
    return completed, total


def summarize(source: Path, run_base: Path) -> list[dict]:
    rows = json.loads(source.read_text())
    summaries = []
    for arm, label, _color in STRATEGIES:
        arm_rows = [row for row in rows if row["arm"] == arm]
        fault_rows = [row for row in arm_rows if row["case"] != "active"]
        if len(arm_rows) != 11 or len(fault_rows) != 10:
            raise ValueError(f"expected 11 workflows/10 fault workflows for {arm}")
        c_completed, c_total = final_c_retention(run_base, arm)
        route_matches = sum(row["error_route_registration_matches"] for row in fault_rows)
        route_eligible = sum(row["error_route_registration_eligible"] for row in fault_rows)
        summaries.append(
            {
                "strategy": label,
                "arm": arm,
                "workflows": len(arm_rows),
                "fault_workflows": len(fault_rows),
                "propagation_mean_max_distance": sum(
                    row["max_error_propagation_distance"] for row in fault_rows
                )
                / len(fault_rows),
                "propagation_sum_max_distance": sum(
                    row["max_error_propagation_distance"] for row in fault_rows
                ),
                "error_accepting_org_mean": sum(
                    row["error_accepting_organizations"] for row in fault_rows
                )
                / len(fault_rows),
                "unrelated_completed": c_completed,
                "unrelated_total": c_total,
                "unrelated_retention": c_completed / c_total if c_total else None,
                "trace_matches": route_matches,
                "trace_eligible": route_eligible,
                "trace_recall": route_matches / route_eligible if route_eligible else None,
                "unsafe_completed": sum(row["unsafe_completed"] for row in arm_rows),
                "error_actions_blocked": sum(row["error_actions_blocked"] for row in arm_rows),
                "verification_queries": sum(row["verification_queries"] for row in arm_rows),
            }
        )
    return summaries


def write_outputs(out: Path, source: Path, summaries: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=False)
    fields = [
        "strategy",
        "arm",
        "workflows",
        "fault_workflows",
        "propagation_mean_max_distance",
        "propagation_sum_max_distance",
        "error_accepting_org_mean",
        "unrelated_completed",
        "unrelated_total",
        "unrelated_retention",
        "trace_matches",
        "trace_eligible",
        "trace_recall",
        "unsafe_completed",
        "error_actions_blocked",
        "verification_queries",
    ]
    with (out / "chart_data.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in summaries)

    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    (out / "provenance.json").write_text(
        json.dumps(
            {
                "source": str(source),
                "source_sha256": source_hash,
                "decision_source": "scripted",
                "new_model_calls": 0,
                "aggregation": {
                    "propagation": "mean max_error_propagation_distance over 10 non-active fault workflows",
                    "unrelated_branch": "final C task completion over all 11 workflows",
                    "traceability": "error route registration matches / eligible, conditional on an accepted error route",
                },
                "strategy_mapping": {arm: label for arm, label, _color in STRATEGIES},
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    lines = [
        "# 四策略三指标对比图",
        "",
        "来源：统一 workflow v1 的完整 88 条矩阵；本图选取四个目标策略，共 44 条 scripted replay。本图没有新增模型调用。",
        "",
        "|策略|错误传播范围：平均最大传播距离（跳）|无关 C 分支保留|追溯能力：错误路由回溯率|回溯分子/分母|",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"|{row['strategy']}|{row['propagation_mean_max_distance']:.2f}|"
            f"{row['unrelated_completed']}/{row['unrelated_total']} "
            f"({row['unrelated_retention']:.0%})|{row['trace_recall']:.0%}|"
            f"{row['trace_matches']}/{row['trace_eligible']}|"
        )
    lines += [
        "",
        "## 读图口径",
        "",
        "错误传播范围取 10 个非 active 条件的 `max_error_propagation_distance` 等权平均；数值越低越好。它描述错误证据实际被接受后到达的最大相对距离，不是所有潜在路径的数量。",
        "",
        "无关分支保留统计每条 workflow 的两个 C 任务最终是否完成；它只反映这组固定工作流中的局部冻结是否误伤 C。",
        "",
        "追溯能力取有错误路由时的 `error_route_recall`。完整依赖门禁若在动作前截住错误交接，就不会产生错误路由；因此回溯率的分母会变小，这个指标不能单独表示阻断能力。",
        "",
        "图中真正有策略差异的是错误传播范围：Autonomous 为 1.70 跳，Simple Gate 为 1.40 跳，Dependency 与 Verify-All 均为 0.60 跳。C 分支在 22/22 个任务中保留，路由回溯在各自有资格的错误路由上均为 100%。这说明当前 benchmark 已证明局部传播控制，但没有证明 Dependency 比 Verify-All 的追溯或可用性更强。",
        "",
        "![four strategies three metrics](four_strategies_three_metrics.png)",
        "",
        "原始逐条件表仍见 `results/unified_workflow_v1_offline/report.md`；本图是汇总展示，不是 live 模型效果估计。",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")


def plot(out: Path, summaries: list[dict]) -> None:
    labels = [row["strategy"] for row in summaries]
    colors = [color for _arm, _label, color in STRATEGIES]
    x = list(range(len(labels)))
    values = [
        [row["propagation_mean_max_distance"] for row in summaries],
        [row["unrelated_retention"] for row in summaries],
        [row["trace_recall"] for row in summaries],
    ]
    # Use English inside the raster/vector figure because the execution
    # environment has no CJK font.  The accompanying report is bilingual in
    # meaning and gives the exact Chinese metric definitions.
    titles = [
        "Error propagation range\nmean maximum distance (hops; lower is better)",
        "Unrelated branch retention\nfinal C-task retention (higher is better)",
        "Traceability\nerror-route recall (when eligible)",
    ]
    y_limits = [(0, 2.05), (0, 1.12), (0, 1.12)]
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 5.2))
    for ax, vals, title, ylim in zip(axes, values, titles, y_limits):
        bars = ax.bar(x, vals, color=colors, width=0.62)
        for index, (bar, value) in enumerate(zip(bars, vals)):
            if index == 0:
                label = f"{value:.2f}"
            elif ylim[1] > 1.5:
                label = f"{value:.2f}"
            else:
                label = f"{value:.0%}"
            ax.text(bar.get_x() + bar.get_width() / 2, value + (ylim[1] * 0.025), label,
                    ha="center", va="bottom", fontsize=9)
        ax.set_title(title, fontsize=11)
        ax.set_xticks(x, labels, rotation=18, ha="right")
        ax.set_ylim(*ylim)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "Four strategies: cross-organization workflow safety",
        fontsize=14,
        y=0.99,
    )
    fig.text(
        0.02,
        0.015,
        "44 target-arm scripted replays from the 88-cell matrix; propagation averages 10 fault conditions; C retention is 22/22; traceability is conditional on an eligible error route.\n"
        "Mechanism control comparison, not a live-Agent error rate. Simple Gate = root_gate; Dependency and Verify-All have identical coverage here.",
        fontsize=8.8,
    )
    fig.subplots_adjust(top=0.78, bottom=0.27, left=0.06, right=0.98, wspace=0.28)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(out / f"four_strategies_three_metrics.{suffix}", dpi=200)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("results/unified_workflow_v1_offline/metrics.json"))
    parser.add_argument("--run-base", type=Path, default=Path("results/unified_workflow_v1_offline"))
    parser.add_argument("--out", type=Path, default=Path("results/workflow_v1_figures_20260910"))
    args = parser.parse_args()
    summaries = summarize(args.source, args.run_base)
    write_outputs(args.out, args.source, summaries)
    plot(args.out, summaries)


if __name__ == "__main__":
    main()
