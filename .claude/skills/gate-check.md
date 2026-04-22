---
name: gate-check
description: Run the full pre-send gate on an email draft — citation coverage, shadow-review adversarial pass, and forbidden-phrase regex. Use before any email is marked as sendable, or when validating that the gate layer itself works correctly.
---

# Gate Check

Run all three pre-send validators and produce a gate report.

## When to invoke

- Before any draft is marked sendable
- When validating the gate layer itself (unit testing)
- When a draft passes claim-audit but you want the full sign-off
- When building the gate_report.json for a run's output directory

## The three checks

### Check 1 — Citation coverage
Delegate to `claim-audit` skill. Every factual sentence must have a valid claim_id and tier-matching mood.

Pass condition: claim-audit returns PASS.

### Check 2 — Shadow review (adversarial second model)
Prompt a second model with:

> "You are an adversarial reviewer. Your job is to find ONE factual claim in this email that the cited evidence does not actually support. If every claim is supported, say 'NO VIOLATION FOUND.' Otherwise, quote the claim and explain why the citation does not support it."

Pass condition: response contains "NO VIOLATION FOUND" AND does not identify any unsupported claims.

Disagreement between claim-audit and shadow-review → human queue, not retry.

### Check 3 — Forbidden-phrase regex
Run regex filter against the draft. Fail on any match:

- `\b(engineers|team|resources)\s+(ready|available)\b`
- `\bavailability\s+(this week|next week|immediately)\b`
- `\bwe have\s+\w+\s+(engineers|developers|candidates)\s+for you\b`
- `\baggressive(ly)?\s+(hiring|scaling|growing)\b` — unless tier=verified AND ≥5 job posts cited
- `\bfalling behind\b|\bbehind your competitors\b` — flag for tone review
- Add more as the probe library discovers new patterns

Pass condition: zero regex matches OR matches occur only in contexts with sufficient citations (per rule metadata).

## Gate report format

Produce `gate_report.json`:

```json
{
  "draft_id": "<uuid>",
  "timestamp": "<ISO>",
  "checks": {
    "citation_coverage": {"status": "pass|fail", "violations": []},
    "shadow_review": {"status": "pass|fail", "verdict": "<raw model output>"},
    "forbidden_phrases": {"status": "pass|fail", "matches": []}
  },
  "overall": "pass|fail|human_queue",
  "routing": "send | human_review | reject"
}
```

## Routing logic

| citation | shadow | phrases | routing |
|---|---|---|---|
| pass | pass | pass | send |
| fail | any | any | reject |
| any | fail | any | reject |
| pass | pass | fail | reject |
| pass | disagrees | pass | human_review |

Note: shadow-review *disagreement* (flags a claim that claim-audit thought was fine) routes to human, not automatic reject. That disagreement data is valuable for calibration over time (but is NOT itself a reliability metric — see CLAUDE.md Section 2 pushback).

## Never do

- Retry after gate failure with the same draft
- Silently weaken a claim to make it pass
- Skip shadow-review to save tokens — it's the one check that catches what citation-audit misses
- Treat shadow-review agreement as positive evidence of correctness — it's a filter, not a metric

## Cost note

Shadow-review doubles LLM cost per draft. Account for this in the $20/week budget. The cost is not optional; it is the price of the brand-safety guarantee.

## Example invocation

User says: "Gate-check this draft."

Assistant runs all three checks, produces the JSON report, and states the routing decision. If any check fails, identifies the specific fix needed — does not attempt the fix unless asked.
