#!/usr/bin/env python3
"""Export a compact, read-only replay from the checked-in final MAST archive."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

FIXTURE_ID = "final-v1:long_chain_fork:confirmed_repair:business-1"
ARCHIVE = Path("results/final_unified_live_v1_combined_20260911")


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def short(value: str) -> str:
    return f"{value[:6]}…{value[-3:]}"


def digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def find_result(root: Path, row: dict) -> Path:
    path = root / row["result_path"]
    if not path.is_file():
        raise FileNotFoundError(f"final result source is missing: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != row["result_sha256"]:
        raise ValueError(f"result checksum mismatch: {path}")
    return path


def event_counts(raw: dict) -> dict[str, dict[str, int]]:
    result = {}
    for org, export in raw["exports"].items():
        counts: dict[str, int] = {}
        for packet in export["events"]:
            action = packet["body"]["action"]
            counts[action] = counts.get(action, 0) + 1
        result[org] = counts
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent / "public" / "replay.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    plan = load(root / ARCHIVE / "plan.json")
    aggregate = load(root / ARCHIVE / "aggregate.json")
    task_metrics = load(root / ARCHIVE / "task_metrics.json")

    fixtures = [f for f in plan["fixtures"] if f["fixture_id"] == FIXTURE_ID]
    if len(fixtures) != 1:
        raise ValueError("selected fixture is not unique in final plan")
    fixture = fixtures[0]
    rows = {r["layer"]: r for r in aggregate
            if r["fixture_id"] == FIXTURE_ID and r["layer"] in ("L0", "L4")}
    if set(rows) != {"L0", "L4"} or any(r["status"] != "completed" for r in rows.values()):
        raise ValueError("selected final L0/L4 pair is unavailable")
    runs = {layer: load(find_result(root, row)) for layer, row in rows.items()}
    per_task = {layer: [m for m in task_metrics
                        if m["fixture_id"] == FIXTURE_ID and m["layer"] == layer]
                for layer in ("L0", "L4")}

    # Runtime truth carries the actual signed packet IDs. Its lineage arrays are
    # digest-sorted sets, so map each known plan role explicitly.
    claim_ids = {}
    lineage = runs["L4"]["raw"]["truth"]["task_lineage"]
    claim_ids.update({
        "root_A": lineage["A_a"][0], "shared_A": lineage["A_a"][2],
        "common_A": lineage["A_a"][1], "branch_A_a": lineage["A_a"][3],
        "branch_A_b": lineage["A_b"][3], "root_C": lineage["C_a"][0],
        "shared_C": lineage["C_a"][2], "common_C": lineage["C_a"][3],
        "branch_C_a": lineage["C_a"][1], "branch_C_b": lineage["C_b"][1],
    })

    l4 = runs["L4"]["raw"]
    revision = l4["source_revision"]
    new_root = revision["offer"]["body"]["new"]
    rebuilds = l4["recoveries"][0]["rebuilds"]
    compact_rebuilds = [{
        "old": item["old"], "old_short": short(item["old"]),
        "issuer": item["issuer"], "status": item["status"],
        "new": digest(item["packet"]),
        "new_short": short(digest(item["packet"])),
        "action_authorized": item["result"]["action_authorized"],
    } for item in rebuilds]

    routes = {}
    for layer in ("L0", "L4"):
        routes[layer] = [{
            "sender": route["sender"], "receiver": route["recipient"],
            "claim_keys": route["refs"], "accepted": route["accepted"],
            "tick": route["tick"],
            "signed": route.get("packet", {}).get("signature") is not None,
            "receipt": route.get("receipt", {}).get("body", {}).get("status"),
        } for route in runs[layer]["raw"]["routes"]]

    issuer_for = {"root_A":"source", "root_C":"source", "shared_A":"chain_1",
                  "shared_C":"chain_1", "common_A":"chain_2", "common_C":"chain_2",
                  "branch_A_a":"branch_a", "branch_C_a":"branch_a",
                  "branch_A_b":"branch_b", "branch_C_b":"branch_b"}
    claim_catalog = {}
    for key, body in fixture["graph"]["claims"].items():
        route = next((r for r in routes["L4"] if key in r["claim_keys"]), None)
        claim_catalog[key] = {
            "id": claim_ids[key], "short_id": short(claim_ids[key]),
            "issuer": issuer_for[key], "parents": body["parents"], "fact": body["fact"],
            "handoff_receiver": route["receiver"] if route else None,
            "receipt": route["receipt"] if route else None,
            "authority_status": "CONTRADICTED" if key == "root_A" else "CONFIRMED",
        }

    replay = {
        "schema": "mast-demo-replay-v1",
        "fixture_id": FIXTURE_ID,
        "fixture_hash": fixture["canonical_hash"],
        "provenance": {
            "label": "Replay from final benchmark fixture",
            "plan": str(ARCHIVE / "plan.json"),
            "aggregate": str(ARCHIVE / "aggregate.json"),
            "task_metrics": str(ARCHIVE / "task_metrics.json"),
            "runs": {layer: {"workflow_id": rows[layer]["workflow_id"],
                              "path": rows[layer]["result_path"],
                              "sha256": rows[layer]["result_sha256"]}
                     for layer in ("L0", "L4")},
        },
        "business": {**fixture["business"], "effect": fixture["graph"]["business_effect"]},
        "topology": {"organizations": fixture["graph"]["organizations"],
                     "edges": fixture["graph"]["edges"], "tasks": fixture["graph"]["tasks"]},
        "truth": {**fixture["evaluation"], "claim_ids": claim_ids,
                  "affected_order": "A", "unrelated_order": "C"},
        "claims": claim_catalog,
        "comparison": {
            layer: {"workflow_id": rows[layer]["workflow_id"],
                    "metrics": {k: rows[layer][k] for k in (
                        "unsafe_completion_count", "safe_final_completion", "unrelated_completed",
                        "recovered_tasks", "post_fault_error_handoffs", "notifications",
                        "authority_confirmed", "budget_decisions")},
                    "tasks": [{k: task[k] for k in ("task_id", "affected", "status",
                                                     "unsafe_completion", "recovered", "safe_final")}
                              for task in per_task[layer]],
                    "routes": routes[layer], "event_counts": event_counts(runs[layer]["raw"])}
            for layer in ("L0", "L4")
        },
        "repair": {
            "status": revision["status"], "old_root": new_root["body"]["supersedes"],
            "new_root": digest(new_root),
            "new_root_short": short(digest(new_root)),
            "issuer": new_root["signature"]["issuer"],
            "old_cents": fixture["business"]["base_cents"],
            "new_cents": new_root["body"]["fact"]["value"]["cents"],
            "authority": "buyer", "authority_status": "CONFIRMED",
            "rebuilds": compact_rebuilds,
            "recoveries": [{"task_id": r["task_id"], "status": r["status"],
                            "final_action": r["final_action"]["action"],
                            "authority_confirmation": r["authority_confirmation"]}
                           for r in l4["recoveries"]],
        },
        # Five presentation beats compress several runtime events without
        # changing their provenance or ordering.
        "stages": [
            {"id":"normal","label":"正常传播","duration_ms":3500},
            {"id":"fault","label":"发现错误","duration_ms":3500},
            {"id":"contain","label":"局部阻断","duration_ms":5000},
            {"id":"repair","label":"修订与重建","duration_ms":4500},
            {"id":"recheck","label":"重新检查","duration_ms":3500},
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"exported {FIXTURE_ID} -> {args.output}")


if __name__ == "__main__":
    main()
