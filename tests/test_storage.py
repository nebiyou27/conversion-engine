"""Storage layer contract tests.

Locks the append-only invariant and the epistemic-layering relationships:
evidence → claims → judgments → drafts → gate_reports.
"""
from __future__ import annotations

import inspect
import json
import sqlite3

import pytest

from storage import cache, db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.init(c)
    yield c
    c.close()


# --- Round-trip per layer ---

def test_evidence_roundtrip(conn):
    eid = db.insert_evidence(
        conn,
        company_id="acme",
        fact="Closed Series B on Apr 3",
        source_url="https://example.com/news",
        source_type="news",
        method="fixture",
        raw_payload={"amount": "50M"},
    )
    rows = db.get_evidence(conn, [eid])
    assert len(rows) == 1
    row = rows[0]
    assert row["company_id"] == "acme"
    assert row["fact"].startswith("Closed Series B")
    assert json.loads(row["raw_payload"]) == {"amount": "50M"}
    assert row["retrieved_at"]  # ISO timestamp present


def test_claim_roundtrip_references_evidence(conn):
    eid = db.insert_evidence(
        conn, company_id="acme", fact="hire spike", source_url="u",
        source_type="jobs", method="fixture",
    )
    cid = db.insert_claim(
        conn, company_id="acme", assertion="hiring surge",
        tier="corroborated", evidence_ids=[eid],
    )
    claim = db.get_claims(conn, [cid])[0]
    resolved = db.get_evidence(conn, json.loads(claim["evidence_ids"]))
    assert len(resolved) == 1
    assert resolved[0]["evidence_id"] == eid


def test_judgment_references_claims(conn):
    cid = db.insert_claim(
        conn, company_id="acme", assertion="a", tier="verified", evidence_ids=[],
    )
    jid = db.insert_judgment(
        conn, company_id="acme", kind="icp", value="segment_1",
        claim_ids=[cid], rationale="recent funding",
    )
    judgments = db.get_judgments(conn, "acme")
    assert len(judgments) == 1
    assert judgments[0]["judgment_id"] == jid
    assert json.loads(judgments[0]["claim_ids"]) == [cid]


def test_draft_and_gate_report(conn):
    cid = db.insert_claim(
        conn, company_id="acme", assertion="a", tier="verified", evidence_ids=[],
    )
    did = db.insert_draft(
        conn, company_id="acme", channel="email", path="commitment",
        subject="hello", body="body {cid}", claim_ids=[cid],
    )
    rid = db.insert_gate_report(
        conn, draft_id=did, citation_ok=True, shadow_ok=True,
        forbidden_ok=True, decision="pass",
    )
    report = db.get_gate_report_for_draft(conn, did)
    assert report["report_id"] == rid
    assert report["decision"] == "pass"


# --- Contract tests ---

def test_claim_rejects_invalid_tier(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_claim(
            conn, company_id="acme", assertion="x",
            tier="definitely_true",  # not in CHECK list
            evidence_ids=[],
        )


def test_gate_report_rejects_unknown_draft(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_gate_report(
            conn, draft_id="nonexistent", citation_ok=True,
            shadow_ok=True, forbidden_ok=True, decision="pass",
        )


def test_storage_exposes_no_mutators():
    """Append-only contract: no update/delete functions in the public API."""
    names = [n for n, _ in inspect.getmembers(db, inspect.isfunction)]
    forbidden = [n for n in names if n.startswith(("update_", "delete_", "remove_"))]
    assert forbidden == [], f"Mutator functions detected: {forbidden}"


# --- Cache ---

def test_cache_roundtrip(tmp_path):
    assert cache.get("crunchbase", "acme", cache_dir=tmp_path) is None
    cache.put("crunchbase", "acme", {"name": "Acme", "funded": True}, cache_dir=tmp_path)
    assert cache.get("crunchbase", "acme", cache_dir=tmp_path) == {"name": "Acme", "funded": True}


def test_cache_different_queries_isolated(tmp_path):
    cache.put("crunchbase", "acme", {"v": 1}, cache_dir=tmp_path)
    cache.put("crunchbase", "beta", {"v": 2}, cache_dir=tmp_path)
    assert cache.get("crunchbase", "acme", cache_dir=tmp_path) == {"v": 1}
    assert cache.get("crunchbase", "beta", cache_dir=tmp_path) == {"v": 2}
