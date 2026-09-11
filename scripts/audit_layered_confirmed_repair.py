#!/usr/bin/env python3
"""Audit whether the live confirmed-repair runs exposed a usable recovery action."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def iter_raw_files() -> Iterable[Path]:
    yield from sorted(
        (REPO / "results" / "layered_v1_live_pilot_01").glob(
            "*confirmed_repair_L4.json"
        )
    )
    yield from sorted(
        (REPO / "results" / "layered_v1_live_expanded_topologies_20260910").glob(
            "*confirmed_repair_L4.json"
        )
    )
    yield from sorted(
        (REPO / "results" / "layered_v1_live_l4_recovery_probe_20260910").glob(
            "probe_*/raw.json"
        )
    )


def fact_check_events(raw: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for exchange in raw.get("exchanges", []):
        if exchange.get("op") != "act":
            continue
        body = exchange.get("response", {}).get("batch", {}).get("body", {})
        for check in body.get("fact_checks", {}).values():
            events.extend(check.get("exchanges", []))
    return events


def contains_kind(value: Any, kind: str) -> bool:
    if isinstance(value, dict):
        if value.get("kind") == kind:
            return True
        return any(contains_kind(item, kind) for item in value.values())
    if isinstance(value, list):
        return any(contains_kind(item, kind) for item in value)
    return False


def rpc_counts(raw: dict[str, Any]) -> dict[str, int]:
    return {
        op: sum(exchange.get("op") == op for exchange in raw.get("exchanges", []))
        for op in ("revision", "envelope", "frontier", "rebuild")
    }


def audit_one(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    root_id = raw["reference_ids"]["root_A"]
    source_decisions = [
        decision
        for decision in raw["decisions"]
        if decision.get("stage") == "repair:source"
    ]
    if len(source_decisions) != 1:
        raise ValueError(f"expected one repair:source decision in {path}")
    decision = source_decisions[0]
    prompt = decision["public_input"]
    prompt_text = json.dumps(prompt, ensure_ascii=False)
    fact_events = fact_check_events(raw)
    old_statuses = [
        event.get("status")
        for event in fact_events
        if event.get("claim_id") == root_id
    ]
    new_candidate_confirmed = any(
        event.get("status") == "CONFIRMED"
        and event.get("query", {})
        .get("request", {})
        .get("body", {})
        .get("claim", {})
        .get("body", {})
        .get("fact", {})
        .get("value", {})
        == {"order": "A", "currency": "CNY", "cents": 125}
        for event in fact_events
    )
    action_surface_keys = (
        "authority_confirmation",
        "fact_resolution",
        "recovery_offer",
        "replacement_offer",
        "recovery_envelope",
        "repair_entry",
        "recovery_request",
        "available_operations",
    )
    counts = rpc_counts(raw)
    model_result = decision.get("model") or {}
    return {
        "file": str(path.relative_to(REPO)),
        "topology": raw["topology"],
        "layer": raw["layer"],
        "source_action": decision["draft"].get("action"),
        "source_reason": decision["draft"].get("reason"),
        "provider_error": model_result.get("provider_error"),
        "controller_old_claim_statuses": sorted(set(old_statuses)),
        "controller_old_claim_contradiction": "CONTRADICTED" in old_statuses,
        "candidate_125_confirmed": new_candidate_confirmed,
        "source_prompt_keys": sorted(prompt),
        "source_prompt_task_claim_count": len(prompt.get("task_claims", [])),
        "source_prompt_last_tool_result": prompt.get("last_tool_result"),
        "source_prompt_has_fact_reply": contains_kind(prompt, "fact_evidence_reply"),
        "source_prompt_action_surface_keys": [
            key for key in action_surface_keys if key in prompt_text
        ],
        "source_prompt_has_bound_recovery_flag": bool(
            prompt.get("capabilities", {}).get("bound_recovery")
        ),
        "source_prompt_blocked_count": len(prompt.get("local_view", {}).get("blocked", {})),
        "source_prompt_disputed_count": len(
            prompt.get("local_view", {}).get("disputed_claims", [])
        ),
        "rpc_counts_after_source_decision": counts,
        "recovery_calls_started": any(counts.values()),
        "source_model_action_opportunity": bool(
            contains_kind(prompt, "fact_evidence_reply")
            and any(key in prompt_text for key in action_surface_keys)
        ),
    }


def source_hashes() -> dict[str, str]:
    root = REPO
    return {
        str(path.relative_to(root)): sha256_file(path)
        for path in sorted((root / "trust_network").rglob("*.py"))
    }


def render_report(rows: list[dict[str, Any]]) -> str:
    actions = Counter(row["source_action"] for row in rows)
    all_hidden = all(
        not row["source_prompt_has_fact_reply"]
        and not row["source_prompt_action_surface_keys"]
        for row in rows
    )
    all_controller_proofs = all(row["controller_old_claim_contradiction"] for row in rows)
    all_no_recovery_calls = all(not row["recovery_calls_started"] for row in rows)
    lines = [
        "# `confirmed_repair` live 诊断",
        "",
        "本报告只审计已经完成的 MiniMax 原始运行，不重跑模型，也不把本报告的判断并入主 benchmark 指标。审计对象是原 15 条 pilot 中的 L4、两种扩展拓扑中的 L4，以及 3 条 L4 recovery probe，共 6 条运行。",
        "",
        "## 直接结论",
        "",
        f"6 条运行中 source 的修复阶段动作是：`hold` {actions.get('hold', 0)} 条、`verify` {actions.get('verify', 0)} 条、`proceed` {actions.get('proceed', 0)} 条。没有一次返回 `request_recovery`，但当前接口的 action 枚举本身只有 `proceed / verify / hold`。",
        "",
        f"调度器在 6/6 条运行中都能找到针对旧 `root_A=100` 的权威 `CONTRADICTED` 证据：{all_controller_proofs}。但这不是给新 `125` 修订签发的 `CONFIRMED` 证据；新候选的确认是在 `propose_revision` 被调用后才会发生，本批 6 条中没有任何一次调用该入口。",
        "",
        f"source 的模型输入在 6/6 条运行中都没有包含 fact evidence reply、recovery offer、recovery envelope 或可调用的恢复操作描述：{all_hidden}。输入只有空的 `task_claims`、`own_business_revision=125`、本地被 dispute/block 的旧声明，以及 `bound_recovery=true` 这个能力标志。",
        "",
        f"因此 6/6 条都没有进入 `revision → envelope → frontier → rebuild`：{all_no_recovery_calls}。这批数据不能回答“模型看到了明确恢复入口却拒绝请求”这一问题；它回答的是“模型在没有看到恢复入口时选择了安全 hold/verify”。",
        "",
        "## 为什么当前 hold 是合理的",
        "",
        "模型实际看到的是一条仍处于 dispute/block 状态的旧声明和一个未签名的本地业务修订值。系统 prompt 要求资料不足时 `hold`，并且把合法 action 限定为 `proceed、verify、hold`；它没有告诉模型 `repair:source` 的特殊语义，也没有给出 `request_recovery` 工具或动作。模型返回“先解决争议/缺少授权依据”符合这个可见状态下的安全策略。",
        "",
        "在一条 probe 中模型返回了 `verify`。`repair()` 对 source 只接受 `proceed`，任何 `verify` 或 `hold` 都直接返回；这里没有执行一次查询并把结果送回模型，和系统 prompt 所说的“verify 后续需重新决定”不一致。因此这条也不能被归为模型拒绝恢复。",
        "",
        "## 代码层面的原因",
        "",
        "1. `trust_network/benchmark/layered/engine.py:14-18` 的 schema 没有 `request_recovery`；`engine.py:175-176` 会把任何新动作归一成 `hold`。",
        "2. `engine.py:254` 给 `repair:source` 的 `task_claims` 是空数组，只附加 `own_business_revision`；`engine.py:258-267` 是控制器在模型决定之后私下从 RPC 日志提取旧声明的 contradiction proof。该 proof 没有进入 source prompt。",
        "3. 只有 source 返回 `proceed`，控制器才调用 `revision`；`backend.py:174-181` 的 revision、envelope 等接口不是模型可调用的动作。`bound_recovery=true` 只是布尔提示。",
        "4. `dispute_protocol.py:131-160` 会在 `revision` 之后为新 125 候选重新查询权威并要求 `CONFIRMED`；所以当前运行中不存在“模型已经看过新候选的权威确认”这一事实。",
        "5. 即使 source 入口修正，`engine.py:277-289` 给派生声明的恢复决定仍只传 parent ID 列表，没有结构化的 old claim、replacement parent、rebuild operation 和 fact reference；这会继续诱发下游 hold/verify。",
        "",
        "## 应如何重做这个 live 条件",
        "",
        "下一版应把修复请求作为显式协议动作，例如 `request_recovery`，并在模型输入中绑定旧声明、受影响 batch、已签名的 contradiction proof、本地可引用的修订事实和可调用的 recovery operation。模型只选择事实引用和是否请求恢复，worker 负责重新查询新候选的权威确认、签发 offer、生成绑定 envelope，并把每个派生重建节点作为结构化新决定交给对应 issuer。`verify` 必须真的执行查询并形成后续模型回合。",
        "",
        "修正后的实验应把结果分成：模型请求恢复、模型 hold/verify、程序接受入口、程序拒绝错误修订、派生重建完成。只有在模型输入真正包含这些条件后，`hold` 才能作为恢复可用性负结果解释。",
        "",
        "## 逐条审计数据",
        "",
        "|运行|拓扑|source动作|旧声明权威状态|新125已确认|模型输入有恢复入口|revision/envelope/frontier/rebuild|",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        counts = row["rpc_counts_after_source_decision"]
        calls = "/".join(str(counts[key]) for key in ("revision", "envelope", "frontier", "rebuild"))
        lines.append(
            f"|`{Path(row['file']).name}`|`{row['topology']}`|`{row['source_action']}`|`{','.join(row['controller_old_statuses']) if 'controller_old_statuses' in row else ','.join(row['controller_old_claim_statuses'])}`|{row['candidate_125_confirmed']}|{row['source_model_action_opportunity']}|`{calls}`|"
        )
    lines.extend(
        [
            "",
            "原始运行目录仍保留在 `results/layered_v1_live_pilot_01/`、`results/layered_v1_live_expanded_topologies_20260910/` 和 `results/layered_v1_live_l4_recovery_probe_20260910/`；本报告没有复制 worker 私有状态。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    if output.exists():
        parser.error(f"output already exists: {output}")
    paths = list(iter_raw_files())
    if len(paths) != 6:
        raise SystemExit(f"expected six L4 confirmed_repair raw files, found {len(paths)}")
    rows = [audit_one(path) for path in paths]
    output.mkdir(parents=True)
    write_json(output / "audit.json", {"runs": rows})
    write_json(
        output / "provenance.json",
        {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "purpose": "diagnose model-visible confirmed_repair recovery preconditions",
            "input_files": {
                str(path.relative_to(REPO)): sha256_file(path) for path in paths
            },
            "source_hashes": source_hashes(),
            "paid_calls": 0,
        },
    )
    (output / "report.md").write_text(render_report(rows) + "\n")
    manifest = {
        name: sha256_file(output / name)
        for name in ("audit.json", "provenance.json", "report.md")
    }
    write_json(output / "artifact_manifest.json", manifest)
    print(json.dumps({"output": str(output), "runs": len(rows), "paid_calls": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
