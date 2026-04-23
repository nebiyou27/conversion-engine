"""AI maturity judgment — LLM-adjudicated scoring with rubric prompt.

Unlike segment.py (deterministic), this module calls the LLM via
``integrations.llm.complete()`` with the rubric prompt from
``agent/prompts/ai_maturity_rubric.md``. The response is parsed into the
structured shape defined by ``hiring_signal_brief.schema.json#ai_maturity``.

Absence handling (Phase 5 decision):
  - status: "absent" → weight ≤ 0.3 (low-weight evidence of absence)
  - status: "unknown" → weight 0 (not counted)

This is the most expensive and flaky judgment module. It is built last
because every other module can be tested deterministically without it.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrations.llm import BudgetLedger, LLMResponse, complete
from storage import db

RUBRIC_PATH = Path(__file__).parent.parent / "prompts" / "ai_maturity_rubric.md"

VALID_SIGNALS = frozenset({
    "ai_adjacent_open_roles",
    "named_ai_ml_leadership",
    "github_org_activity",
    "executive_commentary",
    "modern_data_ml_stack",
    "strategic_communications",
})

VALID_WEIGHTS = frozenset({"high", "medium", "low"})
VALID_CONFIDENCES = frozenset({"high", "medium", "low"})


class AiMaturityParseError(ValueError):
    """LLM response did not conform to the rubric output spec."""


def _load_rubric() -> str:
    return RUBRIC_PATH.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    # Try stripping markdown code fence
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise AiMaturityParseError(f"LLM response is not valid JSON: {e}\n---\n{text}") from e


def _validate(result: dict) -> dict:
    """Validate and normalize the parsed LLM response."""
    if not isinstance(result, dict):
        raise AiMaturityParseError(f"Expected dict, got {type(result).__name__}")

    # Score
    score = result.get("score")
    if score is None or not isinstance(score, int) or not (0 <= score <= 3):
        raise AiMaturityParseError(f"score must be int 0–3, got {score!r}")

    # Confidence
    confidence = result.get("confidence")
    if confidence is None:
        confidence = 0.5  # default if LLM omits
    if not isinstance(confidence, (int, float)):
        raise AiMaturityParseError(f"confidence must be numeric, got {confidence!r}")
    confidence = max(0.0, min(1.0, float(confidence)))

    # Justifications
    justifications = result.get("justifications")
    if not isinstance(justifications, list):
        raise AiMaturityParseError(f"justifications must be a list, got {type(justifications).__name__}")

    validated_justifications: list[dict[str, Any]] = []
    seen_signals: set[str] = set()

    for j in justifications:
        if not isinstance(j, dict):
            raise AiMaturityParseError(f"justification entry must be dict, got {type(j).__name__}")

        signal = j.get("signal", "")
        if signal not in VALID_SIGNALS:
            continue  # skip unknown signals, don't crash

        seen_signals.add(signal)

        status = j.get("status", "unknown")
        weight = j.get("weight", "low")
        conf = j.get("confidence", "low")
        source_url = j.get("source_url")

        # Normalize weight and confidence
        if weight not in VALID_WEIGHTS:
            weight = "low"
        if conf not in VALID_CONFIDENCES:
            conf = "low"

        # Absence handling per Phase 5 decision
        if status == "absent":
            weight = "low"  # cap at low-weight evidence
        if status == "unknown":
            weight = "low"
            conf = "low"

        validated_justifications.append({
            "signal": signal,
            "status": status,
            "weight": weight,
            "confidence": conf,
            "source_url": source_url,
        })

    # Fill missing signals as absent
    for signal in VALID_SIGNALS - seen_signals:
        validated_justifications.append({
            "signal": signal,
            "status": "absent",
            "weight": "low",
            "confidence": "low",
            "source_url": None,
        })

    return {
        "score": score,
        "confidence": confidence,
        "justifications": validated_justifications,
    }


def _build_user_message(claims: list[dict]) -> str:
    """Format the company's claims into a structured prompt for the LLM."""
    if not claims:
        return "No claims available for this company. Score based on absence of all signals."

    lines = ["Company claims for AI maturity assessment:", ""]
    for c in claims:
        tier = c.get("tier", "unknown")
        kind = c.get("kind", "unknown")
        assertion = c.get("assertion", "")
        payload_raw = c.get("payload")
        payload = {}
        if payload_raw:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw

        lines.append(f"- [{tier}] {kind}: {assertion}")
        if kind == "hiring_surge" and payload.get("titles"):
            for t in payload["titles"]:
                lines.append(f"    Role: {t}")
        if kind == "company_metadata":
            if payload.get("headcount"):
                lines.append(f"    Headcount: {payload['headcount']}")

    return "\n".join(lines)


def judge(
    conn: sqlite3.Connection,
    company_id: str,
    *,
    run_id: str,
    ledger: BudgetLedger,
    client: Any | None = None,
) -> dict[str, Any]:
    """Produce the AI maturity judgment for a company.

    Parameters
    ----------
    conn : sqlite3.Connection
        DB connection with claims already written.
    company_id : str
        Target company.
    run_id : str
        LLM budget tracking run ID.
    ledger : BudgetLedger
        Cost ceiling tracker.
    client : optional
        Override OpenAI client for testing.

    Returns
    -------
    dict matching hiring_signal_brief.schema.json#ai_maturity:
        score : int (0–3)
        confidence : float (0.0–1.0)
        justifications : list[dict]
        judgment_id : str
    """
    # Fetch claims
    rows = conn.execute(
        "SELECT * FROM claims WHERE company_id = ?", (company_id,)
    ).fetchall()
    claims = [dict(r) for r in rows]

    rubric = _load_rubric()
    user_msg = _build_user_message(claims)

    messages = [
        {"role": "system", "content": rubric},
        {"role": "user", "content": user_msg},
    ]

    kwargs: dict[str, Any] = {
        "run_id": run_id,
        "ledger": ledger,
        "max_tokens": 800,
        "temperature": 0.0,
        "metadata": {"name": "ai_maturity"},
    }
    if client is not None:
        kwargs["client"] = client

    resp: LLMResponse = complete(messages, **kwargs)

    parsed = _extract_json(resp.text)
    result = _validate(parsed)

    # Persist judgment
    judgment_id = db.insert_judgment(
        conn,
        company_id=company_id,
        kind="ai_maturity",
        value=str(result["score"]),
        claim_ids=[c["claim_id"] for c in claims],
        rationale=json.dumps(result["justifications"]),
    )

    return {**result, "judgment_id": judgment_id}


def parse_response(text: str) -> dict[str, Any]:
    """Parse and validate an LLM response string. Useful for testing."""
    parsed = _extract_json(text)
    return _validate(parsed)
