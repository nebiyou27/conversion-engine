"""Company-metadata fixture loader. Emits one Fact per company-attribute snapshot.

Distinct source_type ('company_metadata') so the claim builder does not conflate
these attributional rows with behavioral signals sharing an underlying scraper.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent.evidence.schema import EvidenceFormatError, Fact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(section, *, company_id: str) -> list[Fact]:
    if section is None:
        return []
    if not isinstance(section, dict):
        raise EvidenceFormatError(
            f"company_metadata section must be a dict, got {type(section).__name__}"
        )

    required = ("headcount", "source_url")
    missing = [k for k in required if k not in section]
    if missing:
        raise EvidenceFormatError(f"company_metadata missing: {missing}")

    headcount = section["headcount"]
    if not isinstance(headcount, int) or isinstance(headcount, bool) or headcount < 0:
        raise EvidenceFormatError(
            f"company_metadata.headcount must be a non-negative int, got {headcount!r}"
        )

    hq = section.get("hq_country")
    founded = section.get("founded_year")
    payload = {"headcount": headcount}
    if hq is not None:
        payload["hq_country"] = hq
    if founded is not None:
        payload["founded_year"] = founded

    return [Fact(
        company_id=company_id,
        source_type="company_metadata",
        kind="company_metadata",
        summary=f"Headcount: {headcount}" + (f", HQ: {hq}" if hq else ""),
        payload=payload,
        source_url=section["source_url"],
        retrieved_at=section.get("retrieved_at") or _now(),
    )]
