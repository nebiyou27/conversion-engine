"""Synthetic end-to-end prospect run orchestration."""
from __future__ import annotations

import json
import os
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from typing import Any

from agent.actions.email_draft import build_commitment_email
from agent.actions.schedule import schedule_discovery_call
from agent.evidence import collector, enrichment
from agent.gate.citation_check import check as citation_check
from agent.gate.forbidden_phrases import check as forbidden_check
from agent.gate.shadow_review import check as shadow_check
from agent.handlers import email as email_handler
from agent.judgment import ai_maturity
from agent.judgment import competitor_gap, icp, segment
from integrations.llm import BudgetLedger
from integrations.calcom_client import BookingResult
from storage import db

DEFAULT_FIXTURE = Path("data/fixtures/companies/acme_series_b.json")
DEFAULT_OUTPUT_DIR = Path("outputs") / "runs"
LIVE_INTEGRATION_ENV_VARS = ("RESEND_API_KEY", "HUBSPOT_TOKEN", "CALCOM_API_KEY", "CALCOM_BOOKING_URL")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_slug() -> str:
    return _now().strftime("%Y%m%d-%H%M%S")


def _is_demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "false").lower() == "true"


def _live_integrations_configured() -> bool:
    return all(os.getenv(name) for name in LIVE_INTEGRATION_ENV_VARS)


def _safe_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


@dataclass(frozen=True)
class ThreadResult:
    run_dir: str
    company_id: str
    company_name: str
    segment_match: str
    segment_confidence: float
    ai_maturity_score: int
    email_message_id: str
    booking_id: str
    booking_url: str
    gate_report: dict[str, Any]


def _fake_email_send(to: str, subject: str, html: str) -> str:
    return f"demo-email-{uuid.uuid4()}"


def _fake_book_discovery_call(**kwargs):
    return BookingResult(
        booking_id=f"demo-booking-{uuid.uuid4()}",
        booking_url="https://cal.com/demo/discovery-call",
        scheduled_start="2026-04-24T10:00:00+00:00",
        scheduled_end="2026-04-24T10:30:00+00:00",
        raw={
            "contact_id": kwargs.get("hubspot_contact_id") or f"demo-contact-{uuid.uuid4()}",
            "mode": "demo",
        },
    )


def _fake_hubspot_upsert_contact(email: str, **kwargs) -> str:
    return f"demo-contact-{uuid.uuid4()}"


def _fake_hubspot_record_booking(contact_id: str, **kwargs) -> str:
    return contact_id


def _build_demo_ai_maturity_response() -> dict[str, Any]:
    return {
        "score": 2,
        "confidence": 0.74,
        "justifications": [
            {"signal": "ai_adjacent_open_roles", "status": "2 ML roles open", "weight": "high", "confidence": "high", "source_url": "https://example.com/jobs"},
            {"signal": "named_ai_ml_leadership", "status": "absent", "weight": "low", "confidence": "low", "source_url": None},
            {"signal": "github_org_activity", "status": "unknown", "weight": "low", "confidence": "low", "source_url": None},
            {"signal": "executive_commentary", "status": "absent", "weight": "low", "confidence": "low", "source_url": None},
            {"signal": "modern_data_ml_stack", "status": "MLflow in job posts", "weight": "medium", "confidence": "medium", "source_url": "https://example.com/jobs/2"},
            {"signal": "strategic_communications", "status": "absent", "weight": "low", "confidence": "low", "source_url": None},
        ],
    }


