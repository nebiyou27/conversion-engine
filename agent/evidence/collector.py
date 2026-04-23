"""Evidence collector — dispatches fixture sections to per-source loaders and writes rows.

Thin by design: no interpretation, no scoring, no filtering. Evidence layer is raw facts only.
"""
from __future__ import annotations

import sqlite3

from agent.evidence.sources import (
    company_metadata,
    crunchbase,
    job_posts,
    layoffs,
    leadership,
)
from storage import db

_LOADERS = {
    "crunchbase":       crunchbase.load,
    "job_posts":        job_posts.load,
    "layoffs":          layoffs.load,
    "leadership":       leadership.load,
    "company_metadata": company_metadata.load,
}


def collect(fixture: dict, conn: sqlite3.Connection) -> list[str]:
    """Load every source section of `fixture` and append evidence rows to the DB.

    Returns the list of evidence_ids written. Keys in `sources` starting with `_` are skipped
    (reserved for provenance notes). Sections missing entirely → 0 rows. Malformed → raise.
    """
    company_id = fixture["company_id"]
    sections = {
        k: v for k, v in fixture.get("sources", {}).items()
        if not k.startswith("_")
    }

    facts = []
    for source_name, loader in _LOADERS.items():
        facts.extend(loader(sections.get(source_name), company_id=company_id))

    ids: list[str] = []
    for f in facts:
        eid = db.insert_evidence(
            conn,
            company_id=f.company_id,
            fact=f.summary,
            source_url=f.source_url,
            source_type=f.source_type,
            method=f.method,
            raw_payload={**f.payload, "kind": f.kind},
            retrieved_at=f.retrieved_at,
        )
        ids.append(eid)
    return ids
