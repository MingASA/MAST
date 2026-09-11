#!/usr/bin/env python3
"""Run a bounded multi-topology live confirmed-repair replication.

The standard layered live pilot includes controls for active and late notice
cases.  This runner isolates the repaired L4 path so the model's recovery
request, source revision, frontier rebuild, and final action can be inspected
without mixing those stages with unrelated live cases.  Every workflow keeps
its own ProcessBackend worker archive and the root directory is immutable.
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
from trust_network.benchmark.layered.storage import write_json  # noqa: E402


TOPOLOGIES = ("long_chain_fork", "converge_then_fork", "reused_org_independent")
CASE = "confirmed_repair"
LAYER = "L4"
MAX_MODEL_CALLS = 28
MAX_PROVIDER_ATTEMPTS = 56


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def root_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: sha256_file(path)
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name not in {"manifest.json", "partial_manifest.json"}
    }


def write_root(directory: Path, hashes: dict[str, str], name: str, value: Any) -> None:
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
    parser.add_argument("--repetitions", type=int, default=2)
    args = parser.parse_args()

    if not args.allow_paid:
        parser.error("live runs require --allow-paid")
    if args.repetitions < 1 or args.repetitions > 4:
        parser.error("repetitions must be between 1 and 4")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    if not args.env_file.exists():
        parser.error(f"env file does not exist: {args.env_file}")

    verify_offline(args.preflight.parent)
    verify_validation(args.validation)

    combos = [
        (topology, repetition)
        for repetition in range(args.repetitions)
        for topology in TOPOLOGIES
    ]
    args.output.mkdir(parents=True, exist_ok=False)
    workers = args.output / "workers"
    workers.mkdir(mode=0o700)
    hashes: dict[str, str] = {}
    sources = source_hashes()
    write_root(
        args.output,
        hashes,
        "provenance.json",
        {
            "source_hashes": sources,
            "mode": "live",
            "backend": "process",
            "initialization": "scripted",
            "effects": "simulated",
            "query_latency_ticks": 0,
            "topologies": list(TOPOLOGIES),
            "case": CASE,
            "layer": LAYER,
            "repetitions": args.repetitions,
            "workflow_count": len(combos),
            "purpose": "replicate repaired L4 confirmed_repair control-plane and recovery path",
            "automatic_paid_retry": False,
        },
    )
    write_root(
        args.output,
        hashes,
        "progress.json",
        {"status": "initialized", "planned": len(combos), "completed": 0, "mode": "live"},
    )

    rows: list[dict[str, Any]] = []
    for index, (topology, repetition) in enumerate(combos):
        if source_hashes() != sources:
            raise RuntimeError("source changed before workflow; do not continue")
        write_root(
            args.output,
            hashes,
            "progress.json",
            {
                "status": "running",
                "index": index,
                "completed": len(rows),
                "planned": len(combos),
                "topology": topology,
                "repetition": repetition,
                "mode": "live",
            },
        )
        started = time.time()
        worker_directory = workers / f"{index:03d}_{topology}_r{repetition}"
        try:
            raw = Run(
                topology,
                CASE,
                LAYER,
                backend="process",
                directory=worker_directory,
                live=True,
                env_file=args.env_file,
            ).run()
        except BaseException as exc:
            write_root(
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
        if raw["new_model_calls"] > MAX_MODEL_CALLS or raw["provider_attempts"] > MAX_PROVIDER_ATTEMPTS:
            raise RuntimeError(
                f"workflow exceeded live budget: calls={raw['new_model_calls']} attempts={raw['provider_attempts']}"
            )
        name = f"{index:03d}_{topology}_confirmed_repair_L4_r{repetition}.json"
        write_root(args.output, hashes, name, raw)
        rows.append(
            {
                "file": name,
                "topology": topology,
                "case": CASE,
                "layer": LAYER,
                "repetition": repetition,
                "workload_hash": raw["workload_hash"],
                "event_tape_hash": raw["event_tape_hash"],
                "proposal_tape_hash": raw["proposal_tape_hash"],
                "metrics": raw["metrics"],
            }
        )
        write_root(args.output, hashes, "metrics.json", rows)
        write_root(
            args.output,
            hashes,
            "progress.json",
            {
                "status": "between_workflows",
                "completed": len(rows),
                "planned": len(combos),
                "mode": "live",
                "last_topology": topology,
                "last_repetition": repetition,
                "last_duration_seconds": round(time.time() - started, 3),
            },
        )
        print(
            json.dumps(
                {
                    "completed": len(rows),
                    "planned": len(combos),
                    "topology": topology,
                    "repetition": repetition,
                    "unsafe": raw["metrics"]["unsafe_completion_count"],
                    "safe_final": raw["metrics"]["safe_final_completion"],
                    "recovered": raw["metrics"]["recovered_tasks"],
                    "calls": raw["new_model_calls"],
                    "tokens": raw["metrics"]["known_tokens"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    write_root(
        args.output,
        hashes,
        "progress.json",
        {"status": "completed", "completed": len(rows), "planned": len(combos), "mode": "live"},
    )
    report(args.output, "live")
    write_json(args.output / "manifest.json", root_hashes(args.output))
    print(json.dumps({"status": "completed", "completed": len(rows), "planned": len(combos)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
