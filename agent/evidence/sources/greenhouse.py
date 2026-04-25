"""Greenhouse Job Boards API client.

Compliance notes:
  - Public Greenhouse boards API only (no token, no scraping).
  - Endpoint: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
  - Returns JSON; no robots.txt issues since this is a documented public API.
  - Failed loads abstain silently — no aggressive retry.

Normalization:
  - Emits Fact with source_type="job_posts" so the claims layer treats it as
    primary hiring evidence. The `payload["platform"]` field discriminates ATS
    origin (greenhouse vs lever vs scraped).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.evidence.schema import Fact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_or_now(value: Any) -> str:
    if not value:
        return _now()
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(timespec="seconds")
    except ValueError:
        return _now()


def parse_greenhouse_jobs(
    payload: dict[str, Any],
    *,
    company_id: str,
    board_token: str,
) -> list[Fact]:
    """Parse Greenhouse jobs API response into Facts."""
    jobs = payload.get("jobs") or []
    facts: list[Fact] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = job.get("title")
        url = job.get("absolute_url")
        if not title or not url:
            continue
        departments = [d.get("name") for d in (job.get("departments") or []) if isinstance(d, dict) and d.get("name")]
        offices = [o.get("name") for o in (job.get("offices") or []) if isinstance(o, dict) and o.get("name")]
        posted_on = _iso_or_now(job.get("updated_at"))
        facts.append(Fact(
            company_id=company_id,
            source_type="job_posts",
            kind="job_posting",
            summary=f"Posted '{title}' on {posted_on}",
            payload={
                "platform": "greenhouse",
                "title": title,
                "posted_on": posted_on,
                "departments": departments,
                "offices": offices,
                "board_token": board_token,
                "external_id": job.get("id"),
            },
            source_url=url,
            retrieved_at=_now(),
            method="greenhouse_api",
        ))
    return facts


def fetch_greenhouse_jobs(
    board_token: str,
    *,
    company_id: str,
    session: Any | None = None,
) -> list[Fact]:
    """Fetch and parse a company's Greenhouse public board.

    `board_token` is the company's slug on Greenhouse, e.g. "airbnb" for
    https://boards.greenhouse.io/airbnb.
    """
    import requests

    requester = session or requests
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
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
    return parse_greenhouse_jobs(payload, company_id=company_id, board_token=board_token)
