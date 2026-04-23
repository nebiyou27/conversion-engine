"""Claim builder. Group a company's evidence by claim kind, compute tier,
render a deterministic assertion, and write rows to the claims table.

Below-threshold claims are persisted (audit trail) but downstream layers
filter them out. A kind with zero matching evidence emits no row at all.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from agent.claims import confidence, tiers
from storage import db


def _payload(row: dict) -> dict:
    raw = row.get("raw_payload")
    if not raw:
        return {}
    return json.loads(raw) if isinstance(raw, str) else raw


def _meets_surge_threshold(rows: list[dict], now: datetime) -> bool:
    cutoff = now - timedelta(days=tiers.HIRING_SURGE_WINDOW_DAYS)
    urls: set[str] = set()
    for r in rows:
        if r["source_type"] != "job_posts":
            continue
        posted_on = _payload(r).get("posted_on")
        if not posted_on:
            continue
        dt = datetime.fromisoformat(posted_on)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff:
            urls.add(r["source_url"])
    return len(urls) >= tiers.HIRING_SURGE_MIN_POSTINGS


def _build_payload(kind: str, rows: list[dict]) -> dict:
    """Structured fields the judgment layer filters on. Populated from primary rows only.

    The judgment layer reads claim.payload instead of the linked evidence rows, so R2
    (judgment never reads raw evidence) holds even when structured attributes are needed.
    """
    primary_types = tiers.PRIMARY[kind]
    primaries = [r for r in rows if r["source_type"] in primary_types]

    if kind == "funding_round":
        for r in primaries:
            p = _payload(r)
            return {
                "round": p.get("round"),
                "amount_usd": p.get("amount_usd"),
                "announced_on": p.get("announced_on"),
            }
    if kind == "hiring_surge":
        postings = [_payload(r) for r in primaries]
        return {
            "postings_count": len({r["source_url"] for r in primaries}),
            "titles": [p.get("title") for p in postings if p.get("title")],
        }
    if kind == "leadership_change":
        for r in primaries:
            p = _payload(r)
            return {
                "event": p.get("event"),
                "person": p.get("person"),
                "effective": p.get("effective"),
            }
    if kind == "layoff_event":
        for r in primaries:
            p = _payload(r)
            return {
                "headcount_cut": p.get("headcount"),
                "event_on": p.get("event_on"),
            }
    if kind == "company_metadata":
        for r in primaries:
            p = _payload(r)
            out = {"headcount": p.get("headcount")}
            if "hq_country" in p:
                out["hq_country"] = p["hq_country"]
            if "founded_year" in p:
                out["founded_year"] = p["founded_year"]
            return out
    return {}


def _render_assertion(kind: str, rows: list[dict]) -> str:
    if kind == "funding_round":
        for r in rows:
            if r["source_type"] == "crunchbase":
                p = _payload(r)
                return (
                    f"Raised {p['round']} (${p['amount_usd'] / 1_000_000:.0f}M) "
                    f"on {p['announced_on']}"
                )
    if kind == "hiring_surge":
        n = len({r["source_url"] for r in rows if r["source_type"] == "job_posts"})
        return f"Hiring surge: {n} distinct postings within {tiers.HIRING_SURGE_WINDOW_DAYS} days"
    if kind == "leadership_change":
        for r in rows:
            if r["source_type"] == "leadership":
                p = _payload(r)
                return f"{p['event']}: {p['person']}, effective {p['effective']}"
    if kind == "layoff_event":
        for r in rows:
            if r["source_type"] == "layoffs":
                p = _payload(r)
                return f"Laid off {p['headcount']} on {p['event_on']}"
    if kind == "company_metadata":
        for r in rows:
            if r["source_type"] == "company_metadata":
                p = _payload(r)
                parts = [f"Headcount: {p['headcount']}"]
                if "hq_country" in p:
                    parts.append(f"HQ: {p['hq_country']}")
                if "founded_year" in p:
                    parts.append(f"founded {p['founded_year']}")
                return ", ".join(parts)
    return f"{kind} signal"


def build(
    conn: sqlite3.Connection,
    company_id: str,
    *,
    now: datetime | None = None,
) -> list[str]:
    now = now or datetime.now(timezone.utc)

    rows = [
        dict(r) for r in conn.execute(
            "SELECT * FROM evidence WHERE company_id = ?", (company_id,)
        ).fetchall()
    ]

    claim_ids: list[str] = []
    for kind in tiers.CLAIM_KINDS:
        relevant_types = tiers.PRIMARY[kind] | tiers.SECONDARY[kind]
        relevant = [r for r in rows if r["source_type"] in relevant_types]
        if not relevant:
            continue

        if kind == "hiring_surge" and not _meets_surge_threshold(relevant, now):
            continue

        tier = confidence.compute_tier(relevant, claim_kind=kind, now=now)
        cid = db.insert_claim(
            conn,
            company_id=company_id,
            kind=kind,
            assertion=_render_assertion(kind, relevant),
            tier=tier,
            evidence_ids=[r["evidence_id"] for r in relevant],
            payload=_build_payload(kind, relevant),
        )
        claim_ids.append(cid)
    return claim_ids
