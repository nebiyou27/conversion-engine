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


def test_schedule_discovery_call_skips_duplicate_booking_update(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_upsert_contact(email: str, **kwargs):
        calls.append(("upsert", {"email": email, **kwargs}))
        return "contact_123"

    def fake_record_booking(contact_id: str, **kwargs):
        calls.append(("record", {"contact_id": contact_id, **kwargs}))
        return contact_id

    def fake_book_discovery_call(**kwargs):
        calls.append(("book", kwargs))
        return _FakeBookingResponse(
            booking_id="bk_replay_123",
            booking_url="https://cal.com/booking/bk_replay_123",
        )

    monkeypatch.setattr(hubspot_client, "upsert_contact", fake_upsert_contact)
    monkeypatch.setattr(hubspot_client, "record_booking", fake_record_booking)
    monkeypatch.setattr(calcom_client, "book_discovery_call", fake_book_discovery_call)

    first = schedule_discovery_call(
        email="prospect@example.com",
        company_name="Acme",
        name="Prospect",
        icp_segment="segment_1_series_a_b",
        signal_enrichment={"job_posts": 3},
        booking_endpoint="https://cal.example.test/book",
    )
    second = schedule_discovery_call(
        email="prospect@example.com",
        company_name="Acme",
        name="Prospect",
        icp_segment="segment_1_series_a_b",
        signal_enrichment={"job_posts": 3},
        booking_endpoint="https://cal.example.test/book",
    )

    assert first["hubspot_updated"] is True
    assert second["hubspot_updated"] is False
    assert [kind for kind, _ in calls].count("record") == 1


def test_hubspot_client_routes_to_mcp_when_enabled(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    class FakeMCPClient:
        def upsert_contact(self, *, email: str, properties: dict):
            calls.append(("upsert", (), {"email": email, "properties": properties}))
            return "mcp_contact_123"

        def update_contact(self, contact_id: str, *, email: str, properties: dict):
            calls.append(("update", (contact_id,), {"email": email, "properties": properties}))
            return contact_id

    monkeypatch.setenv("USE_HUBSPOT_MCP", "true")
    monkeypatch.setattr(hubspot_client, "_get_mcp_client", lambda: FakeMCPClient())
    monkeypatch.setattr(hubspot_client, "_get_client", lambda: (_ for _ in ()).throw(AssertionError("SDK path should not be used")))

    contact_id = hubspot_client.upsert_contact(
        "prospect@example.com",
        icp_segment="segment_1_series_a_b",
        signal_enrichment={"job_posts": 3},
        company_name="Acme",
    )

    assert contact_id == "mcp_contact_123"
    assert calls[0][0] == "upsert"
    assert calls[0][2]["email"] == "prospect@example.com"
    assert calls[0][2]["properties"]["company"] == "Acme"


def test_hubspot_client_routes_booking_updates_to_mcp_when_enabled(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    class FakeMCPClient:
        def upsert_contact(self, *, email: str, properties: dict):
            calls.append(("upsert", (), {"email": email, "properties": properties}))
            return "mcp_contact_123"

        def update_contact(self, contact_id: str, *, email: str, properties: dict):
            calls.append(("update", (contact_id,), {"email": email, "properties": properties}))
            return contact_id

    monkeypatch.setenv("USE_HUBSPOT_MCP", "true")
    monkeypatch.setattr(hubspot_client, "_get_mcp_client", lambda: FakeMCPClient())
    monkeypatch.setattr(hubspot_client, "_get_client", lambda: (_ for _ in ()).throw(AssertionError("SDK path should not be used")))

    result = hubspot_client.record_booking(
        "contact_123",
        email="prospect@example.com",
        booking_id="bk_123",
        booking_url="https://cal.com/booking/bk_123",
        icp_segment="segment_1_series_a_b",
        signal_enrichment={"job_posts": 3},
        company_name="Acme",
    )

    assert result == "contact_123"
    assert calls[0][0] == "update"
    assert calls[0][1] == ("contact_123",)
    assert calls[0][2]["properties"]["calcom_booking_status"] == "booked"
