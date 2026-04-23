"""Evidence layer contract tests.

Locks loader granularity, fail-loud-on-malformed + clean-on-absent semantics,
source_url audit trail, and end-to-end collector round-trip.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.evidence import collector
from agent.evidence.schema import EvidenceFormatError, Fact
from agent.evidence.sources import crunchbase, job_posts, layoffs, leadership
from storage import db

FIXTURE_PATH = Path("data/fixtures/companies/acme_series_b.json")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.init(c)
    yield c
    c.close()


@pytest.fixture
def acme_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# --- Loader granularity ---

def test_crunchbase_loader_emits_one_fact_per_round(acme_fixture):
    facts = crunchbase.load(acme_fixture["sources"]["crunchbase"], company_id="acme")
    assert len(facts) == 1
    assert facts[0].source_type == "crunchbase"
    assert facts[0].kind == "funding_round"
    assert "Series B" in facts[0].summary


def test_job_posts_loader_emits_one_fact_per_posting(acme_fixture):
    facts = job_posts.load(acme_fixture["sources"]["job_posts"], company_id="acme")
    assert len(facts) == 3
    assert all(f.source_type == "job_posts" for f in facts)
    assert all(f.kind == "job_posting" for f in facts)


def test_layoffs_empty_list_returns_empty(acme_fixture):
    # Fixture has layoffs: [] — critical path: 'present but empty' must yield 0 facts cleanly.
    facts = layoffs.load(acme_fixture["sources"]["layoffs"], company_id="acme")
    assert facts == []


# --- Absent vs malformed input ---

@pytest.mark.parametrize("loader", [crunchbase.load, job_posts.load, layoffs.load, leadership.load])
def test_loader_missing_section_returns_empty(loader):
    assert loader(None, company_id="acme") == []


@pytest.mark.parametrize("loader,bad", [
    (crunchbase.load, "not a dict"),
    (job_posts.load, {"not": "a list"}),
    (layoffs.load, "string instead of list"),
    (leadership.load, 42),
])
def test_loader_wrong_type_raises(loader, bad):
    with pytest.raises(EvidenceFormatError):
        loader(bad, company_id="acme")


def test_crunchbase_malformed_amount_raises():
    bad = {"funding_round": {
        "round": "Series B", "amount_usd": "50M",
        "announced_on": "2026-04-18", "source_url": "https://x",
    }}
    with pytest.raises(EvidenceFormatError):
        crunchbase.load(bad, company_id="acme")


def test_job_posts_missing_field_raises():
    bad = [{"title": "Staff Eng", "posted_on": "2026-04-15"}]  # no source_url
    with pytest.raises(EvidenceFormatError):
        job_posts.load(bad, company_id="acme")


# --- Dataclass audit-trail enforcement ---

def test_fact_without_source_url_raises():
    with pytest.raises(ValueError, match="source_url required"):
        Fact(
            company_id="acme", source_type="crunchbase", kind="funding_round",
            summary="x", payload={}, source_url="", retrieved_at="2026-04-22T00:00:00+00:00",
        )


# --- End-to-end collector ---

def test_collector_round_trip_via_db(conn, acme_fixture):
    ids = collector.collect(acme_fixture, conn)
    # 1 crunchbase + 3 job_posts + 0 layoffs + 1 leadership + 1 company_metadata = 6
    assert len(ids) == 6

    rows = db.get_evidence(conn, ids)
    assert len(rows) == 6
    assert {r["source_type"] for r in rows} == {"crunchbase", "job_posts", "leadership", "company_metadata"}
    assert all(r["company_id"] == "acme" for r in rows)
    assert all(r["method"] == "fixture" for r in rows)
    assert all(r["source_url"].startswith("https://example.com/") for r in rows)

    # kind is merged into raw_payload at write time
    for r in rows:
        payload = json.loads(r["raw_payload"])
        assert "kind" in payload


def test_collector_with_aged_retrieved_at(conn):
    aged_fixture = {
        "company_id": "beta",
        "sources": {
            "crunchbase": {
                "funding_round": {
                    "round": "Series A",
                    "amount_usd": 10_000_000,
                    "announced_on": "2026-03-01",
                    "source_url": "https://example.com/crunchbase/beta",
                    "retrieved_at": "2026-03-02T09:00:00+00:00",
                },
            },
        },
    }
    ids = collector.collect(aged_fixture, conn)
    row = db.get_evidence(conn, ids)[0]
    assert row["retrieved_at"] == "2026-03-02T09:00:00+00:00"


def test_collector_ignores_underscore_prefixed_keys(conn, acme_fixture):
    # _note at the fixture root is not in sources; make sure _-prefixed section keys are skipped too.
    acme_fixture["sources"]["_provenance"] = {"anything": "that would crash a loader"}
    ids = collector.collect(acme_fixture, conn)
    assert len(ids) == 6  # same as clean run; _provenance was skipped
