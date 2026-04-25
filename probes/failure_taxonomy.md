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

## Key Findings

**Highest observed incident rate:** P24 (AI maturity empty JSON) at 43% in tau2 thinking-model evaluation. Fix: enforce strict JSON schema in prompt + abstain object for low-confidence cases.

**Highest business-risk rate:** P33 (gap-condescension) at 15.6% in signal-grounded outreach. Fix: sensitivity axis already implemented in `agent/claims/sensitivity.py` — needs to gate all 4 sensitive claim kinds before draft generation, not just flag them.

**Confirmed working at 0% incident rate:** citation gate, staff-sink routing, replay protection, entity collision filtering, segment priority logic.

## Target Failure

The selected target is **signal over-claiming under defensive replies**. See
`probes/target_failure_mode.md` for the ACV arithmetic, rejected alternatives,
and why this failure is the best mechanism target.
