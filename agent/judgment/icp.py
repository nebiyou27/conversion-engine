"""ICP judgment — thin wrapper that orchestrates segment + AI maturity into
the ``primary_segment_match`` / ``segment_confidence`` shape required by the
hiring_signal_brief schema.

This module is the single entry-point the actions layer calls. It:
  1. Runs segment.classify (deterministic)
  2. Persists the judgment row via storage.db
  3. Returns the schema-shaped dict

It does NOT interpret claims itself (R2 — judgment reads claims, not evidence).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from agent.judgment import segment
from storage import db


def judge(
    conn: sqlite3.Connection,
    company_id: str,
    *,
    now: datetime | None = None,
    ai_maturity_score: int | None = None,
) -> dict[str, Any]:
    """Produce the ICP judgment for a company.

    Parameters
    ----------
    conn : sqlite3.Connection
        DB connection with claims already written.
    company_id : str
        Target company.
    now : datetime, optional
        Override for deterministic testing.
    ai_maturity_score : int | None
        AI maturity score (0–3) from ai_maturity.judge(). Pass None if not
        yet scored — S4 will be skipped.

    Returns
    -------
    dict matching hiring_signal_brief schema subset:
        primary_segment_match : str
        segment_confidence : float
        rationale : str
        claim_ids : list[str]
        judgment_id : str — the persisted judgment row ID
    """
    now = now or datetime.now(timezone.utc)

    # Fetch all claims for the company
    rows = conn.execute(
        "SELECT * FROM claims WHERE company_id = ?", (company_id,)
    ).fetchall()
    claims = [dict(r) for r in rows]

    result = segment.classify(claims, now=now, ai_maturity_score=ai_maturity_score)

    # Persist the judgment
    judgment_id = db.insert_judgment(
        conn,
        company_id=company_id,
        kind="segment",
        value=result["primary_segment_match"],
        claim_ids=result["claim_ids"],
        rationale=result["rationale"],
    )

    return {**result, "judgment_id": judgment_id}
