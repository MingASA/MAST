"""Plot the offline contribution experiment without calling a model.

The script consumes the archived contribution metrics and writes descriptive
figures plus fixed-denominator tables.  It does not alter the raw run files.
"""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


FREEZE_CELLS = [
    ("routed", "dependency", "Routed\nDependency"),
    ("routed", "recipient_workload", "Routed\nWorkload freeze"),
    ("broadcast", "dependency", "Broadcast\nDependency"),
    ("broadcast", "recipient_workload", "Broadcast\nWorkload freeze"),
]
VIEWS = [
    ("full", "Full"),
    ("no_receipts", "No receipts"),
    ("ordinary_logs", "Ordinary logs"),
    ("opaque_relay", "Opaque relay"),
]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in rows)


def freeze_summary(rows: list[dict]) -> list[dict]:
    result = []
    for fault in ("coordinator", "middle_a"):
        for notice, scope, label in FREEZE_CELLS:
            row = next(
                item
                for item in rows
                if item["fault"] == fault
                and item["notice_scope"] == notice
                and item["freeze_scope"] == scope
            )
            result.append(
                {
                    "fault": fault,
                    "notice_scope": notice,
                    "freeze_scope": scope,
                    "cell": label.replace("\n", " "),
                    "unsafe_completion_count": row["unsafe_completion_count"],
                    "affected_task_count": row["affected_task_count"],
                    "affected_tasks_blocked": row["affected_tasks_blocked"],
                    "unaffected_tasks_completed": row["unaffected_tasks_completed"],
                    "unaffected_task_count": row["unaffected_task_count"],
                    "unaffected_retention": row["unaffected_retention"],
                    "overfrozen_tasks": row["overfrozen_tasks"],
                    "notice_attempts": row["notice_attempts"],
                    "notice_receipts": row["notice_receipts"],
                    "notice_bytes": row["notice_bytes"],
                    "receipt_bytes": row["receipt_bytes"],
                    "reference_id": row["reference_id"],
                }
            )
    return result


def count_metric(rows: list[dict], field: str) -> dict:
    true_positive = sum(row[field]["true_positive"] for row in rows)
    expected = sum(row[field]["expected"] for row in rows)
    predicted = sum(row[field]["predicted"] for row in rows)
    false_positive = sum(row[field]["false_positive"] for row in rows)
    return {
        "true_positive": true_positive,
        "expected": expected,
        "predicted": predicted,
        "false_positive": false_positive,
        "recall": true_positive / expected if expected else None,
        "precision": true_positive / predicted if predicted else None,
    }


def trace_summary(rows: list[dict]) -> list[dict]:
    clean = [row for row in rows if row["fault"] == "none"]
    summaries = []
    for view, label in VIEWS:
        selected = [row for row in clean if row["view"] == view]
        verified = count_metric(selected, "routes_verified")
        estimate = count_metric(selected, "routes_unsigned_estimate")
        sources = count_metric(selected, "source_identity")
        duties = count_metric(selected, "duty_violations")
        negative_count = sum(row["negative_actions"] for row in selected)
        false_accusations = sum(row["false_accusations"] for row in selected)
        summaries.append(
            {
                "view": view,
                "label": label,
                "route_verified_tp": verified["true_positive"],
                "route_expected": verified["expected"],
                "route_verified_predicted": verified["predicted"],
                "route_verified_recall": verified["recall"],
                "route_verified_precision": verified["precision"],
                "route_estimate_tp": estimate["true_positive"],
                "route_estimate_expected": estimate["expected"],
                "route_estimate_predicted": estimate["predicted"],
                "route_estimate_recall": estimate["recall"],
                "route_estimate_precision": estimate["precision"],
                "source_tp": sources["true_positive"],
                "source_expected": sources["expected"],
                "source_recall": sources["recall"],
                "duty_tp": duties["true_positive"],
                "duty_expected": duties["expected"],
                "duty_recall": duties["recall"],
                "negative_cases": negative_count,
                "false_accusations": false_accusations,
                "false_accusation_rate": false_accusations / negative_count if negative_count else None,
            }
        )
    return summaries


