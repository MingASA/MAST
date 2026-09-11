#!/usr/bin/env python3
"""Run the supplementary layered MiniMax pilot on the two unseen topologies.

The original bounded pilot covers long_chain_fork.  This runner keeps that
archive immutable and adds the same three live cases and five layers for the
two remaining benchmark topologies.  It is intentionally a small experiment
orchestrator rather than a change to the benchmark mechanism.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from trust_network.benchmark.layered.engine import Run  # noqa: E402
from trust_network.benchmark.layered.preflight import (  # noqa: E402
    source_hashes,
    verify_offline,
    verify_validation,
)
from trust_network.benchmark.layered.report import report  # noqa: E402
from trust_network.benchmark.layered.spec import LIVE_CASES, MAIN  # noqa: E402
from trust_network.benchmark.layered.storage import write_json  # noqa: E402


TOPOLOGIES = ("converge_then_fork", "reused_org_independent")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def all_root_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: sha256_file(path)
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name not in {"manifest.json", "partial_manifest.json"}
    }


def write_root_json(directory: Path, hashes: dict[str, str], name: str, value: Any) -> None:
    path = directory / name
    write_json(path, value)
    hashes[name] = sha256_file(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    args = parser.parse_args()

    if not args.allow_paid:
        parser.error("supplementary live runs require --allow-paid")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    if not args.env_file.exists():
        parser.error(f"env file does not exist: {args.env_file}")

    verify_offline(args.preflight.parent)
    verify_validation(args.validation)

    combos = [(topology, case, layer) for topology in TOPOLOGIES for case in LIVE_CASES for layer in MAIN]
    args.output.mkdir(parents=True, exist_ok=False)
    workers = args.output / "workers"
    workers.mkdir(mode=0o700)
    hashes: dict[str, str] = {}
    sources = source_hashes()
    write_root_json(
        args.output,
        hashes,
        "provenance.json",
        {
            "source_hashes": sources,
            "mode": "live",
            "initialization": "scripted",
            "effects": "simulated",
            "query_latency_ticks": 0,
            "topologies": list(TOPOLOGIES),
            "cases": list(LIVE_CASES),
            "layers": list(MAIN),
            "workflow_count": len(combos),
            "supplement_to": "results/layered_v1_live_pilot_01",
            "automatic_paid_retry": False,
        },
    )
    write_root_json(
        args.output,
        hashes,
        "progress.json",
        {"status": "initialized", "planned": len(combos), "completed": 0, "mode": "live"},
    )

    rows: list[dict[str, Any]] = []
    for index, (topology, case, layer) in enumerate(combos):
        if source_hashes() != sources:
            raise RuntimeError("source changed before workflow; do not continue")
        write_root_json(
            args.output,
            hashes,
            "progress.json",
            {
                "status": "running",
                "index": index,
                "completed": len(rows),
                "planned": len(combos),
                "topology": topology,
                "case": case,
                "layer": layer,
                "mode": "live",
            },
        )
        started = time.time()
        worker_directory = workers / str(index)
        try:
            raw = Run(
                topology,
                case,
                layer,
                backend="process",
                directory=worker_directory,
                live=True,
                env_file=args.env_file,
            ).run()
        except BaseException as exc:
            write_root_json(
                args.output,
                hashes,
                "progress.json",
                {
                    "status": "interrupted",
                    "index": index,
                    "completed": len(rows),
                    "planned": len(combos),
                    "mode": "live",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "automatic_paid_retry": False,
                    "journal": str(worker_directory),
                },
            )
            write_json(args.output / "partial_manifest.json", hashes)
            raise

        if source_hashes() != sources:
            raise RuntimeError("source changed after workflow; archive worker journal before resuming")
        metrics = raw["metrics"]
        if raw["new_model_calls"] > 28 or raw["provider_attempts"] > 56:
            raise RuntimeError(
                f"workflow exceeded live budget: calls={raw['new_model_calls']} attempts={raw['provider_attempts']}"
            )
        name = f"{index:03d}_{topology}_{case}_{layer}.json"
        write_root_json(args.output, hashes, name, raw)
        rows.append(
            {
                "file": name,
                "topology": topology,
                "case": case,
                "layer": layer,
                "workload_hash": raw["workload_hash"],
                "event_tape_hash": raw["event_tape_hash"],
                "proposal_tape_hash": raw["proposal_tape_hash"],
                "metrics": metrics,
            }
        )
        write_root_json(args.output, hashes, "metrics.json", rows)
        write_root_json(
            args.output,
            hashes,
            "progress.json",
            {
                "status": "between_workflows",
                "completed": len(rows),
                "planned": len(combos),
                "mode": "live",
                "last_topology": topology,
                "last_case": case,
                "last_layer": layer,
                "last_duration_seconds": round(time.time() - started, 3),
            },
        )
        print(
            json.dumps(
                {
                    "completed": len(rows),
                    "planned": len(combos),
                    "topology": topology,
                    "case": case,
                    "layer": layer,
                    "unsafe": metrics["unsafe_completion_count"],
                    "safe_final": metrics["safe_final_completion"],
                    "calls": raw["new_model_calls"],
                    "tokens": metrics["known_tokens"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    write_root_json(
        args.output,
        hashes,
        "progress.json",
        {"status": "completed", "completed": len(rows), "planned": len(combos), "mode": "live"},
    )
    report(args.output, "live")
    write_json(args.output / "manifest.json", all_root_hashes(args.output))
    print(json.dumps({"status": "completed", "completed": len(rows), "planned": len(combos)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
