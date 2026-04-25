"""Conversation router and bench guard tests."""
from __future__ import annotations

import pytest

from agent import router
from agent.actions.email_draft import (
    BenchCommitmentError,
    bench_summary_citation_present,
    draft_references_availability,
    enforce_bench_to_brief_guard,
)
from agent.handlers import email as email_handler
from agent.handlers import sms as sms_handler
from integrations import calcom_client


def test_reply_handoff_moves_to_scheduling_with_booking_link(monkeypatch):
    monkeypatch.setenv("CALCOM_BOOKING_URL", "https://cal.com/team/discovery")

    decision = router.handoff(
        router.ConversationState.SENT,
        "reply",
        source_channel="email",
        email="prospect@example.com",
        company="Acme",
    )

    assert decision.previous_state == router.ConversationState.SENT
    assert decision.next_state == router.ConversationState.SCHEDULING
    assert decision.channel == "email"
    assert decision.booking_link is not None
    assert decision.booking_link.startswith("https://cal.com/team/discovery?")
    assert "source=email" in decision.booking_link


def test_email_and_sms_reply_handlers_attach_scheduling_links(monkeypatch):
    monkeypatch.setattr(
        calcom_client,
        "generate_booking_link",
        lambda **kwargs: f"https://cal.example/book?source={kwargs['source_channel']}",
    )

    email_result = email_handler.handle_webhook_payload({
        "event": "inbound.reply",
        "message_id": "router_email_reply",
        "from": "prospect@example.com",
        "to": "sales@tenacious.co",
        "text": "Let's talk.",
    })
    sms_result = sms_handler.handle_webhook_payload({
        "event": "inbound.reply",
        "message_id": "router_sms_reply",
        "from": "+254700000000",
        "to": "+254711111111",
        "text": "Let's talk.",
        "email": "prospect@example.com",
    })

    assert email_result["routing"]["next_state"] == "scheduling"
    assert email_result["routing"]["booking_link"] == "https://cal.example/book?source=email"
    assert sms_result["routing"]["next_state"] == "scheduling"
    assert sms_result["routing"]["booking_link"] == "https://cal.example/book?source=sms"


def test_bench_to_brief_guard_raises_on_unsupported_availability_claim():
    draft = {
        "body": "We have three engineers available in 7 days for your platform work.",
    }

    assert draft_references_availability(draft) is True
    assert bench_summary_citation_present(draft) is False
    with pytest.raises(BenchCommitmentError, match="bench_summary"):
        enforce_bench_to_brief_guard(draft)


def test_bench_to_brief_guard_accepts_supported_availability_claim():
    draft = {
        "body": "We have three engineers available in 7 days for your platform work.",
        "bench_summary_id": "bench_2026_04_23",
    }

    enforce_bench_to_brief_guard(draft)