def plot_freeze(out: Path, rows: list[dict]) -> None:
    x = list(range(len(FREEZE_CELLS)))
    colors = {"coordinator": "#2f78a8", "middle_a": "#d88b1f"}
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.1))
    for fault, offset in (("coordinator", -0.18), ("middle_a", 0.18)):
        selected = [row for row in rows if row["fault"] == fault]
        selected.sort(key=lambda row: [
            (row["notice_scope"], row["freeze_scope"])
        ])
        # The explicit order above is replaced below so routed/broadcast and
        # dependency/workload remain visually aligned with FREEZE_CELLS.
        selected = [
            next(
                row
                for row in rows
                if row["fault"] == fault
                and row["notice_scope"] == notice
                and row["freeze_scope"] == scope
            )
            for notice, scope, _label in FREEZE_CELLS
        ]
        positions = [value + offset for value in x]
        retention = [row["unaffected_retention"] for row in selected]
        bars = axes[0].bar(positions, retention, width=0.34, label=fault, color=colors[fault])
        for bar, value in zip(bars, retention):
            axes[0].text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.025,
                f"{value:.0%}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
        overfreeze = [row["overfrozen_tasks"] for row in selected]
        bars = axes[1].bar(positions, overfreeze, width=0.34, label=fault, color=colors[fault])
        for bar, value in zip(bars, overfreeze):
            axes[1].text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.07,
                str(value),
                ha="center",
                va="bottom",
                fontsize=8,
            )

    labels = [label for _notice, _scope, label in FREEZE_CELLS]
    for ax in axes:
        ax.set_xticks(x, labels, rotation=16, ha="right")
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, title="fault location")
    axes[0].set_ylim(0, 1.16)
    axes[0].set_ylabel("unaffected task retention")
    axes[0].set_title("Unrelated work retained\n(higher is better)")
    axes[1].set_ylim(0, 3.7)
    axes[1].set_ylabel("over-frozen unaffected tasks")
    axes[1].set_title("Collateral freeze\n(lower is better)")
    fig.suptitle("Notice scope × freeze granularity", fontsize=14, y=0.99)
    fig.text(
        0.02,
        0.015,
        "All eight cells block 100% of affected tasks and produce 0 unsafe completions. "
        "Routed/broadcast changes notice cost; dependency/workload changes collateral effects.",
        fontsize=9,
    )
    fig.subplots_adjust(top=0.79, bottom=0.28, left=0.07, right=0.98, wspace=0.25)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(out / f"freeze_four_cells.{suffix}", dpi=200)
    plt.close(fig)


def _draw_bars(ax, x, values, color, label, formatter, width=0.34, offset=0.0):
    clean_values = [float("nan") if value is None else value for value in values]
    bars = ax.bar([value + offset for value in x], clean_values, width=width, color=color, label=label)
    for bar, value in zip(bars, values):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            text = "—"
            y = 0.035
        else:
            text = formatter(value)
            y = value + 0.035
        ax.text(bar.get_x() + bar.get_width() / 2, y, text, ha="center", va="bottom", fontsize=8)
    return bars


