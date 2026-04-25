"""Compute Delta A for a tau2 treatment run.

Usage:
    python eval/compute_delta_a.py deliverables/held_out_traces.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Any


BASELINE_SUCCESSES = 109
BASELINE_TRIALS = 150
BASELINE_PASS_AT_1 = 0.7267
BASELINE_CI95 = [0.6504, 0.7917]
BASELINE_COST_PER_TASK_USD = 0.0199
BASELINE_P95_LATENCY_S = 551.6491
MODEL = "openrouter/qwen/qwen3-next-80b-a3b-thinking"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def wilson_ci(successes: int, trials: int, z: float = 1.959963984540054) -> list[float]:
    if trials == 0:
        return [0.0, 0.0]
    phat = successes / trials
    denom = 1 + z * z / trials
    center = (phat + z * z / (2 * trials)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * trials)) / trials) / denom
    return [max(0.0, center - margin), min(1.0, center + margin)]


def two_proportion_z(success_a: int, n_a: int, success_b: int, n_b: int) -> tuple[float, float]:
    if n_a == 0 or n_b == 0:
        return 0.0, 1.0
    pooled = (success_a + success_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    if se == 0:
        return 0.0, 1.0
    z_score = (success_a / n_a - success_b / n_b) / se
    p_value = math.erfc(abs(z_score) / math.sqrt(2))
    return z_score, p_value


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = math.ceil(pct / 100 * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    trials = len(records)
    successes = sum(1 for record in records if float(record.get("reward", 0.0)) >= 1.0)
    durations = [float(record["duration"]) for record in records if record.get("duration") is not None]
    costs = [float(record["agent_cost"]) for record in records if record.get("agent_cost") is not None]
    pass_at_1 = successes / trials if trials else 0.0
    ci95 = wilson_ci(successes, trials)
    baseline_low, baseline_high = BASELINE_CI95
    ci_separation = ci95[0] > baseline_high or ci95[1] < baseline_low
    z_score, p_value = two_proportion_z(successes, trials, BASELINE_SUCCESSES, BASELINE_TRIALS)

    return {
        "successes": successes,
        "trials": trials,
        "pass_at_1": pass_at_1,
        "ci95": ci95,
        "avg_agent_cost": (sum(costs) / len(costs)) if costs else None,
        "p50_latency_s": median(durations) if durations else None,
        "p95_latency_s": percentile(durations, 95),
        "delta": pass_at_1 - BASELINE_PASS_AT_1,
        "z_score": z_score,
        "p_value": p_value,
        "significant": p_value < 0.05,
        "ci_separation": ci_separation,
    }


def write_artifacts(summary: dict[str, Any], ablation_path: Path, test_path: Path) -> None:
    ablation = {
        "method": {
            "pass_at_1": summary["pass_at_1"],
            "ci95": summary["ci95"],
            "cost_per_task_usd": summary["avg_agent_cost"],
            "p95_latency_s": summary["p95_latency_s"],
            "tasks": summary["trials"],
            "trials_per_task": 1,
            "model": MODEL,
        },
        "day1_baseline": {
            "pass_at_1": BASELINE_PASS_AT_1,
            "ci95": BASELINE_CI95,
            "cost_per_task_usd": BASELINE_COST_PER_TASK_USD,
            "p95_latency_s": BASELINE_P95_LATENCY_S,
            "tasks": 30,
            "trials_per_task": 5,
            "source": "deliverables/baseline.md",
        },
        "automated_optimization_baseline": None,
        "delta_A": {
            "value": summary["delta"],
            "sign": "positive" if summary["delta"] > 0 else "negative" if summary["delta"] < 0 else "flat",
            "ci_separation": summary["ci_separation"],
            "two_proportion_z_p_value": summary["p_value"],
        },
        "notes": [
            "Delta B (vs GEPA/AutoAgent) skipped per Abdulhamid 2026-04-24 scope reduction.",
            "Sealed held-out 20-task partition not delivered; evaluation on 30-task dev slice.",
            "One-trial sample width makes CI separation unlikely below near-perfect pass rates.",
        ],
    }
    test = {
        "p_value": summary["p_value"],
        "z_score": summary["z_score"],
        "significant": summary["significant"],
        "ci_separation": summary["ci_separation"],
    }
    ablation_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    ablation_path.write_text(json.dumps(ablation, indent=2) + "\n", encoding="utf-8")
    test_path.write_text(json.dumps(test, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_jsonl", type=Path)
    parser.add_argument("--ablation-out", type=Path, default=Path("deliverables/ablation_results.json"))
    parser.add_argument("--test-out", type=Path, default=Path("eval/delta_a_test.json"))
    args = parser.parse_args()

    records = read_jsonl(args.trace_jsonl)
    summary = summarize(records)
    write_artifacts(summary, args.ablation_out, args.test_out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
