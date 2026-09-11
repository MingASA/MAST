#!/usr/bin/env python3
"""Run a small, durable live probe for the layered L4 recovery path.

This is deliberately separate from the 15-row main pilot.  It does not alter
the workload or prompts; it only checks whether the real model reaches the
already implemented recovery entry after L4 blocks the faulty proposal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from trust_network.benchmark.layered.engine import Run  # noqa: E402
from trust_network.benchmark.layered.preflight import source_hashes  # noqa: E402
from trust_network.benchmark.layered.storage import write_json  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_artifacts(directory: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "artifact_manifest.json":
            artifacts[str(path.relative_to(directory))] = sha256_file(path)
    return artifacts


def write_progress(path: Path, **values: Any) -> None:
    payload = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    payload.update(values)
    write_json(path, payload)


def run_probe(probe_dir: Path, env_file: Path, index: int) -> dict[str, Any]:
    probe_dir.mkdir(mode=0o700)
    progress_path = probe_dir / "progress.json"
    write_progress(
        progress_path,
        status="running",
        probe=index,
        topology="long_chain_fork",
        case="confirmed_repair",
        layer="L4",
    )

    before = source_hashes()
    started = time.time()
    try:
        raw = Run(
            "long_chain_fork",
            "confirmed_repair",
            "L4",
            backend="process",
            directory=probe_dir / "workers",
            live=True,
            env_file=env_file,
        ).run()
        after = source_hashes()
        if before != after:
            raise RuntimeError("layered benchmark source changed during live probe")

        write_json(probe_dir / "raw.json", raw)
        write_json(probe_dir / "metrics.json", raw.get("metrics", {}))
        write_json(
            probe_dir / "provenance.json",
            {
                "probe": index,
                "topology": "long_chain_fork",
                "case": "confirmed_repair",
                "layer": "L4",
                "mode": "live",
                "env_file": str(env_file),
                "source_hashes": before,
                "source_hashes_after": after,
                "started_at_epoch": started,
                "finished_at_epoch": time.time(),
                "purpose": "supplementary recovery-entry probe; excluded from the 15-row main pilot",
            },
        )
        metrics = raw.get("metrics", {})
        write_progress(
            progress_path,
            status="completed",
            probe=index,
            recovered_tasks=metrics.get("recovered_tasks", 0),
            unsafe_completion_count=metrics.get("unsafe_completion_count", 0),
            error_action_blocks=metrics.get("error_action_blocks", 0),
            model_holds=metrics.get("model_holds", 0),
            new_model_calls=metrics.get("new_model_calls", 0),
            duration_seconds=round(time.time() - started, 3),
        )
        write_json(probe_dir / "artifact_manifest.json", list_artifacts(probe_dir))
        return metrics
    except BaseException as exc:
        write_progress(
            progress_path,
            status="interrupted_or_failed",
            probe=index,
            error_type=type(exc).__name__,
            error=str(exc),
            duration_seconds=round(time.time() - started, 3),
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--max-probes", type=int, default=3)
    args = parser.parse_args()

    if args.max_probes < 1:
        parser.error("--max-probes must be positive")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    if not args.env_file.exists():
        parser.error(f"env file does not exist: {args.env_file}")

    args.output.mkdir(mode=0o700)
    write_json(
        args.output / "provenance.json",
        {
            "mode": "live",
            "topology": "long_chain_fork",
            "case": "confirmed_repair",
            "layer": "L4",
            "max_probes": args.max_probes,
            "source_hashes": source_hashes(),
            "purpose": "supplementary recovery-entry probe; excluded from the 15-row main pilot",
        },
    )
    write_progress(args.output / "progress.json", status="started", planned=args.max_probes)

    completed = 0
    stop_reason = "probe_limit_reached_without_recovery"
    summaries: list[dict[str, Any]] = []
    for index in range(args.max_probes):
        metrics = run_probe(args.output / f"probe_{index:02d}", args.env_file, index)
        completed += 1
        summary = {
            "probe": index,
            "recovered_tasks": metrics.get("recovered_tasks", 0),
            "unsafe_completion_count": metrics.get("unsafe_completion_count", 0),
            "error_action_blocks": metrics.get("error_action_blocks", 0),
            "model_holds": metrics.get("model_holds", 0),
            "new_model_calls": metrics.get("new_model_calls", 0),
        }
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if metrics.get("recovered_tasks", 0) > 0:
            stop_reason = "recovery_observed"
            break

    write_json(
        args.output / "summary.json",
        {
            "status": "completed",
            "planned_max_probes": args.max_probes,
            "completed_probes": completed,
            "stop_reason": stop_reason,
            "summaries": summaries,
        },
    )
    write_progress(
        args.output / "progress.json",
        status="completed",
        planned=args.max_probes,
        completed=completed,
        stop_reason=stop_reason,
    )
    write_json(args.output / "artifact_manifest.json", list_artifacts(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
