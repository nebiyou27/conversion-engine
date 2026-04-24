"""Measure stalled-thread rate from latency run artifacts.

Definition: a thread is stalled when no outbound action happens within 300
seconds of inbound reply normalization. The latency runner records full thread
elapsed time per synthetic iteration, so this report uses total_seconds as the
conservative proxy for reply-normalization-to-next-action completion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STALL_THRESHOLD_SECONDS = 300
DEFAULT_INPUT = Path("outputs/runs/latency-20260423-201603")
DEFAULT_OUTPUT = Path("eval/stall_rate_report.json")


def _load_runs(input_dir: Path) -> list[dict[str, Any]]:
    log_path = input_dir / "latency_log.jsonl"
    if log_path.exists():
        return [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    summary_path = input_dir / "latency_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Expected {log_path} or {summary_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return [
        {"run_index": i + 1, "total_seconds": summary["p95_total_seconds"]}
        for i in range(int(summary["count"]))
    ]


def build_report(
    input_dir: Path = DEFAULT_INPUT,
    *,
    stall_threshold_seconds: int = STALL_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    runs = _load_runs(input_dir)
    stalled = [
        run for run in runs
        if float(run.get("total_seconds", 0.0)) > stall_threshold_seconds
    ]
    denominator = len(runs)
    return {
        "definition": "stalled = no outbound action within 300s of inbound reply normalization",
        "input_dir": str(input_dir),
        "stall_threshold_seconds": stall_threshold_seconds,
        "n": denominator,
        "stalled_count": len(stalled),
        "stall_rate": (len(stalled) / denominator) if denominator else None,
        "stalled_run_indices": [run.get("run_index") for run in stalled],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute stalled-thread rate.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--threshold-seconds", type=int, default=STALL_THRESHOLD_SECONDS)
    args = parser.parse_args()

    report = build_report(Path(args.input_dir), stall_threshold_seconds=args.threshold_seconds)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
