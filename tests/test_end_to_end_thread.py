"""End-to-end synthetic thread smoke test."""
from __future__ import annotations

import json
from pathlib import Path

from agent.core import run_synthetic_thread


def test_run_synthetic_thread_produces_complete_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")

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
    assert (run_dir / "invoice_summary.json").exists()

    run_data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["demo_mode"] is True
    assert run_data["ai_maturity"]["source"] == "hardcoded_demo_stub"
    assert run_data["gate_report"]["decision"] == "pass"
    assert run_data["booking"]["booking_url"]
    assert run_data["email_reply_event"]["ok"] is True
    assert run_data["segment"]["primary_segment_match"] != "abstain"
    assert result.booking_id

    invoice = json.loads((run_dir / "invoice_summary.json").read_text(encoding="utf-8"))
    assert invoice["run_id"] == run_dir.name
    assert invoice["spent_usd"] == 0.0


def test_demo_mode_overrides_live_integrations(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("RESEND_API_KEY", "test-resend-key")
    monkeypatch.setenv("HUBSPOT_TOKEN", "test-hubspot-token")
    monkeypatch.setenv("CALCOM_API_KEY", "test-calcom-key")
    monkeypatch.setenv("CALCOM_BOOKING_URL", "https://cal.com/demo/discovery-call")

    def fail_live_email(**_: object) -> str:
        raise AssertionError("live email should not be used in DEMO_MODE")

    monkeypatch.setattr("agent.handlers.email.email_client.send", fail_live_email)

    result = run_synthetic_thread(
        fixture_path=Path("data/fixtures/companies/acme_series_b.json"),
        output_root=tmp_path / "runs",
        live=True,
    )

    run_dir = Path(result.run_dir)
    run_data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert result.email_message_id.startswith("demo-email-")
    assert run_data["demo_mode"] is True
    assert run_data["demo_mode_env"] is True
    assert run_data["live_requested"] is True
    assert run_data["live_integrations_used"] is False
    assert run_data["ai_maturity"]["source"] == "hardcoded_demo_stub"
