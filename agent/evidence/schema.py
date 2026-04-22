"""Evidence-layer data carrier.

Fact is the structured handoff between source loaders and the collector.
The collector maps Fact fields to DB columns via storage.db.insert_evidence.
"""
from __future__ import annotations

from dataclasses import dataclass


class EvidenceFormatError(ValueError):
    """A fixture section is present but malformed. Must fail loud, not degrade silently."""


@dataclass(frozen=True)
class Fact:
    company_id: str
    source_type: str   # "crunchbase" | "job_posts" | "layoffs" | "leadership"
    kind: str          # "funding_round" | "job_posting" | "layoff_event" | "leadership_change"
    summary: str       # human-readable, written to evidence.fact
    payload: dict      # structured, merged with kind and written to evidence.raw_payload
    source_url: str
    retrieved_at: str  # ISO UTC; honored if fixture supplies it, else collector stamps now
    method: str = "fixture"

    def __post_init__(self):
        if not self.source_url:
            raise ValueError("source_url required — audit trail is mandatory")
