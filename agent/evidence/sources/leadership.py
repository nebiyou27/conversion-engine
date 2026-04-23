"""Leadership-transition fixture loader. Emits one Fact per event."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from agent.evidence.schema import EvidenceFormatError, Fact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(section, *, company_id: str) -> list[Fact]:
    if section is None:
        return []
    if not isinstance(section, list):
        raise EvidenceFormatError(
            f"leadership section must be a list, got {type(section).__name__}"
        )

    facts: list[Fact] = []
    for i, item in enumerate(section):
        if not isinstance(item, dict):
            raise EvidenceFormatError(f"leadership[{i}] must be a dict")
        required = ("event", "person", "effective", "source_url")
        missing = [k for k in required if k not in item]
        if missing:
            raise EvidenceFormatError(f"leadership[{i}] missing: {missing}")

        event = item["event"]
        person = item["person"]
        effective = item["effective"]
        facts.append(Fact(
            company_id=company_id,
            source_type="leadership",
            kind="leadership_change",
            summary=f"{event}: {person}, effective {effective}",
            payload={"event": event, "person": person, "effective": effective},
            source_url=item["source_url"],
            retrieved_at=item.get("retrieved_at") or _now(),
        ))
    return facts


def detect_leadership_changes(
    section: Any,
    *,
    company_id: str,
    source_url: str | None = None,
) -> list[Fact]:
    """Normalize a leadership feed into Facts.

    This accepts the same shape as the fixture loader but provides a clearer
    live-facing name for the change-detection step.
    """
    if isinstance(section, dict):
        items: list[dict[str, Any]] = [section]
    else:
        items = list(section) if section is not None else []

    if source_url:
        normalized: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and "source_url" not in item:
                normalized.append({**item, "source_url": source_url})
            else:
                normalized.append(item)
        items = normalized

    return load(items, company_id=company_id)
