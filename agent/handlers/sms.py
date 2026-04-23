"""SMS handler for warm-lead messaging and inbound replies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from integrations import sms_client

SmsEventType = Literal["reply", "delivery", "failed", "unknown"]
SmsEventHandler = Callable[["NormalizedSmsEvent"], None]


class SmsHandlerError(Exception):
    """Base error for SMS handler failures."""


class SmsChannelError(SmsHandlerError):
    """Raised when SMS is attempted outside the warm-lead path."""


class SmsDeliveryError(SmsHandlerError):
    """Raised when outbound SMS sending fails."""


class SmsWebhookError(SmsHandlerError):
    """Raised when inbound SMS webhook payloads are malformed."""


@dataclass(frozen=True)
class NormalizedSmsEvent:
    """Provider-neutral inbound SMS event."""

    event_type: SmsEventType
    message_id: str | None
    sender: str | None
    recipient: str | None
    body: str | None
    raw: dict[str, Any]


_EVENT_HANDLER: SmsEventHandler | None = None


def register_event_handler(handler: SmsEventHandler | None) -> SmsEventHandler | None:
    """Register a downstream callback for inbound SMS events."""
    global _EVENT_HANDLER
    previous = _EVENT_HANDLER
    _EVENT_HANDLER = handler
    return previous


def clear_event_handler() -> None:
    """Remove any registered SMS event callback."""
    register_event_handler(None)


def can_use_sms(*, prior_email_reply: bool, is_warm_lead: bool) -> bool:
    """Gate SMS to warm leads only."""
    return prior_email_reply and is_warm_lead


def send_warm_lead_sms(
    to: str,
    message: str,
    *,
    prior_email_reply: bool,
    is_warm_lead: bool,
    sender_id: str | None = None,
) -> dict[str, Any]:
    """Send SMS only after the lead is warm.

    Cold outreach is blocked here by design, not left to caller discipline.
    """
    if not can_use_sms(prior_email_reply=prior_email_reply, is_warm_lead=is_warm_lead):
        raise SmsChannelError("SMS is reserved for warm leads after an email reply")

    try:
        result = sms_client.send_message(to, message, sender_id=sender_id)
    except Exception as exc:  # pragma: no cover - integration-level failure
        raise SmsDeliveryError(f"Outbound SMS send failed: {exc}") from exc

    return {
        "ok": True,
        "channel": "sms",
        "warm_lead": True,
        **result,
    }


def handle_webhook_payload(payload: Any) -> dict[str, Any]:
    """Normalize an inbound SMS webhook payload and dispatch it downstream."""
    event = _normalize_payload(payload)

    if _EVENT_HANDLER is not None:
        _EVENT_HANDLER(event)

    return {
        "ok": True,
        "event_type": event.event_type,
        "message_id": event.message_id,
        "handled": _EVENT_HANDLER is not None,
    }


def _normalize_payload(payload: Any) -> NormalizedSmsEvent:
    if not isinstance(payload, dict):
        raise SmsWebhookError("SMS webhook payload must be a JSON object")

    raw_event = _first_string(payload, "type", "event", "name", "event_type")
    if not raw_event:
        raise SmsWebhookError("SMS webhook payload missing event type")

    event_type = _classify_event_type(raw_event)
    if event_type == "unknown":
        raise SmsWebhookError(f"Unrecognized SMS webhook event type: {raw_event}")

    message_id = _first_string(payload, "message_id", "id", "sms_id", "messageId")
    sender = _first_string(payload, "from", "sender", "msisdn", "phone_number")
    recipient = _first_string(payload, "to", "recipient", "destination", "phoneNumber")
    body = _first_string(payload, "text", "message", "body", "content")

    if event_type == "reply" and not body:
        raise SmsWebhookError("Reply webhook missing message body")

    return NormalizedSmsEvent(
        event_type=event_type,
        message_id=message_id,
        sender=sender,
        recipient=recipient,
        body=body,
        raw=payload,
    )


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _classify_event_type(raw_event: str) -> SmsEventType:
    event = raw_event.strip().lower()
    if any(token in event for token in ("reply", "inbound", "received")):
        return "reply"
    if any(token in event for token in ("deliver", "delivered", "delivery")):
        return "delivery"
    if any(token in event for token in ("fail", "error", "rejected", "blocked")):
        return "failed"
    return "unknown"
