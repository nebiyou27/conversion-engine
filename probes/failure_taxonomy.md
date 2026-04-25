# Failure Taxonomy

This taxonomy groups the probe library by the business cost of the failure.
Trigger rates are drawn from three measurement sources:

- **A/B eval** — 32 signal-grounded + 32 generic drafts, LLM-judged reply rate (`eval/ab_reply_rate_report.json`)
- **tau2 retail** — 30 dev-slice tasks, 1 trial each, Qwen thinking model (`deliverables/ablation_results.json`)
- **Live pipeline** — 3 end-to-end gate runs + 20 Resend latency sends (`outputs/runs/`, `eval/stall_rate_report.json`)

"Gate catch rate" = mechanism caught the failure before output. "Incident rate" = failure reached output uncaught.

| Category | Probes | Business cost | Desired mechanism | Trigger rate |
|---|---|---|---|---|
| Unsupported factual claim | P01, P02, P03, P06 | Prospect trust loss; brand risk for Tenacious | Citation gate and shadow review | Gate catch rate: 100% in unit tests (n=141 passing). Incident rate: 0/3 live pipeline runs leaked an uncited claim. Base rate in real outreach: not yet measured at scale. |
| Mood/tier mismatch | P05, P07 | Overconfident outreach from weak evidence | Claim tier controls output posture | P05 implicated in ~2/32 (6.3%) signal-grounded A/B failures where judge flagged unjustified strategic assumption. P07 blocked in all segment-classifier tests. |
| Contradictory buying-window logic | P08, P28, P29 | Wrong ICP narrative and poor targeting | Deterministic segment priority ladder | 0% incident rate — Segment 2 correctly outranked Segment 1 in all 4 fixture variants, including contradicted_co. P29 abstain path triggered correctly on thin-evidence fixture. |
| Layoff data quality | P09, P10, P11 | False restructuring narrative | Company-filtered CSV ingestion; skip incomplete rows | 0% incident rate across all tested inputs. P11 entity-collision validated: 4,361-row Meta+Acko CSV correctly emits only Meta facts when `company_name="Meta"` (8 facts, Reuters/NYT/SFChronicle sources). |
| Channel safety | P12, P13, P14, P15 | Regulatory and trust risk from cold personal-device outreach | Warm-lead SMS gate and staff-sink routing | 0/20 live Resend sends reached a real prospect — staff-sink enforced 100%. SMS cold-outreach guard blocked correctly in unit tests. |
| Provider reliability | P16, P17, P18, P22, P23 | Silent operational failure | Explicit adapters, bounded retries, configuration errors | P16: 0/20 live Resend sends failed (p50=0.58s, p95=2.93s). P17/P18: not triggered in demo runs. Retry and error-path logic exercised in unit tests only — production base rate unmeasured. |
| Replay safety | P19, P20 | Duplicate CRM writes or duplicate outreach | Idempotency keys | 0 duplicates across all pipeline runs. Replay explicitly tested in `tests/test_crm_calendar.py` and `tests/test_email_handler.py`. |
| Webhook robustness | P21 | Broken downstream state transitions | Payload validation | 0 malformed payloads reached downstream state in tests. Validated in `tests/test_email_handler.py`. |
| AI maturity validity | P24, P25, P26 | Segment 4 pitch based on malformed or invented reasoning | Structured parser and rubric constraints | **P24: 43% incident rate in tau2 thinking-model runs** (13/30 tasks returned empty or invalid JSON; scored as failure). 0% in DEMO_MODE pipeline runs where stub is used. Primary driver of Delta A = −0.197. |
| Gap over-claiming and condescension | P27, P33 | Burns high-value accounts; condescending to sophisticated buyers | Sensitivity axis routes sensitive claims to interrogative or human queue | **P33: 15.6% trigger rate** (5/32 signal-grounded A/B drafts rejected — judge cited layoff + AI-maturity + competitor-gap language as intrusive or presumptuous). Highest-priority mechanism gap. |
| Stub leakage | P30 | Reviewer distrust from demo artifacts presented as production | Explicit stub/demo labels in all artifacts | 0% — all 3 demo pipeline runs correctly set `demo_mode: true` and labeled AI maturity source as stub. |

## Aggregate Trigger Rates

Numbers below aggregate across all measurement sources (A/B n=32 signal-grounded, tau2 n=30 retail dev-slice, live n=3 pipeline runs + n=20 Resend sends, plus 150 passing unit tests).

### By measurement source

| Source | Sample size | Probes measured | Incident rate (failures uncaught) | Gate catch rate (mechanism worked) |
|---|---|---|---|---|
| A/B signal-grounded outreach | 32 drafts | P05, P27, P33 | 5/32 = 15.6% (gap-condescension) + 2/32 = 6.3% (tier mood) | 25/32 = 78.1% drafts judged reply-worthy |
| tau2 retail dev-slice | 30 tasks | P24 | 13/30 = 43.3% (empty JSON on hard tasks) | 0% — these are unhandled provider errors |
| Live pipeline runs | 3 end-to-end | P01–P04, P14, P30 | 0/3 = 0% leakage | 100% gate enforcement |
| Live Resend sends | 20 sends | P14, P15, P16 | 0/20 = 0% reached real prospect | 100% sink routing |
| Unit tests | 150 passing | 28 of 35 probes | 0% in tested paths | Every test exercises the catch path |

### By failure category (incident rate where measured)

| Category | Combined incident rate | Sample basis |
|---|---|---|
| AI maturity validity (P24) | **43.3%** | tau2 thinking-model, n=30 |
| Gap over-claiming (P33) | **15.6%** | A/B signal-grounded, n=32 |
| Tier-mood mismatch (P05) | **6.3%** | A/B signal-grounded, n=32 |
| All other measured categories | **0%** | live runs + tests |

### Coverage state

- **28 of 35 probes** have at least one measured rate or test-path validation.
- **7 probes** are scoped but unmeasured (P22, P23, P26, P31, P32, P34, P35) — they cover scenarios that the demo run cannot reach (multi-contact, timezone, multi-turn, MCP errors, bench mismatch).
- **2 probes** drove the only material incidents observed: P24 and P33. Together they account for 100% of observed Δ-A degradation and 100% of A/B reply-rate loss.

## Key Findings

**Highest observed incident rate:** P24 (AI maturity empty JSON) at 43.3% in tau2 thinking-model evaluation. Fix: enforce strict JSON schema in prompt + abstain object for low-confidence cases.

**Highest business-risk rate:** P33 (gap-condescension) at 15.6% in signal-grounded outreach. Fix: sensitivity axis already implemented in `agent/claims/sensitivity.py` — needs to gate all 4 sensitive claim kinds before draft generation, not just flag them.

**Confirmed working at 0% incident rate:** citation gate, staff-sink routing, replay protection, entity collision filtering, segment priority logic, SMS warm-lead gate.

**Production-audit posture:** The two measured failure modes are concentrated in non-deterministic LLM paths (P24, P33). All deterministic mechanisms (gates, routers, classifiers) have 0% measured incident rate. This is the right shape for a system that wants to put a hard ceiling on trust-loss events.

## Target Failure

The selected target is **signal over-claiming under defensive replies**. See
`probes/target_failure_mode.md` for the ACV arithmetic, rejected alternatives,
and why this failure is the best mechanism target.
