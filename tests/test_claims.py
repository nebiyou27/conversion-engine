"""Claims layer contract tests.

Locks tier computation (pure function) + builder end-to-end behavior.
Tier is the single lever controlling downstream sentence mood; these tests
are the regression suite for over-claiming prevention.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.claims import builder, confidence, tiers
from agent.evidence import collector
from storage import db

NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
SHADOW_FIXTURE_PATH = Path("data/fixtures/companies/shadow_startup.json")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.init(c)
    yield c
    c.close()


def _ev(source_type: str, source_url: str, event_key: str, event_date: str) -> dict:
    """Synthetic evidence row matching the DB row shape returned by conn.execute."""
    return {
        "evidence_id": f"e-{source_url}",
        "company_id": "test",
        "fact": "stub",
        "source_type": source_type,
        "source_url": source_url,
        "retrieved_at": NOW.isoformat(),
        "method": "fixture",
        "raw_payload": json.dumps({event_key: event_date, "kind": "x"}),
    }


def _actionable_claims(claims: list[dict]) -> list[dict]:
    return [c for c in claims if c["tier"] != tiers.BELOW_THRESHOLD]


# --- Pure tier logic ---

def test_tier_verified_two_primaries_recent():
    rows = [
        _ev("crunchbase", "https://a", "announced_on", "2026-04-20"),
        _ev("crunchbase", "https://b", "announced_on", "2026-04-19"),
    ]
    assert confidence.compute_tier(rows, claim_kind="funding_round", now=NOW) == "verified"


def test_tier_corroborated_primary_plus_secondary():
    rows = [
        _ev("crunchbase", "https://a", "announced_on", "2026-04-20"),
        _ev("job_posts", "https://b", "posted_on", "2026-04-18"),
    ]
    assert confidence.compute_tier(rows, claim_kind="funding_round", now=NOW) == "corroborated"


def test_tier_verified_downgrades_to_corroborated_on_age():
    # Two primaries but age > 7d — loses verified status, still corroborated under lenient rule.
    rows = [
        _ev("crunchbase", "https://a", "announced_on", "2026-04-12"),  # 10 days old
        _ev("crunchbase", "https://b", "announced_on", "2026-04-10"),
    ]
    assert confidence.compute_tier(rows, claim_kind="funding_round", now=NOW) == "corroborated"


def test_tier_inferred_secondary_only():
    rows = [
        _ev("job_posts", "https://a", "posted_on", "2026-04-20"),
        _ev("job_posts", "https://b", "posted_on", "2026-04-18"),
    ]
    assert confidence.compute_tier(rows, claim_kind="funding_round", now=NOW) == "inferred"


def test_tier_below_threshold_empty():
    assert confidence.compute_tier([], claim_kind="funding_round", now=NOW) == "below_threshold"


def test_tier_below_threshold_stale_past_30d():
    rows = [
        _ev("crunchbase", "https://a", "announced_on", "2026-02-01"),
        _ev("crunchbase", "https://b", "announced_on", "2026-01-15"),
    ]
    assert confidence.compute_tier(rows, claim_kind="funding_round", now=NOW) == "below_threshold"


def test_tier_single_primary_within_7d_is_inferred():
    # One primary, no secondary, ≤7d → honest uncertainty posture.
    rows = [_ev("leadership", "https://a", "effective", "2026-04-20")]
    assert confidence.compute_tier(rows, claim_kind="leadership_change", now=NOW) == "inferred"


def test_tier_single_primary_past_7d_falls_to_below_threshold():
    rows = [_ev("leadership", "https://a", "effective", "2026-04-10")]  # 12 days
    assert confidence.compute_tier(rows, claim_kind="leadership_change", now=NOW) == "below_threshold"


def test_independence_same_source_url_counts_once():
    rows = [
        _ev("crunchbase", "https://a", "announced_on", "2026-04-20"),
        _ev("crunchbase", "https://a", "announced_on", "2026-04-19"),
    ]
    # Same URL → counts as 1 primary → single-primary-within-7d → inferred (not verified).
    assert confidence.compute_tier(rows, claim_kind="funding_round", now=NOW) == "inferred"


# --- Builder end-to-end ---


def test_builder_on_shadow_startup_fixture_emits_zero_actionable_claims(conn):
    fixture = json.loads(SHADOW_FIXTURE_PATH.read_text(encoding="utf-8"))
    collector.collect(fixture, conn)
    ids = builder.build(conn, fixture["company_id"], now=NOW)
    claims = db.get_claims(conn, ids)

    assert len(claims) == 2
    assert not _actionable_claims(claims)
    assert {c["kind"] for c in claims} == {"funding_round", "leadership_change"}
    assert all(c["tier"] == tiers.BELOW_THRESHOLD for c in claims)


def test_builder_shadow_startup_fixture_skips_under_threshold_hiring_surge(conn):
    fixture = json.loads(SHADOW_FIXTURE_PATH.read_text(encoding="utf-8"))
    collector.collect(fixture, conn)
    ids = builder.build(conn, fixture["company_id"], now=NOW)
    claims = db.get_claims(conn, ids)

    assert all(c["kind"] != "hiring_surge" for c in claims)
    assert len(_actionable_claims(claims)) == 0

def test_builder_on_acme_fixture_emits_expected_tiers(conn):
    fixture = json.loads(
        Path("data/fixtures/companies/acme_series_b.json").read_text(encoding="utf-8")
    )
    collector.collect(fixture, conn)
    ids = builder.build(conn, "acme", now=NOW)
    claims = db.get_claims(conn, ids)
    by_kind = {c["kind"]: c for c in claims}

    # funding_round: 1 crunchbase (04-18, 4d) + 3 job_posts → corroborated
    assert by_kind["funding_round"]["tier"] == "corroborated"
    assert "Series B" in by_kind["funding_round"]["assertion"]
    # hiring_surge: 3 distinct job_posts within 30d, most recent 04-15 (7d) → verified
    assert by_kind["hiring_surge"]["tier"] == "verified"
    # leadership_change: 1 leadership row, effective 2026-03-15 (38d) → below_threshold persisted
    assert by_kind["leadership_change"]["tier"] == "below_threshold"
    # layoff_event: no evidence → not emitted
    assert "layoff_event" not in by_kind


def test_builder_hiring_surge_below_postings_threshold_not_emitted(conn):
    for url in ("https://j1", "https://j2"):
        db.insert_evidence(
            conn, company_id="acme", fact="job", source_url=url,
            source_type="job_posts", method="fixture",
            raw_payload={"title": "Eng", "posted_on": "2026-04-15", "kind": "job_posting"},
        )
    ids = builder.build(conn, "acme", now=NOW)
    claims = db.get_claims(conn, ids)
    assert not any(c["kind"] == "hiring_surge" for c in claims)


def test_builder_persists_below_threshold_claim(conn):
    # Stale primary only → builder emits a below_threshold row (audit trail).
    db.insert_evidence(
        conn, company_id="acme", fact="old round", source_url="https://c1",
        source_type="crunchbase", method="fixture",
        raw_payload={
            "round": "A", "amount_usd": 10_000_000,
            "announced_on": "2026-01-01", "kind": "funding_round",
        },
    )
    ids = builder.build(conn, "acme", now=NOW)
    claims = db.get_claims(conn, ids)
    assert any(c["tier"] == "below_threshold" for c in claims)


def test_claims_kind_check_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_claim(
            conn, company_id="acme", kind="not_a_real_kind",
            assertion="x", tier="verified", evidence_ids=[],
        )
