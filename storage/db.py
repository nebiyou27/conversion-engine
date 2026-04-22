"""Storage API. One insert + one read per epistemic layer.

Append-only is enforced by the absence of update/delete functions. Do not add them.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path("data") / "conversion.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _uid() -> str:
    return str(uuid.uuid4())


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open (and create if missing) the SQLite database. Enables FK enforcement."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


# --- Layer 1: Evidence ---

def insert_evidence(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    fact: str,
    source_url: str,
    source_type: str,
    method: str,
    raw_payload: dict | None = None,
    retrieved_at: str | None = None,
) -> str:
    evidence_id = _uid()
    conn.execute(
        "INSERT INTO evidence (evidence_id, company_id, fact, source_url, "
        "source_type, retrieved_at, method, raw_payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            evidence_id,
            company_id,
            fact,
            source_url,
            source_type,
            retrieved_at or _now(),
            method,
            json.dumps(raw_payload) if raw_payload is not None else None,
        ),
    )
    conn.commit()
    return evidence_id


def get_evidence(conn: sqlite3.Connection, evidence_ids: list[str]) -> list[dict]:
    if not evidence_ids:
        return []
    placeholders = ",".join("?" for _ in evidence_ids)
    rows = conn.execute(
        f"SELECT * FROM evidence WHERE evidence_id IN ({placeholders})",
        evidence_ids,
    ).fetchall()
    return [dict(r) for r in rows]


# --- Layer 2: Claims ---

def insert_claim(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    assertion: str,
    tier: str,
    evidence_ids: list[str],
) -> str:
    claim_id = _uid()
    conn.execute(
        "INSERT INTO claims (claim_id, company_id, assertion, tier, built_at, evidence_ids) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (claim_id, company_id, assertion, tier, _now(), json.dumps(evidence_ids)),
    )
    conn.commit()
    return claim_id


def get_claims(conn: sqlite3.Connection, claim_ids: list[str]) -> list[dict]:
    if not claim_ids:
        return []
    placeholders = ",".join("?" for _ in claim_ids)
    rows = conn.execute(
        f"SELECT * FROM claims WHERE claim_id IN ({placeholders})",
        claim_ids,
    ).fetchall()
    return [dict(r) for r in rows]


# --- Layer 3: Judgment ---

def insert_judgment(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    kind: str,
    value: str,
    claim_ids: list[str],
    rationale: str | None = None,
) -> str:
    judgment_id = _uid()
    conn.execute(
        "INSERT INTO judgments (judgment_id, company_id, kind, value, rationale, "
        "claim_ids, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (judgment_id, company_id, kind, value, rationale, json.dumps(claim_ids), _now()),
    )
    conn.commit()
    return judgment_id


def get_judgments(conn: sqlite3.Connection, company_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM judgments WHERE company_id = ?", (company_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- Layer 4: Actions (drafts) ---

def insert_draft(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    channel: str,
    path: str,
    body: str,
    claim_ids: list[str],
    contact_id: str | None = None,
    subject: str | None = None,
) -> str:
    draft_id = _uid()
    conn.execute(
        "INSERT INTO drafts (draft_id, company_id, contact_id, channel, path, "
        "subject, body, claim_ids, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (draft_id, company_id, contact_id, channel, path, subject, body,
         json.dumps(claim_ids), _now()),
    )
    conn.commit()
    return draft_id


def get_draft(conn: sqlite3.Connection, draft_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)
    ).fetchone()
    return dict(row) if row else None


# --- Layer 5: Gate ---

def insert_gate_report(
    conn: sqlite3.Connection,
    *,
    draft_id: str,
    citation_ok: bool,
    shadow_ok: bool,
    forbidden_ok: bool,
    decision: str,
    failures: list[dict] | None = None,
) -> str:
    report_id = _uid()
    conn.execute(
        "INSERT INTO gate_reports (report_id, draft_id, citation_ok, shadow_ok, "
        "forbidden_ok, failures, decision, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            report_id, draft_id, int(citation_ok), int(shadow_ok), int(forbidden_ok),
            json.dumps(failures) if failures is not None else None,
            decision, _now(),
        ),
    )
    conn.commit()
    return report_id


def get_gate_report_for_draft(conn: sqlite3.Connection, draft_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM gate_reports WHERE draft_id = ? ORDER BY created_at DESC LIMIT 1",
        (draft_id,),
    ).fetchone()
    return dict(row) if row else None
