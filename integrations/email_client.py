"""Resend email wrapper. Routes to staff sink unless ALLOW_REAL_PROSPECT_CONTACT=true."""
import os
import resend
from dotenv import load_dotenv

load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")

_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
_SINK = os.getenv("STAFF_SINK_EMAIL")
_ALLOW_REAL = os.getenv("ALLOW_REAL_PROSPECT_CONTACT", "false").lower() == "true"


def send(to: str, subject: str, html: str) -> str:
    """Send an email. Returns Resend message ID. Routes to sink unless real contact is enabled."""
    actual_to = to if _ALLOW_REAL else _SINK
    response = resend.Emails.send({
        "from": _FROM,
        "to": actual_to,
        "subject": subject,
        "html": html,
    })
    return response.get("id", "")
