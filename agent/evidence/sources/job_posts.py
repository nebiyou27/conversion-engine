"""Job-board fixture loader. Emits one Fact per posting."""
from __future__ import annotations

from html import unescape
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
import re

from agent.evidence.schema import EvidenceFormatError, Fact


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


def scrape_job_posts(
    url: str,
    *,
    company_id: str,
    page: Any | None = None,
    playwright: Any | None = None,
    max_posts: int = 25,
) -> list[Fact]:
    """Scrape a public jobs page using Playwright with no login or captcha bypass."""
    if page is None:
        if playwright is None:
            from playwright.sync_api import sync_playwright
            playwright = sync_playwright()

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
