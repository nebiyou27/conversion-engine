"""Judgment layer contract tests.

Covers four modules:
  - segment.py — deterministic 5-step ladder (most branches)
  - icp.py — thin wrapper, DB round-trip
  - competitor_gap.py — stub shape validation
  - ai_maturity.py — parser validation (no LLM calls)

No LLM calls in this file. ai_maturity tests exercise the parser/validator
against canned JSON strings; live LLM integration is tested separately.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.claims import builder
from agent.evidence import collector
from agent.judgment import ai_maturity, competitor_gap, icp, segment
from agent.judgment.ai_maturity import AiMaturityParseError
from storage import db

NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
ACME_FIXTURE_PATH = Path("data/fixtures/companies/acme_series_b.json")
CONTRADICTED_FIXTURE_PATH = Path("data/fixtures/companies/contradicted_co.json")
SHADOW_FIXTURE_PATH = Path("data/fixtures/companies/shadow_startup.json")
SILENT_FIXTURE_PATH = Path("data/fixtures/companies/silent_sophisticate.json")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.init(c)
    yield c
    c.close()


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _ingest(conn, fixture: dict) -> list[str]:
    """Evidence + claims in one shot."""
    collector.collect(fixture, conn)
    return builder.build(conn, fixture["company_id"], now=NOW)


def _make_claims(conn, company_id: str, claim_specs: list[dict]) -> list[dict]:
    """Insert synthetic claims and return them as dicts."""
    ids = []
    for spec in claim_specs:
        cid = db.insert_claim(
            conn,
            company_id=company_id,
            kind=spec["kind"],
            assertion=spec.get("assertion", "test"),
            tier=spec.get("tier", "corroborated"),
            evidence_ids=spec.get("evidence_ids", []),
            payload=spec.get("payload"),
        )
        ids.append(cid)
    return [dict(r) for r in db.get_claims(conn, ids)]


# =====================================================================
# segment.py — deterministic classifier
# =====================================================================

class TestSegmentLadder:
    """Each test locks one step of the 5-step priority ladder."""

    def test_s2_layoff_plus_funding(self, conn):
        """Step 1: layoff within 120d + fresh funding → S2."""
        fixture = _load_fixture(CONTRADICTED_FIXTURE_PATH)
        _ingest(conn, fixture)

        rows = conn.execute(
            "SELECT * FROM claims WHERE company_id = ?",
            (fixture["company_id"],),
        ).fetchall()
        claims = [dict(r) for r in rows]

        result = segment.classify(claims, now=NOW)
        assert result["primary_segment_match"] == "segment_2_mid_market_restructure"
        assert result["segment_confidence"] >= 0.6

    def test_s3_leadership_transition(self, conn):
        """Step 2: new CTO within 90d + headcount 50–500 → S3."""
        claims = _make_claims(conn, "co3", [
            {
                "kind": "leadership_change",
                "tier": "corroborated",
                "payload": {"event": "new_cto", "person": "Jane", "effective": "2026-04-01"},
            },
            {
                "kind": "company_metadata",
                "tier": "corroborated",
                "payload": {"headcount": 120},
            },
        ])
        result = segment.classify(claims, now=NOW)
        assert result["primary_segment_match"] == "segment_3_leadership_transition"
        assert result["segment_confidence"] >= 0.6

    def test_s3_rejected_concurrent_cfo(self, conn):
        """S3 disqualified: concurrent CFO transition."""
        claims = _make_claims(conn, "co3b", [
            {
                "kind": "leadership_change",
                "tier": "corroborated",
                "payload": {"event": "new_cto", "person": "J", "effective": "2026-04-01"},
            },
            {
                "kind": "leadership_change",
                "tier": "corroborated",
                "payload": {"event": "new_cfo", "person": "K", "effective": "2026-04-05"},
            },
            {
                "kind": "company_metadata",
                "tier": "corroborated",
                "payload": {"headcount": 100},
            },
        ])
        result = segment.classify(claims, now=NOW)
        assert result["primary_segment_match"] != "segment_3_leadership_transition"

    def test_s3_rejected_headcount_too_large(self, conn):
        """S3 disqualified: headcount > 500."""
        claims = _make_claims(conn, "co3c", [
            {
                "kind": "leadership_change",
                "tier": "corroborated",
                "payload": {"event": "new_cto", "person": "J", "effective": "2026-04-01"},
            },
            {
                "kind": "company_metadata",
                "tier": "corroborated",
                "payload": {"headcount": 2000},
            },
        ])
        result = segment.classify(claims, now=NOW)
        assert result["primary_segment_match"] != "segment_3_leadership_transition"

    def test_s4_ai_maturity_ge_2_plus_hiring(self, conn):
        """Step 3: AI maturity ≥ 2 + hiring → S4."""
        claims = _make_claims(conn, "co4", [
            {
                "kind": "hiring_surge",
                "tier": "verified",
                "payload": {"postings_count": 5, "titles": ["ML Eng", "Data Sci"]},
            },
        ])
        result = segment.classify(claims, now=NOW, ai_maturity_score=2)
        assert result["primary_segment_match"] == "segment_4_specialized_capability"
        assert result["segment_confidence"] >= 0.6

    def test_s4_rejected_low_ai_maturity(self, conn):
        """S4 not triggered when AI maturity < 2."""
        claims = _make_claims(conn, "co4b", [
            {
                "kind": "hiring_surge",
                "tier": "verified",
                "payload": {"postings_count": 5, "titles": ["ML Eng"]},
            },
        ])
        result = segment.classify(claims, now=NOW, ai_maturity_score=1)
        assert result["primary_segment_match"] != "segment_4_specialized_capability"

    def test_s1_recent_funding(self, conn):
        """Step 4: fresh funding within 180d → S1."""
        fixture = _load_fixture(ACME_FIXTURE_PATH)
        _ingest(conn, fixture)

        rows = conn.execute(
            "SELECT * FROM claims WHERE company_id = 'acme'",
        ).fetchall()
        claims = [dict(r) for r in rows]

        result = segment.classify(claims, now=NOW)
        assert result["primary_segment_match"] == "segment_1_series_a_b"
        assert result["segment_confidence"] >= 0.6

    def test_abstain_on_stale_signals(self, conn):
        """Step 5: shadow_startup has only stale/below_threshold claims → abstain."""
        fixture = _load_fixture(SHADOW_FIXTURE_PATH)
        _ingest(conn, fixture)

        rows = conn.execute(
            "SELECT * FROM claims WHERE company_id = ?",
            (fixture["company_id"],),
        ).fetchall()
        claims = [dict(r) for r in rows]

        result = segment.classify(claims, now=NOW)
        assert result["primary_segment_match"] == "abstain"
        assert result["segment_confidence"] == 0.0

    def test_abstain_on_empty_claims(self):
        """No claims at all → abstain."""
        result = segment.classify([], now=NOW)
        assert result["primary_segment_match"] == "abstain"
        assert result["segment_confidence"] == 0.0
        assert result["claim_ids"] == []

    def test_s2_priority_over_s1(self, conn):
        """S2 beats S1: layoff + funding → S2, even though funding alone → S1."""
        fixture = _load_fixture(CONTRADICTED_FIXTURE_PATH)
        _ingest(conn, fixture)

        rows = conn.execute(
            "SELECT * FROM claims WHERE company_id = ?",
            (fixture["company_id"],),
        ).fetchall()
        claims = [dict(r) for r in rows]

        result = segment.classify(claims, now=NOW)
        # Must be S2, not S1
        assert result["primary_segment_match"] == "segment_2_mid_market_restructure"

    def test_s3_priority_over_s4(self, conn):
        """S3 beats S4 when both match."""
        claims = _make_claims(conn, "co34", [
            {
                "kind": "leadership_change",
                "tier": "corroborated",
                "payload": {"event": "new_cto", "person": "J", "effective": "2026-04-01"},
            },
            {
                "kind": "hiring_surge",
                "tier": "verified",
                "payload": {"postings_count": 5, "titles": ["ML Eng"]},
            },
            {
                "kind": "company_metadata",
                "tier": "corroborated",
                "payload": {"headcount": 100},
            },
        ])
        result = segment.classify(claims, now=NOW, ai_maturity_score=3)
        assert result["primary_segment_match"] == "segment_3_leadership_transition"


class TestSegmentHelpers:
    """Lock helper function behavior."""

    def test_open_role_count_from_hiring_surge(self, conn):
        claims = _make_claims(conn, "hr1", [
            {
                "kind": "hiring_surge",
                "tier": "verified",
                "payload": {"postings_count": 7, "titles": ["A", "B"]},
            },
        ])
        assert segment._open_role_count(claims) == 7

    def test_open_role_count_zero_when_no_surge(self):
        assert segment._open_role_count([]) == 0

    def test_get_headcount_from_metadata(self, conn):
        claims = _make_claims(conn, "hc1", [
            {
                "kind": "company_metadata",
                "tier": "corroborated",
                "payload": {"headcount": 42},
            },
        ])
        assert segment._get_headcount(claims) == 42

    def test_get_headcount_none_when_absent(self):
        assert segment._get_headcount([]) is None

    def test_below_threshold_claims_are_not_actionable(self, conn):
        claims = _make_claims(conn, "bt1", [
            {
                "kind": "funding_round",
                "tier": "below_threshold",
                "payload": {"round": "A", "amount_usd": 10000000, "announced_on": "2026-04-18"},
            },
        ])
        assert not segment._is_actionable(claims[0])


# =====================================================================
# icp.py — thin wrapper
# =====================================================================

class TestICP:
    def test_judge_persists_judgment_row(self, conn):
        fixture = _load_fixture(ACME_FIXTURE_PATH)
        _ingest(conn, fixture)

        result = icp.judge(conn, "acme", now=NOW)
        assert "judgment_id" in result
        assert result["primary_segment_match"] == "segment_1_series_a_b"

        # Verify DB persistence
        judgments = db.get_judgments(conn, "acme")
        assert any(j["kind"] == "segment" for j in judgments)

    def test_judge_with_ai_maturity_score(self, conn):
        _make_claims(conn, "icp2", [
            {
                "kind": "hiring_surge",
                "tier": "verified",
                "payload": {"postings_count": 5, "titles": ["ML Eng"]},
            },
        ])
        result = icp.judge(conn, "icp2", now=NOW, ai_maturity_score=2)
        assert result["primary_segment_match"] == "segment_4_specialized_capability"


# =====================================================================
# competitor_gap.py — deterministic peer benchmark
# =====================================================================

class TestCompetitorGap:
    def _justifications(self, *, leadership="absent", mlops="absent", commentary="absent", stack="absent"):
        return [
            {"signal": "named_ai_ml_leadership", "status": leadership, "weight": "low", "confidence": "medium", "source_url": None},
            {"signal": "ai_adjacent_open_roles", "status": mlops, "weight": "low", "confidence": "medium", "source_url": None},
            {"signal": "executive_commentary", "status": commentary, "weight": "low", "confidence": "medium", "source_url": None},
            {"signal": "modern_data_ml_stack", "status": stack, "weight": "low", "confidence": "medium", "source_url": None},
        ]

    def test_returns_schema_shaped_peer_gap_brief(self, conn):
        result = competitor_gap.judge(
            conn, "acme",
            prospect_domain="acme.com",
            prospect_sector="saas",
            ai_maturity_score=1,
            ai_maturity_justifications=self._justifications(),
        )
        assert result is not None
        assert result["prospect_domain"] == "acme.com"
        assert result["prospect_sector"] == "saas"
        assert result["prospect_ai_maturity_score"] == 1
        assert len(result["competitors_analyzed"]) == 6
        assert 1 <= len(result["gap_findings"]) <= 3
        assert "judgment_id" in result

    def test_top_quartile_math_and_gap_selection(self, conn):
        result = competitor_gap.judge(
            conn,
            "acme",
            prospect_domain="acme.com",
            prospect_sector="saas",
            ai_maturity_score=0,
            ai_maturity_justifications=self._justifications(mlops="1 ML role open"),
        )
        assert result is not None
        assert result["sector_top_quartile_benchmark"] == 3.0
        top = [p for p in result["competitors_analyzed"] if p["top_quartile"]]
        assert [p["domain"] for p in top] == ["northstar-metrics.example", "vectorlane.example"]
        practices = {g["practice"] for g in result["gap_findings"]}
        assert "Dedicated MLOps or ML-platform engineering role open" not in practices
        assert "Dedicated AI/ML leadership role publicly named" in practices

    def test_missing_peer_file_abstains_without_judgment(self, conn):
        result = competitor_gap.judge(
            conn,
            "acme",
            prospect_domain="acme.com",
            prospect_sector="industrial",
            ai_maturity_score=0,
            ai_maturity_justifications=self._justifications(),
        )
        assert result is None
        assert not db.get_judgments(conn, "acme")

    def test_self_check_flags(self, conn):
        result = competitor_gap.judge(
            conn,
            "silent",
            prospect_domain="silent.example",
            prospect_sector="saas",
            ai_maturity_score=1,
            ai_maturity_justifications=self._justifications(commentary="published engineering blog"),
        )
        assert result is not None
        flags = result["gap_quality_self_check"]
        assert flags["all_peer_evidence_has_source_url"] is True
        assert flags["at_least_one_gap_high_confidence"] is False
        assert flags["prospect_silent_but_sophisticated_risk"] is True

    def test_persists_benchmark_and_gap_rationale(self, conn):
        _make_claims(conn, "acme", [
            {
                "kind": "hiring_surge",
                "tier": "verified",
                "payload": {"postings_count": 3, "titles": ["ML Engineer"]},
            },
        ])
        result = competitor_gap.judge(
            conn,
            "acme",
            prospect_domain="acme.com",
            prospect_sector="saas",
            ai_maturity_score=0,
            ai_maturity_justifications=self._justifications(),
        )
        assert result is not None
        judgments = db.get_judgments(conn, "acme")
        gap_judgment = next(j for j in judgments if j["kind"] == "competitor_gap")
        assert gap_judgment["value"] == "3.0"
        assert "Dedicated AI/ML leadership" in gap_judgment["rationale"]
        assert json.loads(gap_judgment["claim_ids"])

    def test_pitch_shift_template_uses_top_gap_confidence(self, conn):
        result = competitor_gap.judge(
            conn,
            "acme",
            prospect_domain="acme.com",
            prospect_sector="saas",
            ai_maturity_score=0,
            ai_maturity_justifications=self._justifications(),
        )
        assert result is not None
        assert "Confidence is medium" in result["suggested_pitch_shift"]
        assert "frame it as a question" in result["suggested_pitch_shift"]


# =====================================================================
# ai_maturity.py — parser tests (no LLM)
# =====================================================================

class TestAiMaturityParser:
    """Test the parse_response function against canned JSON."""

    def test_valid_full_response(self):
        raw = json.dumps({
            "score": 2,
            "confidence": 0.75,
            "justifications": [
                {"signal": "ai_adjacent_open_roles", "status": "2 ML roles open", "weight": "high", "confidence": "high", "source_url": "https://example.com/jobs"},
                {"signal": "named_ai_ml_leadership", "status": "absent", "weight": "high", "confidence": "low", "source_url": None},
                {"signal": "github_org_activity", "status": "unknown", "weight": "medium", "confidence": "low", "source_url": None},
                {"signal": "executive_commentary", "status": "absent", "weight": "medium", "confidence": "low", "source_url": None},
                {"signal": "modern_data_ml_stack", "status": "MLflow in job posts", "weight": "medium", "confidence": "medium", "source_url": "https://example.com/jobs/2"},
                {"signal": "strategic_communications", "status": "absent", "weight": "low", "confidence": "low", "source_url": None},
            ],
        })
        result = ai_maturity.parse_response(raw)
        assert result["score"] == 2
        assert result["confidence"] == 0.75
        assert len(result["justifications"]) == 6

    def test_absent_signal_capped_to_low_weight(self):
        raw = json.dumps({
            "score": 0,
            "confidence": 0.9,
            "justifications": [
                {"signal": "ai_adjacent_open_roles", "status": "absent", "weight": "high", "confidence": "high", "source_url": None},
            ],
        })
        result = ai_maturity.parse_response(raw)
        # Absent signal's weight must be capped to "low"
        j = next(j for j in result["justifications"] if j["signal"] == "ai_adjacent_open_roles")
        assert j["weight"] == "low"

    def test_unknown_signal_gets_low_weight_and_confidence(self):
        raw = json.dumps({
            "score": 1,
            "confidence": 0.5,
            "justifications": [
                {"signal": "github_org_activity", "status": "unknown", "weight": "high", "confidence": "high", "source_url": None},
            ],
        })
        result = ai_maturity.parse_response(raw)
        j = next(j for j in result["justifications"] if j["signal"] == "github_org_activity")
        assert j["weight"] == "low"
        assert j["confidence"] == "low"

    def test_missing_signals_filled_as_absent(self):
        raw = json.dumps({
            "score": 0,
            "confidence": 0.9,
            "justifications": [],  # no signals at all
        })
        result = ai_maturity.parse_response(raw)
        # All 6 signals must be present
        assert len(result["justifications"]) == 6
        for j in result["justifications"]:
            assert j["status"] == "absent"
            assert j["weight"] == "low"

    def test_all_absent_forces_score_zero_and_low_confidence(self):
        raw = json.dumps({
            "score": 2,
            "confidence": 0.9,
            "justifications": [
                {"signal": "ai_adjacent_open_roles", "status": "absent", "weight": "high", "confidence": "high", "source_url": None},
                {"signal": "named_ai_ml_leadership", "status": "unknown", "weight": "high", "confidence": "high", "source_url": None},
            ],
        })
        result = ai_maturity.parse_response(raw)
        assert result["score"] == 0
        assert result["confidence"] == 0.3

    def test_markdown_fenced_json_extracted(self):
        raw = '```json\n{"score": 1, "confidence": 0.5, "justifications": []}\n```'
        result = ai_maturity.parse_response(raw)
        assert result["score"] == 0

    def test_invalid_score_raises(self):
        raw = json.dumps({"score": 5, "confidence": 0.5, "justifications": []})
        with pytest.raises(AiMaturityParseError):
            ai_maturity.parse_response(raw)

    def test_non_json_raises(self):
        with pytest.raises(AiMaturityParseError):
            ai_maturity.parse_response("I think the score is 2.")

    def test_missing_score_raises(self):
        raw = json.dumps({"confidence": 0.5, "justifications": []})
        with pytest.raises(AiMaturityParseError):
            ai_maturity.parse_response(raw)

    def test_confidence_clamped_to_bounds(self):
        raw = json.dumps({
            "score": 1,
            "confidence": 1.5,
            "justifications": [
                {"signal": "ai_adjacent_open_roles", "status": "1 ML role open", "weight": "high", "confidence": "high", "source_url": "https://example.com/jobs"}
            ],
        })
        result = ai_maturity.parse_response(raw)
        assert result["confidence"] == 1.0

        raw2 = json.dumps({
            "score": 1,
            "confidence": -0.5,
            "justifications": [
                {"signal": "ai_adjacent_open_roles", "status": "1 ML role open", "weight": "high", "confidence": "high", "source_url": "https://example.com/jobs"}
            ],
        })
        result2 = ai_maturity.parse_response(raw2)
        assert result2["confidence"] == 0.0

    def test_unknown_signals_in_response_ignored_gracefully(self):
        raw = json.dumps({
            "score": 1,
            "confidence": 0.5,
            "justifications": [
                {"signal": "completely_made_up", "status": "found", "weight": "high", "confidence": "high"},
                {"signal": "ai_adjacent_open_roles", "status": "found", "weight": "high", "confidence": "high"},
            ],
        })
        result = ai_maturity.parse_response(raw)
        signals = {j["signal"] for j in result["justifications"]}
        assert "completely_made_up" not in signals
        assert "ai_adjacent_open_roles" in signals

    def test_default_confidence_when_omitted(self):
        raw = json.dumps({"score": 0, "justifications": []})
        result = ai_maturity.parse_response(raw)
        assert result["confidence"] == 0.3  # silent-company cap

    def test_build_user_message_with_claims(self, conn):
        """Smoke test: _build_user_message produces non-empty string."""
        fixture = _load_fixture(ACME_FIXTURE_PATH)
        _ingest(conn, fixture)
        rows = conn.execute("SELECT * FROM claims WHERE company_id = 'acme'").fetchall()
        claims = [dict(r) for r in rows]
        msg = ai_maturity._build_user_message(claims)
        assert "funding_round" in msg or "hiring_surge" in msg

    def test_build_user_message_empty_claims(self):
        msg = ai_maturity._build_user_message([])
        assert "No claims" in msg
