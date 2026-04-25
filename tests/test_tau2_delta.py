from __future__ import annotations

import json

from eval.compute_delta_a import summarize, wilson_ci
from eval.convert_tau2_results import TRACE_KEYS, convert


def test_wilson_ci_matches_expected_shape():
    low, high = wilson_ci(24, 30)

    assert 0.62 < low < 0.63
    assert 0.90 < high < 0.91


def test_summarize_computes_delta_and_z_test():
    records = [{"reward": 1.0, "duration": 10, "agent_cost": 0.01} for _ in range(24)]
    records.extend({"reward": 0.0, "duration": 20, "agent_cost": 0.02} for _ in range(6))

    summary = summarize(records)

    assert summary["successes"] == 24
    assert summary["trials"] == 30
    assert round(summary["pass_at_1"], 4) == 0.8
    assert summary["delta"] > 0
    assert 0 <= summary["p_value"] <= 1


def test_convert_tau2_results_extracts_trace_records(tmp_path):
    source = tmp_path / "tau2_results.json"
    output = tmp_path / "held_out_traces.jsonl"
    source.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "agent_cost": 0.1,
                        "domain": "retail",
                        "duration": 12,
                        "reward": 1.0,
                        "simulation_id": "sim-1",
                        "task_id": "1",
                        "termination_reason": "user_stop",
                        "extra": "ignored",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    count = convert(source, output)
    record = json.loads(output.read_text(encoding="utf-8"))

    assert count == 1
    assert tuple(record) == TRACE_KEYS
    assert "extra" not in record
