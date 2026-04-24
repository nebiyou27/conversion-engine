"""Job-board fixture loader. Emits one Fact per posting.

Compliance notes:
  - Public job listings only. No login, no session cookies, no CAPTCHA bypass.
  - Before adding a new domain, verify robots.txt allows unauthenticated read
    of the public careers / jobs path.
  - As of 2026-04, BuiltIn, Wellfound, and LinkedIn public /jobs pages permit
    read access; we scrape only the rendered page DOM, never private profiles.
  - Failed loads abstain silently rather than retrying aggressively.
"""
from __future__ import annotations

from html import unescape
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any
import json
import re
from urllib.parse import quote_plus

from agent.evidence.schema import EvidenceFormatError, Fact

SUPPORTED_DOMAINS = ["builtin.com", "wellfound.com", "linkedin.com/jobs"]
JOB_VELOCITY_WINDOW_DAYS = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(section, *, company_id: str) -> list[Fact]:
    if section is None:
        return []
    if not isinstance(section, list):
        raise EvidenceFormatError(
            f"job_posts section must be a list, got {type(section).__name__}"
        )

    facts: list[Fact] = []
    for i, item in enumerate(section):
        if not isinstance(item, dict):
            raise EvidenceFormatError(f"job_posts[{i}] must be a dict")
        required = ("title", "posted_on", "source_url")
        missing = [k for k in required if k not in item]
        if missing:
            raise EvidenceFormatError(f"job_posts[{i}] missing: {missing}")

        title = item["title"]
        posted_on = item["posted_on"]
        facts.append(Fact(
            company_id=company_id,
            source_type="job_posts",
            kind="job_posting",
            summary=f"Posted '{title}' on {posted_on}",
            payload={"title": title, "posted_on": posted_on},
            source_url=item["source_url"],
            retrieved_at=item.get("retrieved_at") or _now(),
        ))
    return facts


class _JobPostAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_anchor = False
        self.current_href = ""
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = ""
        for key, value in attrs:
            if key.lower() == "href" and value:
                href = value
                break
        self.in_anchor = True
        self.current_href = href
        self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.in_anchor:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self.in_anchor:
            return
        text = unescape("".join(self.current_text)).strip()
        if text:
            self.links.append((self.current_href, text))
        self.in_anchor = False
        self.current_href = ""
        self.current_text = []


def extract_job_posts_from_html(
    html: str,
    *,
    company_id: str,
    source_url: str,
    max_posts: int = 25,
) -> list[Fact]:
    """Parse job-post listings from rendered HTML."""
    parser = _JobPostAnchorParser()
    parser.feed(html)

    facts: list[Fact] = []
    for href, text in parser.links:
        if len(facts) >= max_posts:
            break
        if not text or len(text) < 3:
            continue
        if not re.search(r"(job|career|role|engineer|data|ml|backend|frontend)", text, re.I):
            continue
        facts.append(Fact(
            company_id=company_id,
            source_type="job_posts",
            kind="job_posting",
            summary=f"Posted '{text}' on {source_url}",
            payload={"title": text, "posted_on": source_url, "listing_url": href or source_url},
            source_url=href or source_url,
            retrieved_at=_now(),
            method="playwright",
        ))
    return facts


def _safe_scrape(url: str, *, company_id: str, playwright_factory: Any | None, max_posts: int) -> list[Fact]:
    try:
        return scrape_job_posts(
            url,
            company_id=company_id,
            playwright_factory=playwright_factory,
            max_posts=max_posts,
        )
    except Exception:
        return []


def scrape_builtin(
    company_slug: str,
    *,
    company_id: str | None = None,
    playwright_factory: Any | None = None,
    max_posts: int = 25,
) -> list[Fact]:
    """Scrape a company's public BuiltIn jobs page."""
    resolved_company_id = company_id or company_slug
    url = f"https://builtin.com/company/{quote_plus(company_slug)}/jobs"
    return _safe_scrape(url, company_id=resolved_company_id, playwright_factory=playwright_factory, max_posts=max_posts)


