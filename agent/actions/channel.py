"""Channel selection helpers."""
from __future__ import annotations


def can_use_sms(*, prior_email_reply: bool, is_warm_lead: bool) -> bool:
    """SMS is a warm-lead channel only."""
    return prior_email_reply and is_warm_lead


def choose_channel(
    *,
    prefer_sms: bool = False,
    prior_email_reply: bool,
    is_warm_lead: bool,
) -> str:
    """Pick email or SMS while enforcing the warm-lead hierarchy."""
    if prefer_sms and can_use_sms(prior_email_reply=prior_email_reply, is_warm_lead=is_warm_lead):
        return "sms"
    return "email"
