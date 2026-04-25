"""Deterministic competitor-gap judgment.

This module compares a prospect's AI-maturity justifications with a static
sector peer benchmark. It does not read raw evidence rows and does not call an
LLM; all peer knowledge comes from curated fixture files.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.runtime import log_event
from storage import db

PEER_FIXTURE_DIR = Path("data") / "fixtures" / "peers"

PRACTICES: dict[str, dict[str, Any]] = {
    "named_ai_leadership": {
        "label": "Dedicated AI/ML leadership role publicly named",
        "segments": ["segment_1_series_a_b", "segment_3_leadership_transition"],
        "pitch": "Lead with a peer-benchmark question about who owns AI/ML execution as the company scales.",
    },
    "mlops_role_open": {
        "label": "Dedicated MLOps or ML-platform engineering role open",
        "segments": ["segment_4_specialized_capability"],
        "pitch": "Lead with the operating gap around turning AI intent into repeatable delivery infrastructure.",
    },
    "public_technical_commentary": {
        "label": "Public technical commentary on AI systems, agents, or evaluation",
        "segments": ["segment_1_series_a_b", "segment_4_specialized_capability"],
        "pitch": "Lead with a soft question about whether deeper technical AI work is happening privately.",
    },
    "modern_ml_stack": {
        "label": "Public signal of a modern ML stack or evaluation tooling",
        "segments": ["segment_4_specialized_capability"],
        "pitch": "Lead with the implementation gap: stack choices, evaluation, and MLOps practices.",
    },
}

SIGNAL_TO_PRACTICE = {
    "named_ai_ml_leadership": "named_ai_leadership",
    "ai_adjacent_open_roles": "mlops_role_open",
    "github_org_activity": "public_technical_commentary",
    "executive_commentary": "public_technical_commentary",
    "strategic_communications": "public_technical_commentary",
    "modern_data_ml_stack": "modern_ml_stack",
}

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
MISSING_STATUSES = {"absent", "unknown"}
SOPHISTICATED_SIGNALS = {"executive_commentary", "github_org_activity"}

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_peers(sector: str) -> list[dict[str, Any]] | None:
    if not sector.strip():
        return None
    path = PEER_FIXTURE_DIR / f"{sector.strip().lower()}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    peers = payload if isinstance(payload, list) else payload.get("peers", [])
    if not isinstance(peers, list) or not (5 <= len(peers) <= 10):
        return None
    return peers


def _top_quartile(peers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    ordered = sorted(peers, key=lambda p: int(p.get("ai_maturity_score", 0)), reverse=True)
    take = max(2, math.ceil(len(ordered) * 0.25))
    top = ordered[:take]
    benchmark = sum(int(p.get("ai_maturity_score", 0)) for p in top) / len(top)
    return top, round(benchmark, 2)


def _status_bucket(status: Any) -> str:
    text = str(status or "").strip().lower()
    return text if text in MISSING_STATUSES else "present"


def _prospect_practices(justifications: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_practice: dict[str, list[dict[str, Any]]] = {}
    for item in justifications:
        practice = SIGNAL_TO_PRACTICE.get(str(item.get("signal", "")))
        if practice:
            by_practice.setdefault(practice, []).append(item)

    out: dict[str, dict[str, Any]] = {}
    for practice in PRACTICES:
        items = by_practice.get(practice, [])
        present = [item for item in items if _status_bucket(item.get("status")) == "present"]
        chosen = present[0] if present else (items[0] if items else {})
        out[practice] = {
            "status": "present" if present else _status_bucket(chosen.get("status")),
            "raw_status": chosen.get("status", "unknown"),
            "confidence": str(chosen.get("confidence", "low")).lower(),
            "source_url": chosen.get("source_url"),
        }
    return out


def _peer_signal(peer: dict[str, Any], practice: str) -> dict[str, Any] | None:
    signal = peer.get("practice_signals", {}).get(practice)
    if not isinstance(signal, dict) or not signal.get("present"):
        return None
    return signal


def _competitor_entry(peer: dict[str, Any], top_domains: set[str]) -> dict[str, Any]:
    return {
        "name": peer["name"],
        "domain": peer["domain"],
        "ai_maturity_score": int(peer["ai_maturity_score"]),
        "ai_maturity_justification": list(peer.get("ai_maturity_justification", [])),
        "headcount_band": peer["headcount_band"],
        "top_quartile": peer["domain"] in top_domains,
        "sources_checked": list(peer.get("sources_checked", [])),
    }


def _confidence(peer_count: int, prospect: dict[str, Any]) -> str:
    prospect_conf = prospect.get("confidence", "low")
    if peer_count >= 3 and prospect["status"] == "absent" and prospect_conf in {"medium", "high"}:
        return "high"
    if peer_count == 2 or prospect_conf == "low":
        return "medium"
    return "low"


def _prospect_state(practice: str, prospect: dict[str, Any]) -> str:
    label = PRACTICES[practice]["label"]
    status = prospect.get("raw_status") or "unknown"
    if prospect["status"] == "absent":
        return f"Prospect AI-maturity justification reports no public signal for: {label}."
    return f"Prospect AI-maturity justification is unknown for: {label}; recorded status was {status!r}."


def _gap_candidates(
    top_peers: list[dict[str, Any]],
    prospect_practices: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for practice, prospect in prospect_practices.items():
        if prospect["status"] not in MISSING_STATUSES:
            continue

        evidence = []
        for peer in top_peers:
            signal = _peer_signal(peer, practice)
            if signal:
                evidence.append(
                    {
                        "competitor_name": peer["name"],
                        "evidence": signal.get("evidence", PRACTICES[practice]["label"]),
                        "source_url": signal.get("source_url"),
                    }
                )

        if len(evidence) < 2:
            continue

        confidence = _confidence(len(evidence), prospect)
        gaps.append(
            {
                "practice": PRACTICES[practice]["label"],
                "peer_evidence": evidence,
                "prospect_state": _prospect_state(practice, prospect),
                "confidence": confidence,
                "segment_relevance": PRACTICES[practice]["segments"],
                "_practice_key": practice,
                "_peer_count": len(evidence),
            }
        )

    gaps.sort(key=lambda g: (CONFIDENCE_RANK[g["confidence"]], g["_peer_count"]), reverse=True)
    return gaps[:3]


def _pitch_shift(gaps: list[dict[str, Any]]) -> str:
    top = gaps[0]
    practice = top.pop("_practice_key")
    top.pop("_peer_count", None)
    confidence = top["confidence"]
    mode = "frame it as a measured gap" if confidence == "high" else "frame it as a question, not an assertion"
    return f"{PRACTICES[practice]['pitch']} Confidence is {confidence}; {mode}."


def _consulted_claim_ids(conn: sqlite3.Connection, company_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT claim_id FROM claims WHERE company_id = ? ORDER BY built_at, claim_id",
        (company_id,),
    ).fetchall()
    return [str(row["claim_id"]) for row in rows]


def _silent_but_sophisticated(
    justifications: list[dict[str, Any]],
    ai_maturity_score: int,
) -> bool:
    if ai_maturity_score > 1:
        return False
    for item in justifications:
        if item.get("signal") in SOPHISTICATED_SIGNALS and _status_bucket(item.get("status")) == "present":
            return str(item.get("confidence", "")).lower() in {"medium", "high"}
    return False


def judge(
    conn: sqlite3.Connection,
    company_id: str,
    *,
    prospect_domain: str = "",
    prospect_sector: str = "",
    ai_maturity_score: int = 0,
    ai_maturity_justifications: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return a schema-shaped competitor gap brief, or None when peer data is sparse."""
    peers = _load_peers(prospect_sector)
    if peers is None:
        log_event(
            logger,
            logging.INFO,
            "competitor_gap_abstain",
            company_id=company_id,
            prospect_sector=prospect_sector,
            reason="missing_or_invalid_peer_fixture",
        )
        return None

    top_peers, benchmark = _top_quartile(peers)
    top_domains = {str(peer["domain"]) for peer in top_peers}
    prospect = _prospect_practices(ai_maturity_justifications or [])
    gaps = _gap_candidates(top_peers, prospect)
    if not gaps:
        log_event(
            logger,
            logging.INFO,
            "competitor_gap_abstain",
            company_id=company_id,
            prospect_sector=prospect_sector,
            reason="no_schema_valid_gap_findings",
        )
        return None

    all_sources_present = all(
        bool(item.get("source_url"))
        for gap in gaps
        for item in gap["peer_evidence"]
    )
    pitch = _pitch_shift(gaps)
    public_gaps = [
        {k: v for k, v in gap.items() if not k.startswith("_")}
        for gap in gaps
    ]

    brief: dict[str, Any] = {
        "prospect_domain": prospect_domain,
        "prospect_sector": prospect_sector,
        "generated_at": _now_iso(),
        "prospect_ai_maturity_score": int(ai_maturity_score),
        "sector_top_quartile_benchmark": benchmark,
        "competitors_analyzed": [_competitor_entry(peer, top_domains) for peer in peers],
        "gap_findings": public_gaps,
        "suggested_pitch_shift": pitch,
        "gap_quality_self_check": {
            "all_peer_evidence_has_source_url": all_sources_present,
            "at_least_one_gap_high_confidence": any(g["confidence"] == "high" for g in public_gaps),
            "prospect_silent_but_sophisticated_risk": _silent_but_sophisticated(
                ai_maturity_justifications or [],
                int(ai_maturity_score),
            ),
        },
    }

    judgment_id = db.insert_judgment(
        conn,
        company_id=company_id,
        kind="competitor_gap",
        value=str(benchmark),
        claim_ids=_consulted_claim_ids(conn, company_id),
        rationale=json.dumps(public_gaps, sort_keys=True),
    )

    return {**brief, "judgment_id": judgment_id}
