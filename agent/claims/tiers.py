"""Claim kinds, tier constants, and the primary/secondary lookup tables.

Primary/secondary is claim-relative, not source-relative: the same source_type
can be primary for one claim kind and secondary for another.
"""
from __future__ import annotations

VERIFIED = "verified"
CORROBORATED = "corroborated"
INFERRED = "inferred"
BELOW_THRESHOLD = "below_threshold"

ALL_TIERS = (VERIFIED, CORROBORATED, INFERRED, BELOW_THRESHOLD)

CLAIM_KINDS = ("funding_round", "hiring_surge", "leadership_change", "layoff_event")

PRIMARY: dict[str, frozenset[str]] = {
    "funding_round":     frozenset({"crunchbase"}),
    "hiring_surge":      frozenset({"job_posts"}),
    "leadership_change": frozenset({"leadership"}),
    "layoff_event":      frozenset({"layoffs"}),
}

SECONDARY: dict[str, frozenset[str]] = {
    "funding_round":     frozenset({"job_posts"}),
    "hiring_surge":      frozenset({"crunchbase"}),
    "leadership_change": frozenset(),
    "layoff_event":      frozenset(),
}

VERIFIED_MAX_AGE_DAYS = 7
CORROBORATED_MAX_AGE_DAYS = 30

HIRING_SURGE_MIN_POSTINGS = 3
HIRING_SURGE_WINDOW_DAYS = 30

# Event-date field name to inspect inside raw_payload, by source_type.
EVENT_DATE_KEY: dict[str, str] = {
    "crunchbase": "announced_on",
    "job_posts":  "posted_on",
    "leadership": "effective",
    "layoffs":    "event_on",
}
