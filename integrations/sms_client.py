"""Africa's Talking SMS wrapper."""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_ALLOW_REAL = os.getenv("ALLOW_REAL_PROSPECT_CONTACT", "false").lower() == "true"
_SINK = os.getenv("STAFF_SINK_PHONE_NUMBER")
_SENDER_ID = os.getenv("AFRICASTALKING_SENDER_ID")


def _get_sms_service():
    try:
        import africastalking
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("africastalking package is not installed") from exc

    username = os.getenv("AFRICASTALKING_USERNAME")
    api_key = os.getenv("AFRICASTALKING_API_KEY")
    if not username or not api_key:
        raise RuntimeError("AFRICASTALKING_USERNAME and AFRICASTALKING_API_KEY are required")

    africastalking.initialize(username, api_key)
    return africastalking.SMS


def send_message(to: str, message: str, *, sender_id: str | None = None) -> dict[str, Any]:
    """Send an SMS through Africa's Talking.

    Messages route to the staff sink unless the real-prospect kill switch is enabled.
    """
    actual_to = to if _ALLOW_REAL else _SINK
    if not actual_to:
        raise RuntimeError("STAFF_SINK_PHONE_NUMBER is required when real prospect contact is disabled")

    sms = _get_sms_service()
    result = sms.send(
        message,
        [actual_to],
        sender_id=sender_id or _SENDER_ID,
    )
    return {
        "to": actual_to,
        "message": message,
        "sender_id": sender_id or _SENDER_ID,
        "raw": result,
    }
