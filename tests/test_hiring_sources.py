"""Tests for ATS hiring sources and the merged hiring brief."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from agent.evidence.hiring_brief import build_hiring_brief
from agent.evidence.schema import Fact
from agent.evidence.sources import greenhouse, lever


@dataclass
class _FakeResponse:
    data: object
    status_code: int = 200

    def json(self):
        return self.data

    @property
    def text(self):
        return json.dumps(self.data)


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self.response = response
        self.last_url: str | None = None

    def get(self, url: str, timeout: int = 30):
        self.last_url = url
        return self.response


# ---------- Greenhouse ----------

def test_greenhouse_parses_jobs_and_normalizes_to_job_posts():
    payload = {
        "jobs": [
            {
                "id": 4001,
                "title": "Staff ML Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/4001",
                "updated_at": "2026-04-15T12:00:00Z",
                "departments": [{"name": "Machine Learning"}],
                "offices": [{"name": "Remote - US"}],
            },
            {
                "id": 4002,
                "title": "Senior Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/4002",
                "updated_at": "2026-04-10T12:00:00Z",
                "departments": [{"name": "Engineering"}],
                "offices": [],
            },
        ]
    }
    facts = greenhouse.parse_greenhouse_jobs(payload, company_id="acme", board_token="acme")
    assert len(facts) == 2
    assert all(f.source_type == "job_posts" for f in facts)
    assert all(f.payload["platform"] == "greenhouse" for f in facts)
    assert facts[0].method == "greenhouse_api"
    assert facts[0].payload["title"] == "Staff ML Engineer"
    assert facts[0].payload["departments"] == ["Machine Learning"]
    assert facts[0].source_url.endswith("/jobs/4001")


def test_greenhouse_skips_jobs_missing_required_fields():
    payload = {"jobs": [{"id": 1}, {"title": "x"}, {"absolute_url": "u"}]}
    facts = greenhouse.parse_greenhouse_jobs(payload, company_id="acme", board_token="acme")
    assert facts == []


def test_greenhouse_fetch_returns_empty_on_http_error():
    session = _FakeSession(_FakeResponse(data={"jobs": []}, status_code=500))
    facts = greenhouse.fetch_greenhouse_jobs("acme", company_id="acme", session=session)
    assert facts == []


def test_greenhouse_fetch_uses_documented_endpoint():
    session = _FakeSession(_FakeResponse(data={"jobs": []}))
    greenhouse.fetch_greenhouse_jobs("airbnb", company_id="airbnb", session=session)
    assert session.last_url == "https://boards-api.greenhouse.io/v1/boards/airbnb/jobs?content=true"


# ---------- Lever ----------

def test_lever_parses_postings_and_normalizes_to_job_posts():
    payload = [
        {
            "id": "abc-123",
            "text": "Senior ML Engineer",
            "categories": {"team": "Applied ML", "department": "Engineering", "location": "Remote"},
            "createdAt": 1713196800000,
            "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        },
        {
            "id": "def-456",
            "text": "Director, Data Platform",
            "categories": {"team": "Data", "department": "Engineering", "location": "NYC"},
            "createdAt": 1712000000000,
            "hostedUrl": "https://jobs.lever.co/acme/def-456",
        },
    ]
    facts = lever.parse_lever_postings(payload, company_id="acme", company_slug="acme")
    assert len(facts) == 2
    assert all(f.source_type == "job_posts" for f in facts)
    assert all(f.payload["platform"] == "lever" for f in facts)
    assert facts[0].method == "lever_api"
    assert facts[0].payload["team"] == "Applied ML"
    assert facts[1].payload["title"] == "Director, Data Platform"


def test_lever_handles_non_list_response():
    facts = lever.parse_lever_postings({"error": "nope"}, company_id="acme", company_slug="acme")
    assert facts == []


def test_lever_fetch_uses_documented_endpoint():
    session = _FakeSession(_FakeResponse(data=[]))
    lever.fetch_lever_postings("netflix", company_id="netflix", session=session)
    assert session.last_url == "https://api.lever.co/v0/postings/netflix?mode=json"


# ---------- Hiring brief ----------

def _make_fact(title: str, platform: str, posted_on: str, url: str) -> Fact:
    return Fact(
        company_id="acme",
        source_type="job_posts",
        kind="job_posting",
        summary=f"Posted '{title}' on {posted_on}",
        payload={"platform": platform, "title": title, "posted_on": posted_on},
        source_url=url,
        retrieved_at="2026-04-25T00:00:00+00:00",
        method=f"{platform}_api" if platform in {"greenhouse", "lever"} else "playwright",
    )


def test_hiring_brief_merges_multiple_sources():
    now = datetime(2026, 4, 25, tzinfo=timezone.utc)
    facts = [
        _make_fact("Staff ML Engineer", "greenhouse", "2026-04-20T00:00:00+00:00", "https://x/1"),
        _make_fact("Senior Backend Engineer", "greenhouse", "2026-04-15T00:00:00+00:00", "https://x/2"),
        _make_fact("Director, Data Platform", "lever", "2026-04-10T00:00:00+00:00", "https://x/3"),
        _make_fact("Frontend Developer", "scraper", "2026-04-05T00:00:00+00:00", "https://x/4"),
    ]
    brief = build_hiring_brief(
        facts,
        company_id="acme",
        sources_checked=["builtin", "wellfound", "linkedin", "greenhouse", "lever"],
        now=now,
    )
    assert brief["total_postings"] == 4
    assert set(brief["sources_with_data"]) == {"greenhouse", "lever", "scraper"}
    assert brief["per_source_count"] == {"greenhouse": 2, "lever": 1, "scraper": 1}
    assert brief["role_mix"]["ml_ai"] == 1
    assert brief["role_mix"]["leadership"] == 1
    assert brief["role_mix"]["engineering"] >= 1
    assert brief["freshness"]["latest_posted_on"].startswith("2026-04-20")
    assert brief["confidence"] > 0.0
    assert "velocity" in brief and brief["velocity"]["window_days"] == 60


def test_hiring_brief_handles_empty_facts():
    brief = build_hiring_brief(
        [],
        company_id="acme",
        sources_checked=["greenhouse", "lever"],
        now=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )
    assert brief["total_postings"] == 0
    assert brief["sources_with_data"] == []
    assert brief["confidence"] == 0.0
    assert brief["freshness"]["latest_posted_on"] is None
