"""Sensitivity-axis claim kinds.

Used by the actions layer to override mood to interrogative regardless of
tier strength. Derived from the Phase A4 A/B finding: research-grounded
outreach underperforms generic outreach when sensitive claim-kinds are
surfaced directly. The sensitivity axis is orthogonal to the tier axis.
"""
from __future__ import annotations

SENSITIVE_CLAIM_KINDS = frozenset({
    "layoff_event",
    "ai_maturity_below_2",
    "capability_gap_primary_deficit",
    "contradictory_signals",
})
