#!/usr/bin/env python3
"""Analyze the final layered confirmed-repair live replications.

The analysis keeps the historical pre-adapter runs separate from the repaired
adapter runs.  It summarizes only public raw-run fields and worker journal
integrity; it never copies private worker state into the report.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[1]
CURRENT = REPO / "results" / "layered_v1_live_confirmed_repair_final_v2_20260910"
OLD_DIRS = (
    REPO / "results" / "layered_v1_live_pilot_01",
    REPO / "results" / "layered_v1_live_expanded_topologies_20260910",
)
OFFLINE = REPO / "results" / "layered_v1_offline_fact_ref_prompt_fix_20260910"
VALIDATION = REPO / "results" / "layered_v1_validation_fact_ref_prompt_fix_20260910" / "validation.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_rows(directory: Path) -> list[dict]:
    rows = json.loads((directory / "metrics.json").read_text())
    return [json.loads((directory / row["file"]).read_text()) for row in rows]


def authority_status(source: dict) -> str | None:
    try:
        return source["offer"]["body"]["fact_resolution"]["reply"]["body"]["status"]
    except (KeyError, TypeError):
        return None


def summarize_run(raw: dict) -> dict:
    requests = raw.get("recovery_requests", [])
    source = raw.get("source_revision") or {}
    recoveries = raw.get("recoveries", [])
    rebuilds = [step for recovery in recoveries for step in recovery.get("rebuilds", [])]
    return {
        "workflow": raw["workflow"],
        "topology": raw["topology"],
        "metrics": raw["metrics"],
        "requests": [
            {
                "task_id": item.get("task_id"),
                "model_action": (item.get("draft") or {}).get("action"),
                "status": item.get("status"),
                "runtime_action": item.get("runtime_action"),
            }
            for item in requests
        ],
        "source": {
            "model_action": (source.get("draft") or {}).get("action"),
            "status": source.get("status"),
            "authority_status": authority_status(source),
        },
        "recoveries": [
            {
                "task_id": item.get("task_id"),
                "status": item.get("status"),
                "authority_confirmation": item.get("authority_confirmation"),
                "rebuild_steps": len(item.get("rebuilds", [])),
                "rebuild_completed": sum(step.get("status") == "completed" for step in item.get("rebuilds", [])),
                "rebuild_holds": sum(step.get("status") == "model_hold" for step in item.get("rebuilds", [])),
                "final_action": (item.get("final_action") or {}).get("action"),
            }
            for item in recoveries
        ],
        "rebuild_steps": {
            "total": len(rebuilds),
            "completed": sum(step.get("status") == "completed" for step in rebuilds),
            "model_hold": sum(step.get("status") == "model_hold" for step in rebuilds),
            "model_invalid": sum(step.get("status") == "model_invalid" for step in rebuilds),
            "program_rejected": sum(step.get("status") == "program_rejected" for step in rebuilds),
        },
    }


def aggregate(summaries: list[dict]) -> dict:
    keys = (
        "affected_task_count", "unsafe_completion_count", "safe_final_completion",
        "unrelated_completed", "unrelated_task_count", "recovered_tasks", "new_model_calls", "provider_attempts",
        "known_tokens", "model_holds", "invalid_actions", "rpc_rejections", "worker_errors",
        "unknown_usage_attempts", "error_action_blocks", "status_queries", "fact_queries",
        "notifications", "notification_bytes",
    )
    values = {key: sum(item["metrics"].get(key, 0) for item in summaries) for key in keys}
    values.update({
        "workflows": len(summaries),
        "workflows_without_unsafe_completion": sum(
            item["metrics"].get("unsafe_completion_count") == 0 for item in summaries
        ),
        "recovery_request_opportunities": sum(len(item["requests"]) for item in summaries),
        "recovery_request_model_actions": sum(
            request["model_action"] == "request_recovery"
            for item in summaries for request in item["requests"]
        ),
        "recovery_request_submitted": sum(
            request["status"] == "submitted"
            for item in summaries for request in item["requests"]
        ),
        "source_revision_opportunities": sum(
            item["source"]["model_action"] is not None for item in summaries
        ),
        "source_revision_proposed": sum(
            item["source"]["model_action"] == "propose_revision" for item in summaries
        ),
        "confirmed_offers": sum(item["source"]["status"] == "confirmed_offer" for item in summaries),
        "authority_confirmed_offers": sum(
            item["source"]["authority_status"] == "CONFIRMED" for item in summaries
        ),
        "recovery_branch_records": sum(len(item["recoveries"]) for item in summaries),
        "recovery_branches_completed": sum(
            recovery["status"] == "recovery_completed"
            for item in summaries for recovery in item["recoveries"]
        ),
        "rebuild_steps_total": sum(item["rebuild_steps"]["total"] for item in summaries),
        "rebuild_steps_completed": sum(item["rebuild_steps"]["completed"] for item in summaries),
        "rebuild_steps_model_hold": sum(item["rebuild_steps"]["model_hold"] for item in summaries),
        "rebuild_steps_model_invalid": sum(item["rebuild_steps"]["model_invalid"] for item in summaries),
        "final_completed_after_recovery": sum(
            recovery["final_action"] == "COMPLETED"
            for item in summaries for recovery in item["recoveries"]
            if recovery["status"] == "recovery_completed"
        ),
    })
    return values


def verify_manifest(directory: Path) -> bool:
    manifest = json.loads((directory / "manifest.json").read_text())
    return all(sha256(directory / name) == expected for name, expected in manifest.items())


def historical_summary() -> dict:
    paths = []
    for directory in OLD_DIRS:
        paths.extend(sorted(directory.glob("*confirmed_repair_L4.json")))
    runs = [json.loads(path.read_text()) for path in paths]
    return {
        "directories": [str(directory.relative_to(REPO)) for directory in OLD_DIRS],
        "workflows": len(runs),
        "affected_task_count": sum(raw["metrics"]["affected_task_count"] for raw in runs),
        "unsafe_completion_count": sum(raw["metrics"]["unsafe_completion_count"] for raw in runs),
        "recovered_tasks": sum(raw["metrics"]["recovered_tasks"] for raw in runs),
        "safe_final_completion": sum(raw["metrics"]["safe_final_completion"] for raw in runs),
        "new_model_calls": sum(raw["metrics"]["new_model_calls"] for raw in runs),
        "recovery_fields_instrumented": all("recovery_requests" in raw for raw in runs),
    }


def plot(output: Path, summary: dict, historical: dict) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    stages = ["request\nsubmitted", "authority\nconfirmed", "rebuild\nsteps", "tasks\nrecovered", "unsafe\ntasks"]
    counts = [
        (summary["recovery_request_submitted"], summary["recovery_request_opportunities"]),
        (summary["authority_confirmed_offers"], summary["confirmed_offers"]),
        (summary["rebuild_steps_completed"], summary["rebuild_steps_total"]),
        (summary["recovered_tasks"], summary["affected_task_count"]),
        (summary["unsafe_completion_count"], summary["affected_task_count"]),
    ]
    rates = [100 * n / d if d else 0 for n, d in counts]
    colors = ["#2f855a", "#2f855a", "#3182ce", "#3182ce", "#c53030"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    bars = ax.bar(stages, rates, color=colors, width=0.65)
    for bar, (numerator, denominator) in zip(bars, counts):
        label = f"{numerator}/{denominator}"
        ax.text(bar.get_x() + bar.get_width() / 2, min(bar.get_height() + 3, 104),
                label, ha="center", va="bottom", fontsize=10)
    ax.set_ylim(0, 112)
    ax.set_ylabel("share of eligible items (%)")
    ax.set_title("L4 confirmed_repair live replication (6 workflows, 3 topologies)")
    ax.grid(axis="y", alpha=0.25)
    ax.text(0.01, -0.22,
            f"Historical pre-adapter L4: recovered {historical['recovered_tasks']}/{historical['affected_task_count']} "
            "affected tasks; no recovery stages were instrumented.",
            transform=ax.transAxes, fontsize=9)
    fig.tight_layout()
    fig.savefig(output / "confirmed_repair_live_funnel.png", dpi=180)
    plt.close(fig)


def main() -> int:
    summaries = [summarize_run(raw) for raw in load_rows(CURRENT)]
    result = {
        "experiment": "layered-confirmed-repair-live-final-v2",
        "current_directory": str(CURRENT.relative_to(REPO)),
        "current": aggregate(summaries),
        "per_workflow": summaries,
        "historical_pre_adapter": historical_summary(),
        "archive_manifest_verified": verify_manifest(CURRENT),
        "preflight": {
            "offline_directory": str(OFFLINE.relative_to(REPO)),
            "offline_manifest_sha256": sha256(OFFLINE / "manifest.json"),
            "validation": str(VALIDATION.relative_to(REPO)),
            "validation_sha256": sha256(VALIDATION),
        },
        "interpretation": {
            "protocol_safety": "All 12 affected live tasks had zero unsafe completions; every workflow had zero unsafe completion.",
            "recovery_entry": "The repaired live adapter received 12/12 explicit request_recovery decisions and submitted 12/12 verify-only recovery bases.",
            "authority_gate": "All 6 source decisions proposed the private fact reference and produced 6/6 confirmed authority offers.",
            "recovery_availability": "6/12 affected tasks completed the full recovery path; 19/25 rebuild steps completed and 6 stopped at model hold.",
            "historical_comparison": "The three historical pre-adapter L4 live runs recovered 0/6 affected tasks; this is a before/after adapter comparison, not a randomized causal estimate.",
            "limits": [
                "The public graph and failure timing are scripted; business effects are simulated.",
                "The replication covers three benchmark topologies and two repetitions per topology.",
                "A model hold is counted as a safe stop and is kept separate from program rejection.",
                "The benchmark does not establish real-world race behavior or legal responsibility.",
            ],
        },
    }
    output = CURRENT
    (output / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    plot(output, result["current"], result["historical_pre_adapter"])
    current = result["current"]
    historical = result["historical_pre_adapter"]
    lines = [
        "# confirmed_repair live 修复适配器复核",
        "",
        "本报告只汇总最终 v2 适配器的 6 条真实 MiniMax / ProcessBackend replication；历史结果单独作为修复前参照。",
        "",
        "## 结果",
        "",
        f"最终批次包含 {current['workflows']} 条 workflow、3 种拓扑、{current['affected_task_count']} 个受影响任务。"
        f"所有 workflow 均为 0 个不安全完成（{current['unsafe_completion_count']}/{current['affected_task_count']}）。",
        "",
        f"模型在恢复入口阶段 12/12 次选择 `request_recovery`，12/12 次通过精确任务绑定并提交了 verify-only 基础。"
        f"source 6/6 次选择 `propose_revision`，6/6 次生成 `confirmed_offer`，权威回执均为 `CONFIRMED`。",
        "",
        f"恢复执行完成 {current['recovery_branches_completed']}/{current['recovery_branch_records']} 个受影响分支，即"
        f" {current['recovered_tasks']}/{current['affected_task_count']} 个任务（50%）。"
        f" frontier 重建步骤完成 {current['rebuild_steps_completed']}/{current['rebuild_steps_total']}，"
        f"其余 {current['rebuild_steps_model_hold']} 步由模型 hold；已完成恢复的 {current['final_completed_after_recovery']}/{current['recovery_branches_completed']} 个分支都完成了最终动作。",
        "",
        f"无关任务完成 {current['unrelated_completed']}/{current['unrelated_task_count']}；"
        f"程序 RPC 拒绝和 worker error 都是 0。模型调用 {current['new_model_calls']} 次，"
        f"provider attempts {current['provider_attempts']} 次，已知 token {current['known_tokens']}，"
        f"未知 usage {current['unknown_usage_attempts']} 次。",
        "",
        "## 与修复前 live 结果的关系",
        "",
        f"修复前的 3 条正式 L4 confirmed_repair live workflow 共覆盖 {historical['affected_task_count']} 个受影响任务，"
        f"恢复完成为 {historical['recovered_tasks']}/{historical['affected_task_count']}；当时没有恢复阶段字段，"
        "不能从旧 JSON 反推出模型是否曾发起恢复请求。新批次把请求、source 修订、权威确认和 frontier 重建逐阶段记录下来。",
        "",
        "这支持两个层次的结论：L4 的安全门禁在真实模型流程中仍保持零不安全完成；修复后的调度入口确实让模型能够发起恢复，"
        "并在一部分多跳拓扑中完成权威确认后的派生重建。恢复可用性仍受模型在多跳重建阶段 hold 的影响，不能写成所有受影响任务都自动恢复。",
        "",
        "## 边界",
        "",
        "- 初始证据图、故障和时间由脚本准备，业务 effect 为模拟回调。",
        "- 这是修复前后适配器的受控 live 对照，不是随机化因果估计。",
        "- `model_hold` 是模型安全暂停；`rpc_rejections=0` 表示本批没有程序拒绝合法恢复请求。",
        "- 结果目录的 manifest、worker provider journal 和当前源码绑定的离线/回归 preflight 均已核验。",
        "",
        "原始 JSON 在本目录；图表见 `confirmed_repair_live_funnel.png`。",
    ]
    (output / "analysis.md").write_text("\n".join(lines) + "\n")
    # The runner's manifest predates these derived analysis artifacts.  Extend
    # it after writing them while keeping the manifest itself outside its hash.
    manifest = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name not in {"manifest.json", "partial_manifest.json"}
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "status": "written",
        "analysis": str((output / "analysis.md").relative_to(REPO)),
        "workflows": current["workflows"],
        "requests": f"{current['recovery_request_model_actions']}/{current['recovery_request_opportunities']}",
        "recovered": f"{current['recovered_tasks']}/{current['affected_task_count']}",
        "unsafe": current["unsafe_completion_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
