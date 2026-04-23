"""Contract tests for CRM and calendar integration."""
from __future__ import annotations

from dataclasses import dataclass

from agent.actions.schedule import schedule_discovery_call
from integrations import calcom_client, hubspot_client


def test_build_contact_properties_includes_enrichment_fields():
    props = hubspot_client.build_contact_properties(
        "prospect@example.com",
        icp_segment="segment_3_leadership_transition",
        signal_enrichment={"job_posts": 4, "layoffs": 1},
        enrichment_timestamp="2026-04-22T12:00:00+00:00",
        company_name="Acme",
        booking_status="booking_requested",
    )

    assert props["email"] == "prospect@example.com"
    assert props["icp_segment"] == "segment_3_leadership_transition"
    assert props["enrichment_timestamp"] == "2026-04-22T12:00:00+00:00"
    assert props["company"] == "Acme"
    assert props["calcom_booking_status"] == "booking_requested"
    assert "signal_enrichment" in props


@dataclass
class _FakeBookingResponse:
    booking_id: str = "bk_123"
    booking_url: str = "https://cal.com/booking/bk_123"
    scheduled_start: str | None = "2026-04-24T10:00:00+00:00"
    scheduled_end: str | None = "2026-04-24T10:30:00+00:00"


def test_schedule_discovery_call_updates_hubspot_after_booking(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_upsert_contact(email: str, **kwargs):
        calls.append(("upsert", {"email": email, **kwargs}))
        return "contact_123"

    def fake_record_booking(contact_id: str, **kwargs):
        calls.append(("record", {"contact_id": contact_id, **kwargs}))
        return contact_id

    def fake_book_discovery_call(**kwargs):
        calls.append(("book", kwargs))
        return _FakeBookingResponse()

    monkeypatch.setattr(hubspot_client, "upsert_contact", fake_upsert_contact)
    monkeypatch.setattr(hubspot_client, "record_booking", fake_record_booking)
    monkeypatch.setattr(calcom_client, "book_discovery_call", fake_book_discovery_call)

    result = schedule_discovery_call(
        email="prospect@example.com",
        company_name="Acme",
        name="Prospect",
        icp_segment="segment_1_series_a_b",
        signal_enrichment={"job_posts": 3},
        booking_endpoint="https://cal.example.test/book",
    )

    assert result["contact_id"] == "contact_123"
    assert result["booking_id"] == "bk_123"
    assert result["hubspot_updated"] is True
    assert [kind for kind, _ in calls] == ["upsert", "book", "record"]
    assert calls[2][1]["booking_id"] == "bk_123"
    assert calls[2][1]["booking_url"] == "https://cal.com/booking/bk_123"
