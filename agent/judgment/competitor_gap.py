"""Competitor gap judgment — schema-valid stub.

Full logic deferred to Phase 6. This stub returns the shape defined by
``schemas/competitor_gap_brief.schema.json`` with empty/default values so
downstream code can depend on the type contract without crashing.

The stub is honest: gap_findings is empty, quality self-check flags are
all False, and suggested_pitch_shift says 'stub — no gap analysis performed.'
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from storage import db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def judge(
    conn: sqlite3.Connection,
    company_id: str,
    *,
    prospect_domain: str = "",
    prospect_sector: str = "",
    ai_maturity_score: int = 0,
) -> dict[str, Any]:
    """Return a schema-valid but empty competitor gap brief.

    Parameters
    ----------
    conn : sqlite3.Connection
        DB connection (used to persist judgment row).
    company_id : str
        Target company.
    prospect_domain : str
        Prospect domain for the brief.
    prospect_sector : str
        Sector classification.
    ai_maturity_score : int
        AI maturity score (0–3).

    Returns
    -------
    dict matching competitor_gap_brief.schema.json with stub values.
    """
    brief: dict[str, Any] = {
        "prospect_domain": prospect_domain,
        "prospect_sector": prospect_sector,
        "generated_at": _now_iso(),
        "prospect_ai_maturity_score": ai_maturity_score,
        "sector_top_quartile_benchmark": 0.0,
        "competitors_analyzed": [],
        "gap_findings": [],
        "suggested_pitch_shift": "stub — no gap analysis performed",
        "gap_quality_self_check": {
            "all_peer_evidence_has_source_url": False,
            "at_least_one_gap_high_confidence": False,
            "prospect_silent_but_sophisticated_risk": False,
        },
    }

    # Persist a judgment row for audit trail
    judgment_id = db.insert_judgment(
        conn,
        company_id=company_id,
        kind="competitor_gap",
        value="stub",
        claim_ids=[],
        rationale="Phase 5 stub — full gap analysis deferred to Phase 6",
    )

    return {**brief, "judgment_id": judgment_id}
