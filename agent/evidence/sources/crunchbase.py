"""Crunchbase-shaped fixture loader. Emits one Fact per funding round."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import requests

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


def parse_crunchbase_odm_record(record: dict[str, Any], *, company_id: str) -> list[Fact]:
    """Parse a Crunchbase ODM record into Facts."""
    if not isinstance(record, dict):
        raise EvidenceFormatError(f"crunchbase ODM record must be a dict, got {type(record).__name__}")
    return load({"funding_round": record}, company_id=company_id)


def lookup_company_odm(
    identifier: str,
    *,
    company_id: str | None = None,
    endpoint: str | None = None,
    session: requests.Session | None = None,
) -> list[Fact]:
    """Look up a company in a Crunchbase ODM-style endpoint and parse the response.

    The endpoint is configurable so the code can run against an approved service
    without embedding login logic or browser automation here.
    """
    url = endpoint
    if not url:
        raise RuntimeError("CRUNCHBASE_ODM_ENDPOINT is required for live lookup")

    requester = session or requests.Session()
    response = requester.get(f"{url.rstrip('/')}/{identifier}", timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Crunchbase lookup failed: {response.status_code} {response.text}")

    data = response.json()
    target_company_id = company_id or identifier
    if isinstance(data, list):
        facts: list[Fact] = []
        for item in data:
            facts.extend(parse_crunchbase_odm_record(item, company_id=target_company_id))
        return facts
    return parse_crunchbase_odm_record(data, company_id=target_company_id)
