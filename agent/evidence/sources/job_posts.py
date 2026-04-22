"""Job-board fixture loader. Emits one Fact per posting."""
from __future__ import annotations

from datetime import datetime, timezone

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
