"""Outbound email handler and inbound webhook normalization."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal

from integrations import email_client
from agent.runtime import claim_once, log_event, stable_key

EmailEventType = Literal["reply", "bounce", "delivery", "failed", "complaint", "unknown"]
EmailEventHandler = Callable[["NormalizedEmailEvent"], None]

logger = logging.getLogger(__name__)


class EmailHandlerError(Exception):
    """Base error for email handler failures."""


class EmailDeliveryError(EmailHandlerError):
    """Raised when outbound email sending fails."""


class EmailWebhookError(EmailHandlerError):
    """Raised when an inbound webhook payload is malformed."""


@dataclass(frozen=True)
class NormalizedEmailEvent:
    """Provider-neutral inbound email event."""

    event_type: EmailEventType
    message_id: str | None
    sender: str | None
    recipient: str | None
    subject: str | None
    body: str | None
    raw: dict[str, Any]


_EVENT_HANDLER: EmailEventHandler | None = None


def register_event_handler(handler: EmailEventHandler | None) -> EmailEventHandler | None:
    """Register a downstream callback for inbound events.

    Returns the previous handler so callers can restore it after tests.
    """
    global _EVENT_HANDLER
    previous = _EVENT_HANDLER
    _EVENT_HANDLER = handler
    return previous


def clear_event_handler() -> None:
    """Remove any registered inbound event callback."""
    register_event_handler(None)


def send_outbound_email(to: str, subject: str, html: str) -> str:
    """Send an outbound email through the Resend wrapper.

    The underlying integration routes to the staff sink unless the real-prospect
    kill switch is enabled. Failures are surfaced as exceptions so they cannot
    disappear silently.
    """
    try:
        message_id = email_client.send(to=to, subject=subject, html=html)
    except Exception as exc:  # pragma: no cover - integration-level failure
        log_event(logger, logging.ERROR, "email_send_error", to=to, subject=subject, error=str(exc))
        raise EmailDeliveryError(f"Outbound email send failed: {exc}") from exc

    if not message_id:
        raise EmailDeliveryError("Outbound email send failed: missing message id")
    log_event(logger, logging.INFO, "email_send_ok", to=to, subject=subject, message_id=message_id)
    return message_id


def handle_webhook_payload(payload: Any) -> dict[str, Any]:
    """Normalize an inbound webhook payload and dispatch it downstream."""
    event = _normalize_payload(payload)
    event_key = _event_key(event)

    if not claim_once("email_webhooks", event_key, payload={"event_type": event.event_type, "message_id": event.message_id}):
        log_event(logger, logging.INFO, "email_webhook_replayed", event_type=event.event_type, message_id=event.message_id, event_key=event_key)
        return {
            "ok": True,
            "event_type": event.event_type,
            "message_id": event.message_id,
            "handled": False,
            "replayed": True,
            "event_key": event_key,
        }

    if _EVENT_HANDLER is not None:
        log_event(logger, logging.INFO, "email_webhook_dispatch", event_type=event.event_type, message_id=event.message_id, event_key=event_key)
        _EVENT_HANDLER(event)

    return {
        "ok": True,
        "event_type": event.event_type,
        "message_id": event.message_id,
        "handled": _EVENT_HANDLER is not None,
        "replayed": False,
        "event_key": event_key,
    }


def _normalize_payload(payload: Any) -> NormalizedEmailEvent:
    if not isinstance(payload, dict):
        raise EmailWebhookError("Email webhook payload must be a JSON object")

    raw_event = _first_string(payload, "type", "event", "name", "event_type")
    if not raw_event:
        raise EmailWebhookError("Email webhook payload missing event type")

    event_type = _classify_event_type(raw_event)
    if event_type == "unknown":
        raise EmailWebhookError(f"Unrecognized email webhook event type: {raw_event}")

    message_id = _first_string(payload, "message_id", "email_id", "id", "Message-Id")
    sender = _first_string(payload, "from", "from_email", "sender", "mail_from")
    recipient = _first_string(payload, "to", "to_email", "recipient", "mail_to")
    subject = _first_string(payload, "subject", "Subject")
    body = _first_string(payload, "text", "body", "body_text", "plain_text", "html")

    if event_type == "reply" and not any([sender, recipient, subject, body, message_id]):
        raise EmailWebhookError("Reply webhook missing reply metadata")
    if event_type in {"bounce", "failed"} and not message_id:
        raise EmailWebhookError(f"{event_type} webhook missing message_id")

    return NormalizedEmailEvent(
        event_type=event_type,
        message_id=message_id,
        sender=sender,
        recipient=recipient,
        subject=subject,
        body=body,
        raw=payload,
    )


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _classify_event_type(raw_event: str) -> EmailEventType:
    event = raw_event.strip().lower()
    if any(token in event for token in ("reply", "inbound", "received")):
        return "reply"
    if any(token in event for token in ("bounce", "bounced")):
        return "bounce"
    if any(token in event for token in ("fail", "error", "rejected", "blocked")):
        return "failed"
    if any(token in event for token in ("deliver", "delivered", "delivery")):
        return "delivery"
    if "complaint" in event:
        return "complaint"
    return "unknown"


def _event_key(event: NormalizedEmailEvent) -> str:
    if event.message_id:
        return stable_key("email", event.event_type, event.message_id)
    return stable_key("email", event.event_type, event.sender, event.recipient, event.subject, event.body, event.raw)
