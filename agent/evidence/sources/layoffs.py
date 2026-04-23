"""Layoffs.fyi-shaped fixture loader. Emits one Fact per layoff event."""
from __future__ import annotations

import csv
from io import StringIO
from datetime import datetime, timezone
from typing import Any

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


def parse_layoffs_csv(
    csv_text: str,
    *,
    company_id: str,
    source_url: str = "https://layoffs.fyi",
) -> list[Fact]:
    """Parse a layoffs.fyi-style CSV into Facts."""
    reader = csv.DictReader(StringIO(csv_text))
    facts: list[Fact] = []
    for i, row in enumerate(reader):
        if not isinstance(row, dict):
            raise EvidenceFormatError(f"layoffs CSV row {i} must be a dict")
        event_on = row.get("event_on") or row.get("date") or row.get("laid_off_at")
        headcount_raw = row.get("headcount") or row.get("laid_off") or row.get("count")
        if not event_on or not headcount_raw:
            raise EvidenceFormatError(f"layoffs CSV row {i} missing event date or headcount")
        try:
            headcount = int(str(headcount_raw).replace(",", "").strip())
        except ValueError as exc:
            raise EvidenceFormatError(f"layoffs CSV row {i} headcount must be numeric") from exc

        source = row.get("source_url") or source_url
        company = row.get("company") or row.get("org") or company_id
        facts.append(Fact(
            company_id=company_id,
            source_type="layoffs",
            kind="layoff_event",
            summary=f"{company} laid off {headcount} on {event_on}",
            payload={"event_on": event_on, "headcount": headcount, "company": company},
            source_url=source,
            retrieved_at=row.get("retrieved_at") or _now(),
            method="csv",
        ))
    return facts


def load_live_layoffs_csv(
    csv_text: str,
    *,
    company_id: str,
    source_url: str = "https://layoffs.fyi",
) -> list[Fact]:
    """Live-facing alias for layoffs.fyi CSV ingestion."""
    return parse_layoffs_csv(csv_text, company_id=company_id, source_url=source_url)


def fetch_layoffs_csv(
    url: str,
    *,
    company_id: str,
    session: Any | None = None,
) -> list[Fact]:
    """Fetch layoffs.fyi CSV content and parse it.

    This keeps scraping limited to public CSV retrieval with no login or
    captcha-bypass logic.
    """
    import requests

    requester = session or requests
    response = requester.get(url, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Layoffs CSV fetch failed: {response.status_code} {response.text}")
    return parse_layoffs_csv(response.text, company_id=company_id, source_url=url)
