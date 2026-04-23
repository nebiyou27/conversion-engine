"""Segment classifier — deterministic 5-step ladder per seed/icp_definition.md.

Priority order (first match wins):
  1. layoff (120d) + fresh funding → segment_2
  2. new CTO/VP Eng (90d), headcount 50–500, no concurrent CFO/CEO → segment_3
  3. capability gap + AI maturity ≥ 2 → segment_4
  4. fresh funding (180d) → segment_1
  5. otherwise → abstain

Every step reads claims only (R2 — judgment never touches raw evidence).
The classifier returns a dict matching the hiring_signal_brief schema fields
``primary_segment_match`` and ``segment_confidence``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

# --- Constants from seed/icp_definition.md ---

SEGMENTS = (
    "segment_1_series_a_b",
    "segment_2_mid_market_restructure",
    "segment_3_leadership_transition",
    "segment_4_specialized_capability",
    "abstain",
)

LAYOFF_WINDOW_DAYS = 120
LEADERSHIP_WINDOW_DAYS = 90
FUNDING_WINDOW_DAYS = 180

S1_MIN_OPEN_ROLES = 5
S2_MIN_OPEN_ROLES = 3
S3_HEADCOUNT_MIN = 50
S3_HEADCOUNT_MAX = 500

S1_FUNDING_MIN_USD = 5_000_000
S1_FUNDING_MAX_USD = 30_000_000
S1_HEADCOUNT_MIN = 15
S1_HEADCOUNT_MAX = 80

S2_LAYOFF_MAX_PCT = 0.40
S1_LAYOFF_COOLDOWN_DAYS = 90
S1_LAYOFF_HEADCOUNT_PCT = 0.15

ABSTAIN_CONFIDENCE_THRESHOLD = 0.6


# --- Helpers ---

def _payload(claim: dict) -> dict:
    raw = claim.get("payload")
    if not raw:
        return {}
    return json.loads(raw) if isinstance(raw, str) else raw


def _is_actionable(claim: dict) -> bool:
    return claim["tier"] not in ("below_threshold",)


def _days_since(date_str: str | None, now: datetime) -> int | None:
    if not date_str:
        return None
    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def _claims_by_kind(claims: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for c in claims:
        out.setdefault(c["kind"], []).append(c)
    return out


def _open_role_count(claims: list[dict]) -> int:
    """Count distinct open engineering roles from hiring_surge claims."""
    for c in claims:
        if c["kind"] == "hiring_surge" and _is_actionable(c):
            p = _payload(c)
            return p.get("postings_count", 0)
    return 0


def _get_headcount(claims: list[dict]) -> int | None:
    """Extract headcount from company_metadata claim."""
    for c in claims:
        if c["kind"] == "company_metadata" and _is_actionable(c):
            p = _payload(c)
            hc = p.get("headcount")
            if hc is not None:
                return int(hc)
    return None


# --- Step classifiers ---

def _check_s2(by_kind: dict, now: datetime, open_roles: int) -> tuple[bool, float]:
    """Step 1: layoff (120d) + fresh funding → S2."""
    layoffs = [c for c in by_kind.get("layoff_event", []) if _is_actionable(c)]
    funding = [c for c in by_kind.get("funding_round", []) if _is_actionable(c)]

    if not layoffs or not funding:
        return False, 0.0

    # Check layoff within window
    layoff_recent = False
    for c in layoffs:
        p = _payload(c)
        age = _days_since(p.get("event_on"), now)
        if age is not None and age <= LAYOFF_WINDOW_DAYS:
            layoff_recent = True
            break

    if not layoff_recent:
        return False, 0.0

    # Check funding is actionable (any tier above below_threshold counts)
    funding_recent = any(_is_actionable(c) for c in funding)
    if not funding_recent:
        return False, 0.0

    # Must have at least S2_MIN_OPEN_ROLES open eng roles post-layoff
    if open_roles < S2_MIN_OPEN_ROLES:
        return False, 0.0

    # Confidence: both signals are strong
    confidence = 0.0
    signals_fired = 0
    total_signals = 3  # layoff, funding, open_roles
    if layoff_recent:
        signals_fired += 1
    if funding_recent:
        signals_fired += 1
    if open_roles >= S2_MIN_OPEN_ROLES:
        signals_fired += 1
    confidence = signals_fired / total_signals

    # Boost if both claims are verified/corroborated
    tier_bonus = sum(0.05 for c in layoffs + funding if c["tier"] in ("verified", "corroborated"))
    confidence = min(1.0, confidence + tier_bonus)

    return True, confidence


def _check_s3(
    by_kind: dict, now: datetime, headcount: int | None,
) -> tuple[bool, float]:
    """Step 2: new CTO/VP Eng (90d), headcount 50–500, no concurrent CFO/CEO."""
    leadership = [c for c in by_kind.get("leadership_change", []) if _is_actionable(c)]
    if not leadership:
        return False, 0.0

    cto_or_vpe = False
    concurrent_cfo_ceo = False

    for c in leadership:
        p = _payload(c)
        event = (p.get("event") or "").lower()
        age = _days_since(p.get("effective"), now)

        if age is not None and age <= LEADERSHIP_WINDOW_DAYS:
            if event in ("new_cto", "new_vp_engineering"):
                cto_or_vpe = True
            if event in ("new_cfo", "new_ceo"):
                concurrent_cfo_ceo = True

    if not cto_or_vpe:
        return False, 0.0

    # Disqualifier: concurrent CFO/CEO
    if concurrent_cfo_ceo:
        return False, 0.0

    # Headcount filter
    if headcount is not None and not (S3_HEADCOUNT_MIN <= headcount <= S3_HEADCOUNT_MAX):
        return False, 0.0

    # Confidence
    signals_fired = 1  # CTO/VP Eng confirmed
    total_signals = 2  # CTO + headcount
    if headcount is not None:
        signals_fired += 1

    confidence = signals_fired / total_signals
    # Boost for strong tier
    tier_bonus = sum(0.05 for c in leadership if c["tier"] in ("verified", "corroborated"))
    confidence = min(1.0, confidence + tier_bonus)

    return True, confidence


def _check_s4(
    by_kind: dict, ai_maturity_score: int | None,
) -> tuple[bool, float]:
    """Step 3: capability gap + AI maturity ≥ 2 → S4."""
    if ai_maturity_score is None or ai_maturity_score < 2:
        return False, 0.0

    # Need hiring evidence (capability gap proxy = they're hiring for roles
    # they can't fill, evidenced by hiring_surge)
    hiring = [c for c in by_kind.get("hiring_surge", []) if _is_actionable(c)]
    if not hiring:
        return False, 0.0

    confidence = 0.7  # base for ai_maturity ≥ 2 + hiring signal
    if ai_maturity_score >= 3:
        confidence += 0.1
    tier_bonus = sum(0.05 for c in hiring if c["tier"] in ("verified", "corroborated"))
    confidence = min(1.0, confidence + tier_bonus)

    return True, confidence


def _check_s1(
    by_kind: dict, now: datetime, open_roles: int, headcount: int | None,
) -> tuple[bool, float]:
    """Step 4: fresh funding (180d) → S1."""
    funding = [c for c in by_kind.get("funding_round", []) if _is_actionable(c)]
    if not funding:
        return False, 0.0

    funding_recent = False
    funding_amount = None
    funding_round = None
    for c in funding:
        p = _payload(c)
        age = _days_since(p.get("announced_on"), now)
        if age is not None and age <= FUNDING_WINDOW_DAYS:
            funding_recent = True
            funding_amount = p.get("amount_usd")
            funding_round = p.get("round", "").lower()
            break

    if not funding_recent:
        return False, 0.0

    # Disqualifier: layoff in last 90 days > 15% headcount → shifts to S2
    layoffs = [c for c in by_kind.get("layoff_event", []) if _is_actionable(c)]
    for c in layoffs:
        p = _payload(c)
        age = _days_since(p.get("event_on"), now)
        if age is not None and age <= S1_LAYOFF_COOLDOWN_DAYS:
            if headcount and p.get("headcount_cut"):
                pct = p["headcount_cut"] / headcount
                if pct > S1_LAYOFF_HEADCOUNT_PCT:
                    return False, 0.0

    # Confidence
    signals_fired = 1  # funding present
    total_signals = 3  # funding + open_roles + headcount
    if open_roles >= S1_MIN_OPEN_ROLES:
        signals_fired += 1
    if headcount is not None and S1_HEADCOUNT_MIN <= headcount <= S1_HEADCOUNT_MAX:
        signals_fired += 1

    confidence = signals_fired / total_signals
    tier_bonus = sum(0.05 for c in funding if c["tier"] in ("verified", "corroborated"))
    confidence = min(1.0, confidence + tier_bonus)

    return True, confidence


# --- Public API ---

def classify(
    claims: list[dict],
    *,
    now: datetime | None = None,
    ai_maturity_score: int | None = None,
) -> dict[str, Any]:
    """Run the 5-step segment ladder over a company's claims.

    Parameters
    ----------
    claims : list[dict]
        Claim rows (as returned by storage.db.get_claims).
    now : datetime, optional
        Override for deterministic testing.
    ai_maturity_score : int | None
        AI maturity score (0–3). Needed for S4 check. None = not yet scored.

    Returns
    -------
    dict with keys:
        primary_segment_match : str — one of SEGMENTS
        segment_confidence : float — [0.0, 1.0]
        rationale : str — human-readable explanation
        claim_ids : list[str] — claims that contributed
    """
    now = now or datetime.now(timezone.utc)
    by_kind = _claims_by_kind(claims)

    open_roles = _open_role_count(claims)
    headcount = _get_headcount(claims)

    # Collect contributing claim_ids from actionable claims
    actionable = [c for c in claims if _is_actionable(c)]
    claim_ids = [c["claim_id"] for c in actionable]

    # Step 1: S2
    match, conf = _check_s2(by_kind, now, open_roles)
    if match and conf >= ABSTAIN_CONFIDENCE_THRESHOLD:
        return {
            "primary_segment_match": "segment_2_mid_market_restructure",
            "segment_confidence": round(conf, 2),
            "rationale": "Layoff within 120d + fresh funding + engineering still hiring",
            "claim_ids": claim_ids,
        }

    # Step 2: S3
    match, conf = _check_s3(by_kind, now, headcount)
    if match and conf >= ABSTAIN_CONFIDENCE_THRESHOLD:
        return {
            "primary_segment_match": "segment_3_leadership_transition",
            "segment_confidence": round(conf, 2),
            "rationale": "New CTO/VP Eng within 90d, headcount 50–500, no concurrent CFO/CEO",
            "claim_ids": claim_ids,
        }

    # Step 3: S4
    match, conf = _check_s4(by_kind, ai_maturity_score)
    if match and conf >= ABSTAIN_CONFIDENCE_THRESHOLD:
        return {
            "primary_segment_match": "segment_4_specialized_capability",
            "segment_confidence": round(conf, 2),
            "rationale": "AI maturity ≥ 2 + active hiring signal (capability gap proxy)",
            "claim_ids": claim_ids,
        }

    # Step 4: S1
    match, conf = _check_s1(by_kind, now, open_roles, headcount)
    if match and conf >= ABSTAIN_CONFIDENCE_THRESHOLD:
        return {
            "primary_segment_match": "segment_1_series_a_b",
            "segment_confidence": round(conf, 2),
            "rationale": "Recent funding within 180d",
            "claim_ids": claim_ids,
        }

    # Step 5: abstain
    return {
        "primary_segment_match": "abstain",
        "segment_confidence": 0.0,
        "rationale": "No segment matched above confidence threshold",
        "claim_ids": claim_ids,
    }
