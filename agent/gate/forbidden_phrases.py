"""Forbidden-phrase filter for outbound drafts."""
from __future__ import annotations

import re
from typing import Any

FORBIDDEN_PATTERNS = [
    r"\btop talent\b",
    r"\bworld[- ]?class\b",
    r"\bA-players\b",
    r"\brockstar\b",
    r"\bninja\b",
    r"\bbench\b",
    r"\bcost savings\b",
]

FORBIDDEN_RE = re.compile("|".join(f"({p})" for p in FORBIDDEN_PATTERNS), re.IGNORECASE)


def check(text: str) -> dict[str, Any]:
    """Check a draft body or subject for forbidden phrases."""
    matches = [m.group(0) for m in FORBIDDEN_RE.finditer(text)]
    return {
        "ok": not matches,
        "matches": matches,
    }
