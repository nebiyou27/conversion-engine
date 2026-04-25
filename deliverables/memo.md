# Tenacious Conversion Engine — Decision Memo
**To:** Tenacious CEO and CFO  **From:** Nebiyou Abebe  **Date:** 2026-04-25

## Executive Summary
We built an evidence-tiered outbound engine — public signals → cited claims → segment judgment → gated draft → CRM/calendar handoff — and used it to produce one finding worth acting on: **research-grounded outbound that bundles AI-maturity and competitor-gap language lost to a plain SDR opener by −9.38 pp (84.38% vs 93.75%, n=32/arm, p=0.09).** The delivery path is solved (0/20 stalled threads vs the 30–40% manual baseline), but claim-quality is not. **Recommendation: run a controlled 30-day Segment 2 A/B pilot at 150 qualified leads/week and $1,200/week, with generic copy as the control arm and grounded *timing-only* copy (funding, hiring, leadership transitions — no gap language) as the treatment.** Kill switch: if gap-condescension rate (P33) exceeds 5% over any rolling 100-email window, route to human queue.

## Headline Finding — and Why It Matters
The interesting result of this build is not that we shipped a stack. It is that the stack made a non-obvious failure mode legible: **more research is not automatically better outbound.** When we layered timing signals + AI maturity + capability-gap language together, the LLM judge simulating Segment 2 CTOs replied less, not more. Probe P33 in [probes/failure_taxonomy.md](../probes/failure_taxonomy.md) identifies this as *gap-condescension* — verified-but-socially-expensive claims that read as "we know your problem better than you do."

The second-order insight: **confidence is not the right axis for tone — sensitivity is.** A "verified" claim about a layoff or capability gap is still socially costly even when it is factually true. The mechanism that ships is the sensitivity axis on top of the confidence tier ([agent/claims/sensitivity.py](../agent/claims/sensitivity.py)), routing sensitive claim kinds to interrogative or human-review even at high confidence.

## My Bet
Grounded *timing-only* copy will beat generic by **≥5 pp** on real Segment 2 prospects within 30 days. If it does not, the research-grounding mechanism is decorative for cold outbound; Tenacious should run generic copy with a fast-acknowledgment layer only and use the engine as an evidence-collector for warm follow-ups instead. This is falsifiable in one pilot.

## Cost Per Qualified Lead
**Qualified lead:** a prospect with an actionable segment match whose draft clears citation, shadow, and forbidden-phrase gates.

Pilot operating envelope:

| Input | Weekly amount | Basis |
|---|---:|---|
| LLM + operator buffer | **$800** | pilot budget |
| Rig, enrichment, review overhead | **$400** | hosted-runner / API / reviewer allowance |
| **Total weekly budget** | **$1,200** | recommendation |
| Qualified leads | **150 / week** | pilot scope |

**Pilot CPQL = $1,200 / 150 = $8.00 per qualified lead** — below the $20 challenge envelope and well below a manual SDR touched-lead benchmark of ~$45–80. Sandbox ledger reconciliation: measured LLM spend across run artifacts is $0.022 total ([outputs/runs/](../outputs/runs/), [eval/ab_reply_rate_report.json](../eval/ab_reply_rate_report.json)) — proves cost logging works; not production economics.

## Speed-to-Lead Delta
**Stalled** = no outbound action within 300 seconds of inbound reply normalization. The live staff-sink latency run measured **0/20 stalled threads = 0.0%** ([eval/stall_rate_report.json](../eval/stall_rate_report.json)) versus the 30–40% manual baseline — a **−30 to −40 pp** delta. Caveat: synthetic prospects, not production traffic; this proves the delivery and normalization paths, not real-world recipient behavior.

## Reply-Rate A/B
Two first-touch variants, 32 trials per arm ([eval/ab_reply_rate_report.json](../eval/ab_reply_rate_report.json)):

| Variant | Definition | Replies | Reply rate |
|---|---|---:|---:|
| Signal-grounded | claim IDs + AI maturity + gap/timing signals | 27/32 | **84.38%** |
| Generic | standard SDR opener, no grounding | 30/32 | **93.75%** |

