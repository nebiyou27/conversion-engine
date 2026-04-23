"""Scheduling action that bridges Cal.com and HubSpot."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from integrations import calcom_client, hubspot_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def schedule_discovery_call(
    *,
    email: str,
    company_name: str | None = None,
    name: str | None = None,
    icp_segment: str | None = None,
    signal_enrichment: dict[str, Any] | None = None,
    enrichment_timestamp: str | None = None,
    hubspot_contact_id: str | None = None,
    booking_endpoint: str | None = None,
    booking_session: Any | None = None,
) -> dict[str, Any]:
    """Book a discovery call and write the same prospect back to HubSpot."""
    enrichment_timestamp = enrichment_timestamp or _now()

    if hubspot_contact_id:
        contact_id = hubspot_client.record_booking(
            hubspot_contact_id,
            email=email,
            booking_id="pending",
            booking_url="pending",
            booking_status="booking_requested",
            icp_segment=icp_segment,
            signal_enrichment=signal_enrichment,
            enrichment_timestamp=enrichment_timestamp,
            company_name=company_name,
        )
    else:
        contact_id = hubspot_client.upsert_contact(
            email,
            icp_segment=icp_segment,
            signal_enrichment=signal_enrichment,
            enrichment_timestamp=enrichment_timestamp,
            company_name=company_name,
            booking_status="booking_requested",
        )

    booking = calcom_client.book_discovery_call(
        email=email,
        name=name,
        company=company_name,
        segment=icp_segment,
        signal_enrichment=signal_enrichment,
        hubspot_contact_id=contact_id,
        endpoint=booking_endpoint,
        session=booking_session,
    )

    hubspot_client.record_booking(
        contact_id,
        email=email,
        booking_id=booking.booking_id,
        booking_url=booking.booking_url,
        booking_status="booked",
        icp_segment=icp_segment,
        signal_enrichment=signal_enrichment,
        enrichment_timestamp=enrichment_timestamp,
        company_name=company_name,
    )

    return {
        "contact_id": contact_id,
        "booking_id": booking.booking_id,
        "booking_url": booking.booking_url,
        "scheduled_start": booking.scheduled_start,
        "scheduled_end": booking.scheduled_end,
        "hubspot_updated": True,
    }
