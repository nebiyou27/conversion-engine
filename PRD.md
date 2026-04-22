# PRD — Conversion Engine

## What we're building

An AI agent that:
1. Finds tech companies likely to need Tenacious's engineering teams (from public data).
2. Builds an evidence-backed research profile per prospect.
3. Sends personalized outreach whose factual claims are citation-traceable.
4. Responds within 5 minutes on the acknowledgment path and 15–60 minutes on the commitment path.
5. Books a discovery call via Cal.com, logged in HubSpot.

## Acceptance criteria (Wed Apr 22 interim)

- [ ] All 5 external services connected with smoke tests passing: Resend, HubSpot, Cal.com, Langfuse, τ²-Bench
- [ ] End-to-end flow: one synthetic prospect → evidence → claims → judgment → draft → gate → send → HubSpot → Cal.com booking link
- [ ] τ²-Bench dev baseline captured (5-trial pass@1, 95% CI, cost/run, p50/p95)
- [ ] p50/p95 latency from ≥20 synthetic interactions
- [ ] Interim PDF report + GitHub repo submitted by 21:00 UTC

## Acceptance criteria (Sat Apr 25 final)

- [ ] 30+ structured adversarial probes in `probes/probe_library.md`
- [ ] `failure_taxonomy.md` grouping probes with trigger rates
- [ ] `target_failure_mode.md` with business-cost derivation in Tenacious terms
- [ ] Mechanism implemented for target failure; Delta A positive with 95% CI separation (p < 0.05)
- [ ] Honest comparison vs automated-optimization baseline (Delta B)
- [ ] 2-page decision memo with evidence-graph backing every numeric claim
- [ ] Demo video (≤8 min) showing end-to-end flow including honesty guardrails in action

## What we are NOT building

- Real scraping against live data sources (fixtures suffice for the week; real integrations are post-approval)
- SMS as a primary channel (email first; SMS only for warm leads who reply)
- Outreach to any real prospect (staff sink only, gated by `ALLOW_REAL_PROSPECT_CONTACT`)
- Features beyond the five-act deliverables

## Hard constraints (from CLAUDE.md)

- Every factual sentence in an email carries a `{claim_id}` annotation
- Sentence mood is determined by claim tier, not by the LLM
- No draft ships without passing all three gate checks
- Below-threshold evidence is invisible to downstream layers
- Total LLM + infra cost under $20/week
