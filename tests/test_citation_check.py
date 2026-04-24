"""Citation coverage gate tests."""
from __future__ import annotations

from agent.gate.citation_check import check


CLAIM_ID = "12345678-1234-5678-1234-567812345678"


def test_factual_question_requires_citation():
    result = check("Is Acme hiring three platform roles?", [CLAIM_ID])

    assert result["ok"] is False
    assert result["failures"] == ["Is Acme hiring three platform roles?"]


def test_operational_question_does_not_require_citation():
    result = check("Would you be open to a 20-minute discovery call next week?", [CLAIM_ID])

    assert result["ok"] is True


def test_factual_question_with_known_citation_passes():
    result = check(f"Is Acme hiring three platform roles {{{CLAIM_ID}}}?", [CLAIM_ID])

    assert result["ok"] is True
    assert result["claim_ids"] == [CLAIM_ID]