def plot_traceability(out: Path, rows: list[dict]) -> None:
    x = list(range(len(VIEWS)))
    labels = [label for _view, label in VIEWS]
    fig, axes = plt.subplots(2, 2, figsize=(14, 8.8))
    axes = list(axes.flat)
    verified = [row["route_verified_recall"] for row in rows]
    estimated = [row["route_estimate_recall"] for row in rows]
    _draw_bars(axes[0], x, verified, "#2f78a8", "verified", lambda value: f"{value:.0%}", offset=-0.18)
    _draw_bars(axes[0], x, estimated, "#d88b1f", "ordinary-log estimate", lambda value: f"{value:.0%}", offset=0.18)
    axes[0].set_title("Route recall\nfixed denominator: 50 actual routes")

    verified_precision = [row["route_verified_precision"] for row in rows]
    estimated_precision = [row["route_estimate_precision"] for row in rows]
    _draw_bars(axes[1], x, verified_precision, "#2f78a8", "verified", lambda value: f"{value:.0%}", offset=-0.18)
    _draw_bars(axes[1], x, estimated_precision, "#d88b1f", "ordinary-log estimate", lambda value: f"{value:.0%}", offset=0.18)
    axes[1].set_title("Route precision\nno predictions shown as —")

    source_recall = [row["source_recall"] for row in rows]
    _draw_bars(axes[2], x, source_recall, "#238b68", "signed source identity", lambda value: f"{value:.0%}")
    axes[2].set_title("Source identity recall\nfixed denominator: 10 root identities")

    duty_recall = [row["duty_recall"] for row in rows]
    false_rate = [row["false_accusation_rate"] for row in rows]
    _draw_bars(axes[3], x, duty_recall, "#238b68", "violation recall", lambda value: f"{value:.0%}", offset=-0.18)
    _draw_bars(axes[3], x, false_rate, "#b54b4b", "false-accusation rate", lambda value: f"{value:.0%}", offset=0.18)
    axes[3].set_title("Duty labels\n1 positive and 4 negative cases")

    for ax in axes:
        ax.set_xticks(x, labels, rotation=16, ha="right")
        ax.set_ylim(0, 1.18)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Fixed-denominator forensic comparison", fontsize=14, y=0.99)
    fig.text(
        0.02,
        0.015,
        "Five fixed executions × ten actual routes = 50 route denominator; source identity = 10; duty labels = 1 positive / 4 negatives. "
        "Verified evidence and unsigned ordinary-log estimates are separate quantities.",
        fontsize=8.8,
    )
    fig.subplots_adjust(top=0.87, bottom=0.19, left=0.06, right=0.98, hspace=0.48, wspace=0.24)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(out / f"traceability_fixed_denominator.{suffix}", dpi=200)
    plt.close(fig)


