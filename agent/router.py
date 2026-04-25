"""Central conversation router for channel and state handoff."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from integrations import calcom_client

Channel = Literal["email", "sms", "none"]


class ConversationState(Enum):
    NEW_LEAD = "new_lead"
    RESEARCHING = "researching"
    DRAFTED = "drafted"
    GATED = "gated"
    SENT = "sent"
    REPLIED = "replied"
    SCHEDULING = "scheduling"
    BOOKED = "booked"
    HUMAN_QUEUED = "human_queued"


@dataclass(frozen=True)
class RouteDecision:
    previous_state: ConversationState
    next_state: ConversationState
    channel: Channel
    booking_link: str | None = None


def parse_state(value: str | ConversationState | None) -> ConversationState:
    if isinstance(value, ConversationState):
        return value
    if not value:
        return ConversationState.SENT
    try:
        return ConversationState(value)
    except ValueError:
        return ConversationState.SENT


def handoff(
    state: str | ConversationState | None,
    event: str,
    *,
    source_channel: str = "email",
    email: str | None = None,
    name: str | None = None,
    company: str | None = None,
) -> RouteDecision:
    """Return the next state and channel for an inbound/outbound event."""
    current = parse_state(state)
    normalized_event = event.strip().lower()

    if normalized_event == "drafted":
        return RouteDecision(current, ConversationState.DRAFTED, "email")
    if normalized_event == "gate_failed":
        return RouteDecision(current, ConversationState.HUMAN_QUEUED, "none")
    if normalized_event == "gate_passed":
        return RouteDecision(current, ConversationState.GATED, "email")
    if normalized_event == "sent":
        return RouteDecision(current, ConversationState.SENT, "email")
    if normalized_event == "booked":
        return RouteDecision(current, ConversationState.BOOKED, "none")
    if normalized_event == "reply":
        booking_link = calcom_client.generate_booking_link(
            email=email,
            name=name,
            company=company,
            source_channel=source_channel,
        )
        return RouteDecision(current, ConversationState.SCHEDULING, source_channel, booking_link)

    return RouteDecision(current, current, "none")
