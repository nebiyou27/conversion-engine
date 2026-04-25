"""Lever public postings API client.

Compliance notes:
  - Public Lever postings endpoint only (no auth, no scraping).
  - Endpoint: https://api.lever.co/v0/postings/{company}?mode=json
  - Returns JSON list of postings; documented public API.
  - Failed loads abstain silently.

Normalization:
  - Emits Fact with source_type="job_posts" so the claims layer treats it as
    primary hiring evidence. The `payload["platform"]` field discriminates ATS
    origin.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.evidence.schema import Fact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ms_to_iso(value: Any) -> str:
    if value in (None, ""):
        return _now()
    try:
        ms = int(value)
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return _now()


def parse_lever_postings(
    payload: list[dict[str, Any]],
    *,
    company_id: str,
    company_slug: str,
) -> list[Fact]:
    """Parse Lever postings API response into Facts."""
    if not isinstance(payload, list):
        return []
    facts: list[Fact] = []
    for posting in payload:
        if not isinstance(posting, dict):
            continue
        title = posting.get("text")
        url = posting.get("hostedUrl")
        if not title or not url:
            continue
        categories = posting.get("categories") or {}
        team = categories.get("team") if isinstance(categories, dict) else None
        department = categories.get("department") if isinstance(categories, dict) else None
        location = categories.get("location") if isinstance(categories, dict) else None
        posted_on = _ms_to_iso(posting.get("createdAt"))
        facts.append(Fact(
            company_id=company_id,
            source_type="job_posts",
            kind="job_posting",
            summary=f"Posted '{title}' on {posted_on}",
            payload={
                "platform": "lever",
                "title": title,
                "posted_on": posted_on,
                "team": team,
                "department": department,
                "location": location,
                "company_slug": company_slug,
                "external_id": posting.get("id"),
            },
            source_url=url,
            retrieved_at=_now(),
            method="lever_api",
        ))
    return facts


def fetch_lever_postings(
    company_slug: str,
    *,
    company_id: str,
    session: Any | None = None,
) -> list[Fact]:
    """Fetch and parse a company's Lever public postings."""
    import requests

    requester = session or requests
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        response = requester.get(url, timeout=30)
    except Exception:
        return []
    if getattr(response, "status_code", 500) >= 400:
        return []
    try:
        payload = response.json()
    except Exception:
        return []
    return parse_lever_postings(payload, company_id=company_id, company_slug=company_slug)
