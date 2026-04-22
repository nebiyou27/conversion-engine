---
name: claim-audit
description: Audit an email draft for citation coverage and tier-mood compliance. Use when reviewing any outbound draft before it reaches the gate layer, or when validating that a generated email respects the epistemic contract.
---

# Claim Audit

Audit a draft email against the epistemic contract defined in CLAUDE.md.

## When to invoke

- Before any email draft is sent or shown as "final"
- When reviewing LLM output that contains factual claims
- When debugging why a gate check failed

## Audit procedure

For each sentence in the draft:

### Step 1 — Classify the sentence
- **Factual claim** (asserts something about the prospect's company, people, or state)
- **Meta statement** (greeting, closing, Tenacious self-description)
- **Question** (interrogative sentence seeking information)

Only factual claims require citations. Meta statements and questions do not.

### Step 2 — For each factual claim, verify
1. Is there a `{claim_id}` annotation or equivalent reference?
2. Does the claim_id exist in the claims layer for this prospect?
3. What tier does the cited claim carry?
4. Does the sentence mood match the tier?

### Step 3 — Tier-mood table

| Tier | Allowed mood | Example |
|---|---|---|
| Verified | Indicative | "Acme closed a $40M Series B on April 3." |
| Corroborated | Hedged indicative | "Based on TechCrunch, it looks like Acme recently raised." |
| Inferred | Interrogative only | "Are you scaling the platform team after the recent round?" |
| Below threshold | Not referenced | (sentence should not exist) |

### Step 4 — Report format

Produce a table:

| Sentence # | Type | Claim ID | Tier | Mood match | Verdict |
|---|---|---|---|---|---|

Then a verdict block:
- **PASS** — every factual sentence cites, every tier matches mood
- **FAIL** — list each violation with the specific fix

## What counts as a violation

- Factual claim with no citation → FAIL
- Citation to nonexistent claim_id → FAIL
- Indicative mood on a corroborated claim → FAIL (downgrade to hedged)
- Indicative or hedged on inferred claim → FAIL (convert to question)
- Any below-threshold claim referenced → FAIL (remove)
- Future-tense staff availability phrase → FAIL (flag R8)

## What counts as out of scope

- Style preferences (comma placement, word choice) — not this skill's job
- Strategic judgment (is this the right pitch?) — not this skill's job
- Tone (does this sound like Tenacious?) — that's shadow-review, not claim-audit

## Example invocation

User says: "Audit this draft."

Assistant reads the draft, runs the procedure above, produces the table + verdict. No rewriting unless user asks for fixes after seeing the audit.
