"""Resend email wrapper. Routes to staff sink unless ALLOW_REAL_PROSPECT_CONTACT=true."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from integrations.retry import retry_call

load_dotenv()

logger = logging.getLogger(__name__)

_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
_SINK = os.getenv("STAFF_SINK_EMAIL")
_ALLOW_REAL = os.getenv("ALLOW_REAL_PROSPECT_CONTACT", "false").lower() == "true"


class EmailSendError(RuntimeError):
    """Raised when Resend rejects a send or returns an unusable response."""


def _get_resend_client():
    try:
        import resend
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("resend package is not installed") from exc

    resend.api_key = os.getenv("RESEND_API_KEY")
    return resend


def send(to: str, subject: str, html: str) -> str:
    """Send an email. Returns Resend message ID. Routes to sink unless real contact is enabled."""
    resend = _get_resend_client()
    actual_to = to if _ALLOW_REAL else _SINK
    if not actual_to:
        raise EmailSendError("STAFF_SINK_EMAIL is required when real prospect contact is disabled")

    def _send_once() -> dict:
        logger.info("email_send_attempt to=%s real_contact=%s", actual_to, _ALLOW_REAL)
        return resend.Emails.send({
            "from": _FROM,
            "to": actual_to,
            "subject": subject,
            "html": html,
        })

    try:
        response = retry_call(_send_once, operation_name="Resend email send")
    except Exception as exc:  # pragma: no cover - integration-level failure
        logger.exception("email_send_failed to=%s", actual_to)
        raise EmailSendError(f"Resend send failed for {actual_to}: {exc}") from exc

    message_id = response.get("id", "")
    if not message_id:
        raise EmailSendError(f"Resend returned no message id: {response!r}")

    logger.info("email_send_success to=%s message_id=%s", actual_to, message_id)
    return message_id
