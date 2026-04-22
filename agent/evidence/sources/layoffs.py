"""Layoffs.fyi-shaped fixture loader. Emits one Fact per layoff event."""
from __future__ import annotations

from datetime import datetime, timezone

from agent.evidence.schema import EvidenceFormatError, Fact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(section, *, company_id: str) -> list[Fact]:
    if section is None:
        return []
    if not isinstance(section, list):
        raise EvidenceFormatError(
            f"layoffs section must be a list, got {type(section).__name__}"
        )

    facts: list[Fact] = []
    for i, item in enumerate(section):
        if not isinstance(item, dict):
            raise EvidenceFormatError(f"layoffs[{i}] must be a dict")
        required = ("event_on", "headcount", "source_url")
        missing = [k for k in required if k not in item]
        if missing:
            raise EvidenceFormatError(f"layoffs[{i}] missing: {missing}")

        headcount = item["headcount"]
        if not isinstance(headcount, int) or isinstance(headcount, bool):
            raise EvidenceFormatError(
                f"layoffs[{i}].headcount must be int, got {type(headcount).__name__}"
            )

        event_on = item["event_on"]
        facts.append(Fact(
            company_id=company_id,
            source_type="layoffs",
            kind="layoff_event",
            summary=f"Laid off {headcount} on {event_on}",
            payload={"event_on": event_on, "headcount": headcount},
            source_url=item["source_url"],
            retrieved_at=item.get("retrieved_at") or _now(),
        ))
    return facts
