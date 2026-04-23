"""Structured signal-enrichment artifact builder.

This sits on top of the evidence layer and turns raw source rows into a
reviewer-friendly artifact with per-signal confidence scores.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SOURCE_IMPLEMENTATIONS = {
    "crunchbase": "Crunchbase ODM lookup",
    "job_posts": "Playwright job-post scraping",
    "layoffs": "layoffs.fyi CSV parsing",
    "leadership": "Leadership change detection",
    "company_metadata": "Company metadata snapshot",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _confidence_for(source_type: str, rows: list[dict[str, Any]], now: datetime) -> float:
    if not rows:
        if source_type == "company_metadata":
            return 0.0
        if source_type in {"crunchbase", "leadership"}:
            return 0.15
        return 0.05

    latest = max((_parse_iso(r.get("retrieved_at")) for r in rows), default=None)
    age_days = (now - latest).days if latest else None
    freshness_bonus = 0.0 if age_days is None else max(0.0, 0.15 - (age_days / 365.0))
    count_bonus = min(0.25, max(0, len(rows) - 1) * 0.05)

    base = {
        "crunchbase": 0.7,
        "job_posts": 0.45,
        "layoffs": 0.6,
        "leadership": 0.7,
        "company_metadata": 0.9,
    }.get(source_type, 0.3)

    return round(min(0.99, base + freshness_bonus + count_bonus), 3)


def build_enrichment_artifact(
    conn,
    company_id: str,
    *,
    company_name: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a structured per-signal enrichment artifact from evidence rows."""
    now = now or datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT * FROM evidence WHERE company_id = ? ORDER BY retrieved_at ASC",
        (company_id,),
    ).fetchall()
    evidence_rows = [dict(r) for r in rows]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        grouped.setdefault(row["source_type"], []).append(row)

    signals: list[dict[str, Any]] = []
    for source_type, implementation in SOURCE_IMPLEMENTATIONS.items():
        source_rows = grouped.get(source_type, [])
        confidence = _confidence_for(source_type, source_rows, now)
        latest_retrieved_at = max((r.get("retrieved_at") for r in source_rows if r.get("retrieved_at")), default=None)
        signals.append({
            "signal": source_type,
            "implementation": implementation,
            "status": "present" if source_rows else "absent",
            "confidence": confidence,
            "evidence_count": len(source_rows),
            "latest_retrieved_at": latest_retrieved_at,
            "source_urls": [r["source_url"] for r in source_rows],
        })

    return {
        "company_id": company_id,
        "company_name": company_name,
        "generated_at": _now(),
        "source_implementations": SOURCE_IMPLEMENTATIONS,
        "signals": signals,
        "per_signal_confidence": {s["signal"]: s["confidence"] for s in signals},
        "evidence_count": len(evidence_rows),
    }
