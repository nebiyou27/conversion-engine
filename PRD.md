# PRD - Conversion Engine

## What we're building

An AI agent that:

1. Finds tech companies likely to need Tenacious's engineering teams from
   public data.
2. Builds an evidence-backed research profile per prospect.
3. Sends personalized outreach whose factual claims are citation-traceable.
4. Responds within 5 minutes on the acknowledgment path and 15-60 minutes on
   the commitment path.
5. Books a discovery call via Cal.com, logged in HubSpot.

## Acceptance criteria - interim

- [ ] All 5 external service adapters present: Resend, HubSpot, Cal.com,
  Langfuse, tau2-Bench.
- [ ] Synthetic prospect flow: evidence -> claims -> judgment -> draft -> gate
  -> send path -> HubSpot path -> Cal.com booking path.
- [ ] tau2-Bench dev baseline captured with pass@1, 95% CI, cost/run, p50, and
  p95.
- [ ] p50/p95 latency from at least 20 synthetic or staff-sink interactions.
- [ ] Interim report and GitHub repo submitted.

## Acceptance criteria - final

- [ ] 30+ structured adversarial probes in `probes/probe_library.md`.
- [ ] `failure_taxonomy.md` grouping probes with trigger rates when measured.
- [ ] Target failure mode with business-cost derivation in Tenacious terms.
- [ ] Mechanism implemented for target failure and evaluated honestly.
- [ ] Honest comparison vs automated-optimization baseline when available.
- [ ] Decision memo with evidence-graph backing every numeric claim.
- [ ] Demo video under 8 minutes showing end-to-end flow including honesty
  guardrails in action.

## What we are not building

- Outreach to any real prospect without staff and Tenacious approval.
- SMS as a primary channel. Email comes first; SMS is only for warm leads.
- Brittle live scraping where a team-provided CSV or approved API exists.
- Features beyond the five-act deliverables.

## Hard constraints

- Every factual sentence in an email carries a `{claim_id}` annotation.
- Sentence mood is determined by claim tier, not by the LLM.
- Citation coverage is independent of mood; factual questions still need
  citations.
- No draft ships without passing all three gate checks.
- Below-threshold evidence is invisible to downstream layers.
- Total LLM + infra cost target is under $20/week.
