# Methodology Notes

## Claim Tiers

Claim tiering is deterministic and implemented in `agent/claims/confidence.py`.

| Tier | Evidence contract | Output posture |
|---|---|---|
| `verified` | At least two independent primary URLs and event age <= 7 days | Indicative language allowed |
| `corroborated` | At least one primary URL plus one secondary URL and event age <= 30 days | Hedged indicative language |
| `inferred` | Single primary signal within the freshness window, or secondary-only signal | Interrogative language only |
| `below_threshold` | Stale or insufficient evidence | Persisted for audit, not actionable downstream |

Citation coverage is independent of mood. A question can still contain factual
content, and factual content still needs a `{claim_id}`.

## Deterministic Segment Ladder

The segment classifier is deterministic and first-match-wins. It reads claim
rows only; raw evidence is not used by the judgment layer.

1. Recent layoff within 120 days + actionable funding + at least 3 open roles:
   `segment_2_mid_market_restructure`.
2. New CTO or VP Engineering within 90 days + headcount 50-500 + no concurrent
   CEO/CFO transition: `segment_3_leadership_transition`.
3. AI maturity score >= 2 + actionable hiring-surge claim:
   `segment_4_specialized_capability`.
4. Funding within 180 days: `segment_1_series_a_b`.
5. Otherwise: `abstain`.

A segment is returned only when confidence is at least `0.6`.

## AI Maturity

The real AI maturity path is `agent/judgment/ai_maturity.py`, which prompts an
LLM with the rubric in `agent/prompts/ai_maturity_rubric.md` and validates a
structured JSON response. Parser and validation behavior are tested without
network calls.

The synthetic thread in `agent/core.py` currently uses a hardcoded demo AI
maturity response. Run artifacts label this as `source:
"hardcoded_demo_stub"` so it cannot be mistaken for a real LLM judgment.

## Layoff Data

Layoff evidence should use the team-provided CSV artifact when available. The
parser accepts the team headers (`Company`, `Laid_Off_Count`, `Date`, `Source`)
and filters rows by exact normalized company name. Blank layoff counts are
skipped rather than guessed.

## Known Limitations

- Crunchbase live lookup requires an approved endpoint.
- Leadership detection normalizes input but has no live feed configured.
- Competitor gap judgment is a schema-valid stub unless peer evidence is
  supplied.
- The synthetic thread is an internal pipeline smoke test, not a fully live
  provider-backed run.
