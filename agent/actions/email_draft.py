"""Deterministic email draft builder."""
from __future__ import annotations

from typing import Any


def _claim_citation(claim_id: str) -> str:
    return f"{{{claim_id}}}"


def build_commitment_email(
    *,
    company_name: str,
    prospect_name: str | None,
    claim_rows: list[dict[str, Any]],
    segment_match: str,
) -> dict[str, Any]:
    """Build a citation-backed commitment-path email."""
    salutation = f"Hi {prospect_name}," if prospect_name else f"Hi {company_name} team,"

    body_lines = [salutation, ""]
    factual_lines: list[str] = []

    for row in claim_rows:
        kind = row.get("kind")
        claim_id = row.get("claim_id", "")
        assertion = row.get("assertion", "")
        tier = row.get("tier", "corroborated")
        if kind == "funding_round":
            factual_lines.append(f"I saw the recent funding note: {assertion} {_claim_citation(claim_id)}")
        elif kind == "hiring_surge":
            factual_lines.append(f"Your hiring pattern points to a real build-out: {assertion} {_claim_citation(claim_id)}")
        elif kind == "leadership_change":
            factual_lines.append(f"Your leadership change stands out: {assertion} {_claim_citation(claim_id)}")
        elif kind == "layoff_event":
            factual_lines.append(f"The layoff signal suggests operating pressure: {assertion} {_claim_citation(claim_id)}")
        elif kind == "company_metadata":
            factual_lines.append(f"Your team size context is useful here: {assertion} {_claim_citation(claim_id)}")

        if tier == "inferred" and factual_lines:
            factual_lines[-1] = factual_lines[-1].replace("points to a real build-out", "looks like a real build-out")

    if not factual_lines:
        factual_lines.append("I pulled together a short research note for your team.")

    body_lines.extend(factual_lines[:2])
    body_lines.append("")
    anchor_citation = _claim_citation(claim_rows[0]["claim_id"]) if claim_rows else ""
    if segment_match == "segment_4_specialized_capability":
        body_lines.append(f"It looks like there may be a capability gap worth discussing {anchor_citation}".strip())
    elif segment_match == "segment_3_leadership_transition":
        body_lines.append(f"It looks like there may be a leadership transition window worth discussing {anchor_citation}".strip())
    else:
        body_lines.append(f"It looks like there may be a good reason to compare notes {anchor_citation}".strip())

    body_lines.append("Would you be open to a 20-minute discovery call next week?")
    body_lines.append("")
    body_lines.append("Best,")
    body_lines.append("Tenacious Consulting")

    body = "\n".join(body_lines)
    subject = f"Quick note for {company_name}"
    claim_ids = [row["claim_id"] for row in claim_rows if row.get("claim_id")]
    return {
        "channel": "email",
        "path": "commitment",
        "subject": subject,
        "body": body,
        "claim_ids": claim_ids,
    }
