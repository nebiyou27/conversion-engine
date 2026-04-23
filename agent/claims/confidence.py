"""Pure tier computation. No DB access.

Age clock is the most-recent event-date among primary rows. Falls back to
`retrieved_at` only when the source carries no event-date field.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from agent.claims.tiers import (
    BELOW_THRESHOLD,
    CORROBORATED,
    CORROBORATED_MAX_AGE_DAYS,
    EVENT_DATE_KEY,
    INFERRED,
    PRIMARY,
    SECONDARY,
    VERIFIED,
    VERIFIED_MAX_AGE_DAYS,
)


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _event_date(row: dict) -> datetime | None:
    payload_raw = row.get("raw_payload")
    if payload_raw:
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
        key = EVENT_DATE_KEY.get(row.get("source_type", ""))
        if key and key in payload:
            return _parse_iso(payload[key])
    retrieved = row.get("retrieved_at")
    return _parse_iso(retrieved) if retrieved else None


def compute_tier(
    evidence_rows: Iterable[dict],
    *,
    claim_kind: str,
    now: datetime,
) -> str:
    primary_types = PRIMARY[claim_kind]
    secondary_types = SECONDARY[claim_kind]

    primary_urls: set[str] = set()
    secondary_urls: set[str] = set()
    primary_dates: list[datetime] = []

    for row in evidence_rows:
        st = row["source_type"]
        url = row["source_url"]
        if st in primary_types:
            primary_urls.add(url)
            ed = _event_date(row)
            if ed is not None:
                primary_dates.append(ed)
        elif st in secondary_types:
            secondary_urls.add(url)

    p = len(primary_urls)
    s = len(secondary_urls)

    if not primary_dates:
        age_days: int | None = None
    else:
        age_days = (now - max(primary_dates)).days

    if p >= 2 and age_days is not None and age_days <= VERIFIED_MAX_AGE_DAYS:
        return VERIFIED
    if p >= 1 and (p + s) >= 2 and age_days is not None and age_days <= CORROBORATED_MAX_AGE_DAYS:
        return CORROBORATED
    if p == 1 and s == 0 and age_days is not None and age_days <= VERIFIED_MAX_AGE_DAYS:
        return INFERRED
    if p == 0 and s >= 1:
        return INFERRED
    return BELOW_THRESHOLD