def scrape_wellfound(
    company_slug: str,
    *,
    company_id: str | None = None,
    playwright_factory: Any | None = None,
    max_posts: int = 25,
) -> list[Fact]:
    """Scrape a company's public Wellfound jobs page."""
    resolved_company_id = company_id or company_slug
    url = f"https://wellfound.com/company/{quote_plus(company_slug)}/jobs"
    return _safe_scrape(url, company_id=resolved_company_id, playwright_factory=playwright_factory, max_posts=max_posts)


def scrape_linkedin_public(
    company_slug: str,
    *,
    company_id: str | None = None,
    playwright_factory: Any | None = None,
    max_posts: int = 25,
) -> list[Fact]:
    """Scrape public LinkedIn jobs search results for a company."""
    resolved_company_id = company_id or company_slug
    url = f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(company_slug)}"
    return _safe_scrape(url, company_id=resolved_company_id, playwright_factory=playwright_factory, max_posts=max_posts)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_60d_velocity(facts: list[Fact], *, now: datetime | None = None) -> dict:
    """Job-post count delta: postings in last 60 days vs. prior 60-day window.

    Returns {window_days: 60, curr_count, prior_count, delta_pct}.
    """
    now = now or datetime.now(timezone.utc)
    curr_start = now - timedelta(days=JOB_VELOCITY_WINDOW_DAYS)
    prior_start = now - timedelta(days=JOB_VELOCITY_WINDOW_DAYS * 2)

    curr_urls: set[str] = set()
    prior_urls: set[str] = set()
    for fact in facts:
        if fact.source_type != "job_posts":
            continue
        posted_at = _parse_datetime(str(fact.payload.get("posted_on") or ""))
        if posted_at is None:
            continue
        if posted_at >= curr_start:
            curr_urls.add(fact.source_url)
        elif prior_start <= posted_at < curr_start:
            prior_urls.add(fact.source_url)

    curr_count = len(curr_urls)
    prior_count = len(prior_urls)
    if prior_count == 0:
        delta_pct = None if curr_count == 0 else 100.0
    else:
        delta_pct = ((curr_count - prior_count) / prior_count) * 100.0
    return {
        "window_days": JOB_VELOCITY_WINDOW_DAYS,
        "curr_count": curr_count,
        "prior_count": prior_count,
        "delta_pct": delta_pct,
    }


def compute_60d_velocity_from_rows(rows: list[dict], *, now: datetime | None = None) -> dict:
    facts: list[Fact] = []
    for row in rows:
        payload_raw = row.get("raw_payload")
        payload = {}
        if payload_raw:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
        facts.append(Fact(
            company_id=row.get("company_id", ""),
            source_type=row.get("source_type", ""),
            kind=payload.get("kind", "job_posting"),
            summary=row.get("fact", ""),
            payload=payload,
            source_url=row.get("source_url", ""),
            retrieved_at=row.get("retrieved_at") or _now(),
            method=row.get("method", "fixture"),
        ))
    return compute_60d_velocity(facts, now=now)


def scrape_job_posts(
    url: str,
    *,
    company_id: str,
    page: Any | None = None,
    playwright: Any | None = None,
    playwright_factory: Any | None = None,
    max_posts: int = 25,
) -> list[Fact]:
    """Scrape a public jobs page using Playwright with no login or captcha bypass."""
    if page is None:
        if playwright is None:
            playwright = (playwright_factory or _sync_playwright_factory)()

        with playwright as p:
            browser = p.chromium.launch(headless=True)
            try:
                page_obj = browser.new_page()
                page_obj.goto(url, wait_until="networkidle")
                html = page_obj.content()
            finally:
                browser.close()
    else:
        if hasattr(page, "goto"):
            page.goto(url, wait_until="networkidle")
        html = page.content()

    return extract_job_posts_from_html(
        html,
        company_id=company_id,
        source_url=url,
        max_posts=max_posts,
    )


def load_live_job_posts(
    url: str,
    *,
    company_id: str,
    max_posts: int = 25,
    playwright_factory: Any | None = None,
) -> list[Fact]:
    """Live-facing alias for Playwright-based job-post scraping."""
    return scrape_job_posts(
        url,
        company_id=company_id,
        playwright_factory=playwright_factory,
        max_posts=max_posts,
    )


def _sync_playwright_factory():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("playwright package is not installed") from exc

    return sync_playwright()
