"""Citation coverage gate for drafted emails."""
from __future__ import annotations

import re
from typing import Any

CITATION_RE = re.compile(r"\{([0-9a-fA-F-]{8,})\}")
SALUTATION_RE = re.compile(r"^(hi|hello|dear|best|regards|thanks)\b", re.IGNORECASE)
SIGNATURE_RE = re.compile(r"^(tenacious consulting|tenacious consulting and outsourcing)$", re.IGNORECASE)


def _split_sentences(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


def check(body: str, claim_ids: list[str]) -> dict[str, Any]:
    """Check that factual sentences carry claim citations."""
    allowed = set(claim_ids)
    failures: list[str] = []
    citations: list[str] = []

    for sentence in _split_sentences(body):
        sentence_citations = CITATION_RE.findall(sentence)
        citations.extend(sentence_citations)
        if SALUTATION_RE.match(sentence):
            continue
        if SIGNATURE_RE.match(sentence):
            continue
        if sentence.endswith("?"):
            continue
        if sentence_citations:
            continue
        if re.search(r"[A-Za-z]", sentence):
            failures.append(sentence)

    unknown = [cid for cid in citations if cid not in allowed]
    if unknown:
        failures.append(f"Unknown claim ids cited: {sorted(set(unknown))}")

    return {
        "ok": not failures,
        "failures": failures,
        "claim_ids": sorted(set(citations)),
    }
