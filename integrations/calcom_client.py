"""Cal.com booking wrapper."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _configured_endpoint() -> str:
    return (
        os.getenv("CALCOM_API_ENDPOINT")
        or os.getenv("CALCOM_BOOKING_ENDPOINT")
        or os.getenv("CALCOM_BOOKING_URL", "")
    )


@dataclass(frozen=True)
class BookingResult:
    booking_id: str
    booking_url: str
    scheduled_start: str | None
    scheduled_end: str | None
    raw: dict[str, Any]


def book_discovery_call(
    *,
    email: str,
    name: str | None = None,
    company: str | None = None,
    segment: str | None = None,
    signal_enrichment: dict[str, Any] | None = None,
    hubspot_contact_id: str | None = None,
    scheduled_start: str | None = None,
    scheduled_end: str | None = None,
    endpoint: str | None = None,
    session: requests.Session | None = None,
) -> BookingResult:
    """Book a discovery call via Cal.com.

    The endpoint can be overridden for tests or deployment-specific Cal.com
    configurations. The result intentionally carries booking metadata that can
    be written back to HubSpot immediately after a successful booking.
    """
    url = endpoint or _configured_endpoint()
    if not url:
        raise RuntimeError("CALCOM_API_ENDPOINT or CALCOM_BOOKING_URL is required")

    payload: dict[str, Any] = {
        "email": email,
        "name": name,
        "company": company,
        "segment": segment,
        "signal_enrichment": signal_enrichment,
        "hubspot_contact_id": hubspot_contact_id,
        "scheduled_start": scheduled_start,
        "scheduled_end": scheduled_end,
        "created_at": _now(),
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = os.getenv("CALCOM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    requester = session or requests
    response = requester.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Cal.com booking failed: {response.status_code} {response.text}")

    data = response.json() if response.content else {}
    booking_id = str(data.get("booking_id") or data.get("id") or data.get("uid") or "")
    booking_url = str(
        data.get("booking_url")
        or data.get("url")
        or data.get("bookingUrl")
        or os.getenv("CALCOM_BOOKING_URL", "")
    )
    if not booking_id:
        booking_id = f"calcom-{int(datetime.now(timezone.utc).timestamp())}"
    if not booking_url:
        booking_url = os.getenv("CALCOM_BOOKING_URL", url)

    return BookingResult(
        booking_id=booking_id,
        booking_url=booking_url,
        scheduled_start=data.get("scheduled_start") or scheduled_start,
        scheduled_end=data.get("scheduled_end") or scheduled_end,
        raw=data,
    )
