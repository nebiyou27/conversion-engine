"""Contract tests for the signal enrichment pipeline."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agent.evidence import collector, enrichment
from agent.evidence.sources import crunchbase, job_posts, layoffs, leadership
from storage import db

FIXTURE_PATH = Path("data/fixtures/companies/acme_series_b.json")


@dataclass
class _FakeResponse:
    data: dict
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


class _FakePage:
    def __init__(self, html: str):
        self._html = html
        self.last_url: str | None = None

    def goto(self, url: str, wait_until: str = "networkidle"):
        self.last_url = url

    def content(self):
        return self._html


class _FakeBrowser:
    def __init__(self, html: str):
        self._page = _FakePage(html)
        self.closed = False

    def new_page(self):
        return self._page

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, html: str):
        self._html = html
        self.last_launch_kwargs: dict | None = None

    def launch(self, **kwargs):
        self.last_launch_kwargs = kwargs
        return _FakeBrowser(
            """
            <html><body>
              <a href="https://example.com/jobs/acme/staff">Staff Backend Engineer</a>
              <a href="https://example.com/about">About us</a>
            </body></html>
            """
        )


class _FakePlaywright:
    def __init__(self, html: str):
        self.chromium = _FakeChromium(html)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.init(c)
    return c


def _fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_build_enrichment_artifact_has_per_signal_confidence(tmp_path):
    conn = _conn(tmp_path)
    fixture = _fixture()
    collector.collect(fixture, conn)

    artifact = enrichment.build_enrichment_artifact(conn, fixture["company_id"], company_name=fixture["name"])

    assert artifact["company_id"] == "acme"
    assert artifact["company_name"] == "Acme Data"
    assert artifact["evidence_count"] == 6
    assert set(artifact["per_signal_confidence"]) == {
        "crunchbase",
        "job_posts",
        "layoffs",
        "leadership",
        "company_metadata",
    }
    assert len(artifact["signals"]) == 5
    assert all("confidence" in signal for signal in artifact["signals"])
    assert artifact["source_implementations"]["job_posts"].startswith("Playwright")


def test_crunchbase_odm_lookup_parses_response():
    session = _FakeSession(_FakeResponse({
        "round": "Series A",
        "amount_usd": 12000000,
        "announced_on": "2026-04-01",
        "source_url": "https://example.com/crunchbase/live",
    }))

    facts = crunchbase.lookup_company_odm(
        "acme",
        company_id="acme",
        endpoint="https://example.com/odm",
        session=session,
    )

    assert session.last_url == "https://example.com/odm/acme"
    assert len(facts) == 1
    assert facts[0].kind == "funding_round"


def test_job_posts_playwright_helper_parses_rendered_html():
    page = _FakePage(
        """
        <html><body>
          <a href="https://example.com/jobs/acme/staff">Staff Backend Engineer</a>
          <a href="https://example.com/about">About us</a>
        </body></html>
        """
    )

    facts = job_posts.scrape_job_posts(
        "https://example.com/careers",
        company_id="acme",
        page=page,
        max_posts=5,
    )

    assert page.last_url == "https://example.com/careers"
    assert len(facts) == 1
    assert facts[0].kind == "job_posting"
    assert "Staff Backend Engineer" in facts[0].summary


def test_job_posts_playwright_factory_wires_browser_path():
    fake = _FakePlaywright("")

    facts = job_posts.scrape_job_posts(
        "https://example.com/careers",
        company_id="acme",
        playwright_factory=lambda: fake,
        max_posts=5,
    )

    assert fake.chromium.last_launch_kwargs == {"headless": True}
    assert len(facts) == 1
    assert facts[0].source_type == "job_posts"
    assert facts[0].source_url == "https://example.com/jobs/acme/staff"


def test_layoffs_csv_parser_emits_facts():
    facts = layoffs.parse_layoffs_csv(
        "company,date,laid_off,source_url\nAcme,2026-04-10,12,https://example.com/layoffs/acme\n",
        company_id="acme",
    )

    assert len(facts) == 1
    assert facts[0].kind == "layoff_event"
    assert "12" in facts[0].summary


def test_leadership_detection_normalizes_dict_input():
    facts = leadership.detect_leadership_changes(
        {"event": "new_cto", "person": "Jane", "effective": "2026-04-01", "source_url": "https://example.com/news/cto"},
        company_id="acme",
    )

    assert len(facts) == 1
    assert facts[0].kind == "leadership_change"