def run_synthetic_thread(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    output_root: Path | str = DEFAULT_OUTPUT_DIR,
    live: bool = False,
) -> ThreadResult:
    """Run one complete synthetic prospect thread and persist artifacts."""
    demo_mode = _is_demo_mode()
    use_live_integrations = live and _live_integrations_configured()

    fixture_path = Path(fixture_path)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / _now_slug()
    run_dir.mkdir(parents=True, exist_ok=False)

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    company_id = fixture["company_id"]
    company_name = fixture.get("name", company_id)

    conn = db.connect(run_dir / "run.db")
    db.init(conn)
    run_id = run_dir.name
    ledger = BudgetLedger(run_id=run_id)

    evidence_ids = collector.collect(fixture, conn)
    if evidence_ids:
        __import__("agent.claims.builder", fromlist=["build"]).build(conn, company_id, now=_now())

    rows = [dict(r) for r in conn.execute("SELECT * FROM claims WHERE company_id = ?", (company_id,)).fetchall()]

    if demo_mode:
        ai_result = _build_demo_ai_maturity_response()
    else:
        ai_result = ai_maturity.judge(conn, company_id, run_id=run_id, ledger=ledger)

    segment_result = segment.classify(rows, now=_now(), ai_maturity_score=ai_result["score"])
    icp_result = icp.judge(conn, company_id, now=_now(), ai_maturity_score=ai_result["score"])
    gap_result = competitor_gap.judge(
        conn,
        company_id,
        prospect_domain="acme.example",
        prospect_sector="saas",
        ai_maturity_score=ai_result["score"],
        ai_maturity_justifications=ai_result["justifications"],
    )
    enrichment_artifact = enrichment.build_enrichment_artifact(conn, company_id, company_name=company_name)

    draft = build_commitment_email(
        company_name=company_name,
        prospect_name="Prospect",
        claim_rows=rows,
        segment_match=segment_result["primary_segment_match"],
    )

    citation_result = citation_check(draft["body"], draft["claim_ids"])
    shadow_result = shadow_check(draft["body"], draft["claim_ids"])
    forbidden_result = forbidden_check(draft["body"])
    gate_ok = citation_result["ok"] and shadow_result["ok"] and forbidden_result["ok"]
    decision = "pass" if gate_ok else "human_queue"

    draft_id = db.insert_draft(
        conn,
        company_id=company_id,
        channel="email",
        path="commitment",
        subject=draft["subject"],
        body=draft["body"],
        claim_ids=draft["claim_ids"],
    )
    report_id = db.insert_gate_report(
        conn,
        draft_id=draft_id,
        citation_ok=citation_result["ok"],
        shadow_ok=shadow_result["ok"],
        forbidden_ok=forbidden_result["ok"],
        decision=decision,
        failures=[
            {"kind": "citation", "failures": citation_result["failures"]},
            {"kind": "shadow", "failures": shadow_result["failures"]},
            {"kind": "forbidden", "matches": forbidden_result["matches"]},
        ],
    )

    if use_live_integrations:
        email_message_id = email_handler.send_outbound_email("prospect@example.com", draft["subject"], draft["body"])
    else:
        email_message_id = _fake_email_send("prospect@example.com", draft["subject"], draft["body"])

    email_reply_event = email_handler.handle_webhook_payload(
        {
            "event": "inbound.reply",
            "message_id": email_message_id,
            "from": "prospect@example.com",
            "to": "sales@tenacious.co",
            "subject": f"Re: {draft['subject']}",
            "text": "Thanks, let's book a call.",
        }
    )

    with ExitStack() as stack:
        if not use_live_integrations:
            stack.enter_context(patch("integrations.hubspot_client.upsert_contact", _fake_hubspot_upsert_contact))
            stack.enter_context(patch("integrations.hubspot_client.record_booking", _fake_hubspot_record_booking))
            stack.enter_context(patch("integrations.calcom_client.book_discovery_call", _fake_book_discovery_call))

        booking_result = schedule_discovery_call(
            email="prospect@example.com",
            company_name=company_name,
            name="Prospect",
            icp_segment=segment_result["primary_segment_match"],
            signal_enrichment=enrichment_artifact["per_signal_confidence"],
            hubspot_contact_id=None,
        )

    run_summary = {
        "demo_mode": not use_live_integrations,
        "demo_mode_env": demo_mode,
        "live_requested": live,
        "live_integrations_used": use_live_integrations,
        "company_id": company_id,
        "company_name": company_name,
        "evidence_ids": evidence_ids,
        "claim_ids": rows and [r["claim_id"] for r in rows] or [],
        "segment": segment_result,
        "icp": icp_result,
        "ai_maturity": {
            **ai_result,
            **(
                {
                    "source": "hardcoded_demo_stub",
                    "limitation": "Synthetic thread uses a fixed AI maturity response when DEMO_MODE=true; agent.judgment.ai_maturity.judge is tested separately.",
                }
                if demo_mode
                else {"source": "llm_qwen"}
            ),
        },
        "competitor_gap": gap_result,
        "enrichment": enrichment_artifact,
        "draft": draft,
        "email_reply_event": email_reply_event,
        "booking": booking_result,
        "gate_report": {
            "report_id": report_id,
            "decision": decision,
            "citation_ok": citation_result["ok"],
            "shadow_ok": shadow_result["ok"],
            "forbidden_ok": forbidden_result["ok"],
        },
    }

    (run_dir / "evidence.jsonl").write_text(
        "\n".join(_safe_json(dict(r)) for r in conn.execute("SELECT * FROM evidence WHERE company_id = ?", (company_id,)).fetchall()) + "\n",
        encoding="utf-8",
    )
    (run_dir / "claims.jsonl").write_text(
        "\n".join(_safe_json(dict(r)) for r in conn.execute("SELECT * FROM claims WHERE company_id = ?", (company_id,)).fetchall()) + "\n",
        encoding="utf-8",
    )
    (run_dir / "draft.md").write_text(f"# {draft['subject']}\n\n{draft['body']}\n", encoding="utf-8")
    (run_dir / "gate_report.json").write_text(_safe_json(run_summary["gate_report"]), encoding="utf-8")
    (run_dir / "run.json").write_text(_safe_json(run_summary), encoding="utf-8")
    (run_dir / "invoice_summary.json").write_text(_safe_json(ledger.get_summary()), encoding="utf-8")
    conn.close()

    return ThreadResult(
        run_dir=str(run_dir),
        company_id=company_id,
        company_name=company_name,
        segment_match=segment_result["primary_segment_match"],
        segment_confidence=segment_result["segment_confidence"],
        ai_maturity_score=ai_result["score"],
        email_message_id=email_message_id,
        booking_id=booking_result["booking_id"],
        booking_url=booking_result["booking_url"],
        gate_report=run_summary["gate_report"],
    )
