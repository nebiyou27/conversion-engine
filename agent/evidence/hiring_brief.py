"""Merged hiring-signal brief.

Aggregates job-post evidence from every supported source (BuiltIn / Wellfound /
LinkedIn scrapers + Greenhouse / Lever ATS APIs) into a single normalized
schema for the judgment and actions layers.

Schema:
{
  "company_id": str,
  "generated_at": iso_utc,
  "sources_checked": list[str],         # e.g. ["greenhouse", "lever", "builtin"]
  "sources_with_data": list[str],       # subset that returned facts
  "total_postings": int,
  "freshness": {
    "latest_posted_on": iso | None,
    "oldest_posted_on": iso | None,
    "median_age_days": float | None
  },
  "velocity": {                         # 60-day delta from job_posts.compute_60d_velocity
    "window_days": 60,
    "curr_count": int,
    "prior_count": int,
    "delta_pct": float | None
  },
  "role_mix": {                         # rough role-family histogram
    "engineering": int,
    "ml_ai": int,
    "data": int,
    "leadership": int,
    "other": int
  },
  "confidence": float,                  # 0-1, function of source count + freshness
  "per_source_count": {source_id: int}  # facts per platform/scraper
}
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from statistics import median
from typing import Any

from agent.evidence.schema import Fact
from agent.evidence.sources.job_posts import compute_60d_velocity

ROLE_PATTERNS = {
    "ml_ai": re.compile(r"\b(ml|machine learning|ai|artificial intelligence|deep learning|llm|nlp|computer vision|cv)\b", re.I),
    "data": re.compile(r"\b(data engineer|data scientist|analytics|analyst|bi)\b", re.I),
    "leadership": re.compile(r"\b(head of|director|vp|chief|manager|lead|principal|staff)\b", re.I),
    "engineering": re.compile(r"\b(engineer|developer|swe|sre|devops|platform|backend|frontend|full[- ]?stack|mobile|ios|android)\b", re.I),
}


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _classify_role(title: str) -> str:
    if ROLE_PATTERNS["ml_ai"].search(title):
        return "ml_ai"
    if ROLE_PATTERNS["data"].search(title):
        return "data"
    if ROLE_PATTERNS["leadership"].search(title):
        return "leadership"
    if ROLE_PATTERNS["engineering"].search(title):
        return "engineering"
    return "other"


def _source_id(fact: Fact) -> str:
    """Discriminate source within source_type=job_posts."""
    platform = (fact.payload or {}).get("platform")
    if platform:
        return platform
    if fact.method in ("greenhouse_api", "lever_api"):
        return fact.method.replace("_api", "")
    if fact.method == "playwright":
        return "scraper"
    return fact.method or "fixture"


def build_hiring_brief(
    job_post_facts: list[Fact],
    *,
    company_id: str,
    sources_checked: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the merged hiring brief from a list of job_post Facts."""
    now = now or datetime.now(timezone.utc)
    facts = [f for f in job_post_facts if f.source_type == "job_posts"]

    per_source_count: dict[str, int] = {}
    role_mix = {"engineering": 0, "ml_ai": 0, "data": 0, "leadership": 0, "other": 0}
    posted_dates: list[datetime] = []

    for fact in facts:
        sid = _source_id(fact)
        per_source_count[sid] = per_source_count.get(sid, 0) + 1
        title = (fact.payload or {}).get("title") or ""
        role_mix[_classify_role(title)] += 1
        posted = _parse_iso((fact.payload or {}).get("posted_on"))
        if posted:
            posted_dates.append(posted)

    if posted_dates:
        latest = max(posted_dates)
        oldest = min(posted_dates)
        ages = sorted([(now - d).days for d in posted_dates])
        med_age = float(median(ages))
        freshness = {
            "latest_posted_on": latest.isoformat(timespec="seconds"),
            "oldest_posted_on": oldest.isoformat(timespec="seconds"),
            "median_age_days": med_age,
        }
    else:
        freshness = {"latest_posted_on": None, "oldest_posted_on": None, "median_age_days": None}

    velocity = compute_60d_velocity(facts, now=now)

    sources_with_data = sorted(per_source_count.keys())
    source_breadth = min(1.0, len(sources_with_data) / 3.0)
    posting_volume = min(1.0, len(facts) / 10.0)
    freshness_score = 0.0
    if freshness["median_age_days"] is not None:
        freshness_score = max(0.0, 1.0 - (freshness["median_age_days"] / 180.0))
    confidence = round(0.4 * source_breadth + 0.3 * posting_volume + 0.3 * freshness_score, 3)

    return {
        "company_id": company_id,
        "generated_at": now.isoformat(timespec="seconds"),
        "sources_checked": sorted(set(sources_checked)),
        "sources_with_data": sources_with_data,
        "total_postings": len(facts),
        "freshness": freshness,
        "velocity": velocity,
        "role_mix": role_mix,
        "confidence": confidence,
        "per_source_count": per_source_count,
    }


def build_hiring_brief_from_rows(
    rows: list[dict[str, Any]],
    *,
    company_id: str,
    sources_checked: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Convert evidence DB rows into Facts and build the brief."""
    facts: list[Fact] = []
    for row in rows:
        if row.get("source_type") != "job_posts":
            continue
        payload_raw = row.get("raw_payload")
        payload: dict[str, Any] = {}
        if payload_raw:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
        facts.append(Fact(
            company_id=row.get("company_id", company_id),
            source_type="job_posts",
            kind=payload.get("kind", "job_posting"),
            summary=row.get("fact", ""),
            payload=payload,
            source_url=row.get("source_url", ""),
            retrieved_at=row.get("retrieved_at") or "",
            method=row.get("method", "fixture"),
        ))
    return build_hiring_brief(facts, company_id=company_id, sources_checked=sources_checked, now=now)
