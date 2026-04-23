"""Shadow-review gate â€” lightweight unsupported-claim detection."""
from __future__ import annotations

from typing import Any

from agent.gate.citation_check import check as citation_check
from agent.gate.forbidden_phrases import FORBIDDEN_RE


def check(body: str, claim_ids: list[str]) -> dict[str, Any]:
    """Run a second pass looking for unsupported or overly salesy language."""
    citation_result = citation_check(body, claim_ids)
    matches = [m.group(0) for m in FORBIDDEN_RE.finditer(body)]
    risky_words = []
    for word in ("maybe", "probably", "guarantee", "world-class", "top talent"):
        if word in body.lower():
            risky_words.append(word)
    failures = list(citation_result["failures"])
    if matches:
        failures.append(f"forbidden phrases: {sorted(set(matches))}")
    if risky_words:
        failures.append(f"risky wording: {sorted(set(risky_words))}")
    return {
        "ok": not failures,
        "failures": failures,
    }