def write_report(out: Path, freeze: list[dict], trace: list[dict], forensic: list[dict]) -> None:
    invalid_faults = [
        row
        for row in forensic
        if row["fault"] != "none" and not row["observation_changed_by_fault"]
    ]
    changed_faults = [
        row
        for row in forensic
        if row["fault"] != "none" and row["observation_changed_by_fault"]
    ]
    lines = [
        "# 协议贡献对照图与结果",
        "",
        "来源：`results/contribution_experiment_v1_20260910/metrics.json`。全量为 8 个冻结条件和 140 个证据投影，均为离线 scripted 控制，模型调用为 0。",
        "",
        "## 冻结四格",
        "",
        "|故障位置|通知范围|冻结粒度|受影响任务错误完成|无关任务保留|过度冻结|通知尝试/签收|",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in freeze:
        lines.append(
            f"|{row['fault']}|{row['notice_scope']}|{row['freeze_scope']}|"
            f"{row['unsafe_completion_count']}/{row['affected_task_count']}|"
            f"{row['unaffected_tasks_completed']}/{row['unaffected_task_count']} "
            f"({row['unaffected_retention']:.0%})|{row['overfrozen_tasks']}|"
            f"{row['notice_attempts']}/{row['notice_receipts']}|"
        )
    lines += [
        "",
        "冻结图的因果含义是清楚的：同一撤销和同一发现时点下，`dependency` 只冻结受影响依赖，保留无关任务；`recipient_workload` 会把收到撤销的组织的无关任务一起停掉。通知从 routed 改成 broadcast 只增加通知尝试和字节，不改变固定冻结粒度下的安全效果。所有格子都阻断了受影响任务，没有把通知延迟或广播本身误记为错误完成。",
        "",
        "## 固定分母追溯",
        "",
        "|证据视图|可证路线回溯|普通日志路线估计|可证路线精确率|来源身份回溯|义务违约回溯|负例误指控率|",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in trace:
        def pct(value):
            return "—" if value is None else f"{value:.0%}"
        lines.append(
            f"|{row['label']}|{row['route_verified_tp']}/{row['route_expected']} "
            f"({pct(row['route_verified_recall'])})|"
            f"{row['route_estimate_tp']}/{row['route_estimate_expected']} "
            f"({pct(row['route_estimate_recall'])})|"
            f"{pct(row['route_verified_precision'])}|"
            f"{row['source_tp']}/{row['source_expected']} ({pct(row['source_recall'])})|"
            f"{row['duty_tp']}/{row['duty_expected']} ({pct(row['duty_recall'])})|"
            f"{row['false_accusations']}/{row['negative_cases']} "
            f"({pct(row['false_accusation_rate'])})|"
        )
    lines += [
        "",
        "这里的 50 条实际路线、10 个根来源身份和 1 个正例/4 个负例在所有 clean view 中固定。完整证据可以验证路线；ordinary logs 在诚实条件下仍能给出 50/50 的估计，但没有可验证签名证据。`no_receipts` 仍保留本地撤销和使用顺序，因此可以识别义务违约，却不能证明全部交接已签收。`opaque_relay` 对路线和身份保持不可判定。",
        "",
        "## 无效条件",
        "",
        f"证据投影共有 140 条：20 条 clean baseline，120 条故障投影；其中 58 条故障确实改变了公开观察，62 条故障投影因目标视图已经移除了对应材料或该材料不存在而不适用。无效投影被保留在原始数据中，但没有当作成功检测。",
        "",
        "|故障|未改变观察的投影数|说明|",
        "|---|---:|---|",
    ]
    from collections import Counter

    invalid_counts = Counter(row["fault"] for row in invalid_faults)
    for fault in ("reorder", "missing_notice", "missing_link", "missing_receipt", "tampered_receipt", "ambiguous_route"):
        lines.append(
            f"|{fault}|{invalid_counts[fault]}|目标视图中没有可供该故障再次删除或改变的材料，按任务书标为不可比较|"
        )
    lines += [
        "",
        "原始逐条结果和 canonical manifest 位于 `results/contribution_experiment_v1_20260910/`；两张图只做汇总展示。该实验支持的结论是：协议的冻结贡献来自依赖粒度，追溯贡献来自可验证签收、来源链和顺序证据；它不支持现实网络错误率或法律责任准确率的外推。",
        "",
        "![freeze four cells](freeze_four_cells.png)",
        "",
        "![fixed denominator traceability](traceability_fixed_denominator.png)",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    (out / "summary.json").write_text(
        json.dumps(
            {
                "freeze_conditions": len(freeze),
                "forensic_projections": len(forensic),
                "forensic_fault_projections": len(forensic) - 20,
                "changed_fault_projections": len(changed_faults),
                "inapplicable_fault_projections": len(invalid_faults),
                "model_calls": 0,
                "tokens": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads((args.result / "metrics.json").read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    freeze = freeze_summary(data["freeze"])
    trace = trace_summary(data["forensics"])
    write_csv(
        args.out / "freeze_chart_data.csv",
        freeze,
        list(freeze[0].keys()),
    )
    write_csv(
        args.out / "traceability_chart_data.csv",
        trace,
        list(trace[0].keys()),
    )
    write_csv(
        args.out / "invalid_conditions.csv",
        [
            {
                "case": row["case"],
                "view": row["view"],
                "fault": row["fault"],
                "observation_changed_by_fault": row["observation_changed_by_fault"],
            }
            for row in data["forensics"]
            if row["fault"] != "none"
        ],
        ["case", "view", "fault", "observation_changed_by_fault"],
    )
    plot_freeze(args.out, freeze)
    plot_traceability(args.out, trace)
    write_report(args.out, freeze, trace, data["forensics"])
    (args.out / "provenance.json").write_text(
        json.dumps(
            {
                "source": str(args.result / "metrics.json"),
                "source_sha256": hashlib.sha256((args.result / "metrics.json").read_bytes()).hexdigest(),
                "decision_source": "scripted",
                "new_model_calls": 0,
                "fixed_denominators": {"routes": 50, "source_identities": 10, "duty_positive": 1, "duty_negatives": 4},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