**Delta = −9.38 pp, p = 0.09.** Treat as suggestive, not conclusive. Critically, this does **not** isolate timing copy from gap copy — both were bundled in the treatment. The follow-up A/B is scoped, prompted, and tested as `timing_grounded` vs `generic` in [eval/ab_reply_rate.py](../eval/ab_reply_rate.py). It was not executed in this submission window: OpenRouter returned `403 Key limit exceeded (weekly limit)`. The harness runs on quota reset without code changes. Until that second report exists, the pilot recommendation is a learning design, not a claimed reply-rate lift.

## Pilot Scope
- **Segment:** Segment 2 mid-market restructuring — stall baseline and defensive-reply risk are most directly tied to this motion.
- **Volume:** 150 qualified leads/week for 4 weeks, split 50/50 between generic control and grounded timing-only treatment.
- **Budget:** $1,200/week ($800 LLM/operator + $400 enrichment/rig/review).
- **Success criterion:** treatment reaches ≥12% human-judged reply rate **and** beats control by ≥2 pp; stalled-thread rate stays at 0%; gap-condescension incidents stay <5% over any rolling 100-email review.
- **Expansion condition:** only add Segment 4 capability-gap copy after timing-only copy beats generic on real prospects.

## Asymmetric Cost of Being Wrong
Two ways the pilot can fail; one ruins the brand, the other costs SDR hours.

| Failure | Trigger | Cost |
|---|---|---:|
| **Gap-condescension reaches a Series C CTO** | P33 escapes the gate | ~1 lost $288K ACV deal per incident |
| **Timing copy is 2 pp below expectation** | Treatment underperforms control | ~30 wasted SDR hours / week |

The first is roughly **100× worse** than the second. That is why the kill switch is on P33, not on reply rate. A pilot that beats reply targets but ships one condescending email to a sophisticated buyer has lost, not won.

## Public-Signal Lossiness in AI Maturity
AI maturity scoring rides on public signals, so it has predictable failure modes:

**False positive — AI-washing Series B.** Public materials use AI language; no named AI leadership, no credible AI hiring, no operating maturity. Agent pitches Segment 4 capability help as if the need were established. Business impact: outreach reads inattentive or condescending, wastes the touch, damages brand with an engineering-generalist prospect.

**False negative — Silent Sophisticate.** Mature AI team, private repos, no public ML roles, no blog. Captured in [data/fixtures/companies/silent_sophisticate.json](../data/fixtures/companies/silent_sophisticate.json) — strong Series C, senior engineering hiring, zero public AI vocabulary. Agent under-scores AI maturity and skips Segment 4 pitch — leaves ACV on the table.

## Unresolved Failure
The mechanism does not fully solve **gap-condescension when multiple sensitive truths are combined.** Probe **P33** in [probes/probe_library.md](../probes/probe_library.md) measures **5/32 = 15.6% trigger rate** on signal-grounded A/B drafts — judge flagged layoff / AI-maturity / competitor-gap language as intrusive ([probes/failure_taxonomy.md](../probes/failure_taxonomy.md) line 23).

[probes/target_failure_mode.md](../probes/target_failure_mode.md) models the related defensive-reply failure at 3% of Segment 2 conversations × 50% deal-loss × $288K ACV = **$4.32M at-risk ACV per 1,000 leads.** At the pilot run-rate (150 leads/week): **30-day exposure ≈ $2.59M; annualized ≈ $33.7M.** Deploy anyway only with the kill switch: if wrong-signal rate exceeds 5% or P33 exceeds 5% in a rolling 100-email review, pause prospect contact and route drafts to human review.

## What Changes Monday Morning
For SDRs in the pilot: **stop drafting first-touch Segment 2 copy from scratch.** Review and approve gated drafts produced by the engine. Job shifts from drafting to adjudicating — fewer keystrokes, more judgment calls. For sales leadership: weekly review of P33 incidents and the 100-email rolling sample is the new operating ritual; the kill switch is theirs to pull, not ours.
