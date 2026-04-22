"""Crunchbase-shaped fixture loader. Emits one Fact per funding round."""
from __future__ import annotations

from datetime import datetime, timezone

from agent.evidence.schema import EvidenceFormatError, Fact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(section, *, company_id: str) -> list[Fact]:
    if section is None:
        return []
    if not isinstance(section, dict):
        raise EvidenceFormatError(
            f"crunchbase section must be a dict, got {type(section).__name__}"
        )

    round_data = section.get("funding_round")
    if round_data is None:
        return []
    if not isinstance(round_data, dict):
        raise EvidenceFormatError("crunchbase.funding_round must be a dict")

    required = ("round", "amount_usd", "announced_on", "source_url")
    missing = [k for k in required if k not in round_data]
    if missing:
        raise EvidenceFormatError(f"crunchbase.funding_round missing: {missing}")

    amount = round_data["amount_usd"]
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        raise EvidenceFormatError(
            f"crunchbase.funding_round.amount_usd must be numeric, got {type(amount).__name__}"
        )

    round_name = round_data["round"]
    announced_on = round_data["announced_on"]
    return [Fact(
        company_id=company_id,
        source_type="crunchbase",
        kind="funding_round",
        summary=f"Raised {round_name} (${amount / 1_000_000:.0f}M) on {announced_on}",
        payload={"round": round_name, "amount_usd": amount, "announced_on": announced_on},
        source_url=round_data["source_url"],
        retrieved_at=round_data.get("retrieved_at") or _now(),
    )]
