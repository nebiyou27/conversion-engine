"""End-to-end synthetic thread smoke test."""
from __future__ import annotations

import json
from pathlib import Path

from agent.core import run_synthetic_thread


def test_run_synthetic_thread_produces_complete_artifacts(tmp_path):
    result = run_synthetic_thread(
        fixture_path=Path("data/fixtures/companies/acme_series_b.json"),
        output_root=tmp_path / "runs",
        live=False,
    )

    run_dir = Path(result.run_dir)
    assert run_dir.exists()
    assert (run_dir / "run.json").exists()
    assert (run_dir / "draft.md").exists()
    assert (run_dir / "gate_report.json").exists()

    run_data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["demo_mode"] is True
    assert run_data["ai_maturity"]["source"] == "hardcoded_demo_stub"
    assert run_data["gate_report"]["decision"] == "pass"
    assert run_data["booking"]["booking_url"]
    assert run_data["email_reply_event"]["ok"] is True
    assert run_data["segment"]["primary_segment_match"] != "abstain"
    assert result.booking_id
