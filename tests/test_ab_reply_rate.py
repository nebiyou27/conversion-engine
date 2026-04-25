"""A/B reply-rate evaluation contract tests."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval import ab_reply_rate
from integrations.llm import BudgetLedger


@dataclass
class _Usage:
    prompt_tokens: int = 100
    completion_tokens: int = 40


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Response:
    choices: list[_Choice]
    usage: _Usage


class _Completions:
    def __init__(self, responses: list[str]):
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self._responses.pop(0)
        return _Response(choices=[_Choice(_Message(text))], usage=_Usage())


class _Chat:
    def __init__(self, completions: _Completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, responses: list[str]):
        self.completions = _Completions(responses)
        self.chat = _Chat(self.completions)


def test_parse_draft_accepts_fenced_json():
    draft = ab_reply_rate.parse_draft(
        '```json\n{"subject":"Quick note","body":"Hi team, worth comparing notes?"}\n```'
    )
    assert draft.subject == "Quick note"
    assert "comparing notes" in draft.body


def test_parse_draft_accepts_subject_body_fallback():
    draft = ab_reply_rate.parse_draft("Subject: Quick note\nBody: Hi team,\nWorth comparing notes?")
    assert draft.subject == "Quick note"
    assert "Worth comparing notes" in draft.body


def test_parse_judgment_returns_boolean_and_reason():
    result = ab_reply_rate.parse_judgment('{"reply": true, "reason": "specific timing"}')
    assert result == {"reply": True, "reason": "specific timing"}


def test_build_context_uses_fixture_claims():
    context = ab_reply_rate.build_context(Path("data/fixtures/companies/acme_series_b.json"))
    assert context["company_name"] == "Acme Data"
    assert context["claims"]
    assert "ai_maturity" in context
    assert "competitor_gap" in context


def test_timing_grounded_context_excludes_gap_and_ai_maturity():
    context = ab_reply_rate.build_context(Path("data/fixtures/companies/acme_series_b.json"))

    messages = ab_reply_rate._draft_messages("timing_grounded", context, trial_index=1)
    user_message = messages[1]["content"]

    assert "timing_claims" in user_message
    assert "competitor_gap" not in user_message
    assert "ai_maturity" not in user_message
    assert "company_metadata" not in user_message


def test_build_report_aggregates_variants_with_fake_client():
    responses = [
        json.dumps({"subject": "Signal", "body": "Hi, your cited hiring signal creates timing."}),
        json.dumps({"reply": True, "reason": "specific"}),
        json.dumps({"subject": "Generic", "body": "Hi, helping teams improve engineering outcomes."}),
        json.dumps({"reply": False, "reason": "generic"}),
    ]
    client = _FakeClient(responses)
    ledger = BudgetLedger(run_id="test-ab", ceiling_usd=1.0)

    report = ab_reply_rate.build_report(
        trials=1,
        fixture_paths=[Path("data/fixtures/companies/acme_series_b.json")],
        run_id="test-ab",
        ledger=ledger,
        client=client,
    )

    assert report["variants"]["signal_grounded"]["n"] == 1
    assert report["variants"]["signal_grounded"]["reply_rate"] == 1.0
    assert report["variants"]["generic"]["reply_rate"] == 0.0
    assert report["delta_pp_signal_grounded_minus_generic"] == 100.0
    assert report["ledger"]["calls"] == 4
    assert len(report["details"]) == 2


def test_build_report_can_run_timing_grounded_against_generic():
    responses = [
        json.dumps({"subject": "Timing", "body": "Hi, your cited funding date creates timing."}),
        json.dumps({"reply": True, "reason": "timely"}),
        json.dumps({"subject": "Generic", "body": "Hi, helping teams improve engineering outcomes."}),
        json.dumps({"reply": False, "reason": "generic"}),
    ]
    client = _FakeClient(responses)
    ledger = BudgetLedger(run_id="test-timing-ab", ceiling_usd=1.0)

    report = ab_reply_rate.build_report(
        trials=1,
        fixture_paths=[Path("data/fixtures/companies/acme_series_b.json")],
        variants=["timing_grounded", "generic"],
        run_id="test-timing-ab",
        ledger=ledger,
        client=client,
    )

    assert report["variants"]["timing_grounded"]["reply_rate"] == 1.0
    assert report["variants"]["generic"]["reply_rate"] == 0.0
    assert report["delta_pp_timing_grounded_minus_generic"] == 100.0
    assert report["delta_pp_signal_grounded_minus_generic"] is None


def test_build_report_retries_empty_draft_response():
    responses = [
        "",
        json.dumps({"subject": "Signal", "body": "Hi, your cited hiring signal creates timing."}),
        json.dumps({"reply": "yes", "reason": "specific"}),
        json.dumps({"subject": "Generic", "body": "Hi, helping teams improve engineering outcomes."}),
        json.dumps({"reply": False, "reason": "generic"}),
    ]
    client = _FakeClient(responses)
    ledger = BudgetLedger(run_id="test-retry", ceiling_usd=1.0)

    report = ab_reply_rate.build_report(
        trials=1,
        fixture_paths=[Path("data/fixtures/companies/acme_series_b.json")],
        run_id="test-retry",
        ledger=ledger,
        client=client,
    )

    assert report["details"][0]["draft_attempts"] == 2
    assert report["variants"]["signal_grounded"]["reply_rate"] == 1.0
    assert report["ledger"]["calls"] == 5
