# Failure Taxonomy

This taxonomy groups the probe library by the business cost of the failure.
Trigger rates are pending evaluation runs; until then, they are marked
`not_measured`.

| Category | Probes | Business cost | Desired mechanism | Trigger rate |
|---|---|---|---|---|
| Unsupported factual claim | P01, P02, P03, P06 | Prospect trust loss; brand risk for Tenacious | Citation gate and shadow review | not_measured |
| Mood/tier mismatch | P05, P07 | Overconfident outreach from weak evidence | Claim tier controls output posture | not_measured |
| Contradictory buying-window logic | P08, P28, P29 | Wrong ICP narrative and poor targeting | Deterministic segment priority ladder | not_measured |
| Layoff data quality | P09, P10, P11 | False restructuring narrative | Company-filtered CSV ingestion and skip incomplete rows | not_measured |
| Channel safety | P12, P13, P14, P15 | Regulatory and trust risk from cold personal-device outreach | Warm-lead SMS gate and staff-sink routing | not_measured |
| Provider reliability | P16, P17, P18, P22, P23 | Silent operational failure | Explicit adapters, bounded retries, configuration errors | not_measured |
| Replay safety | P19, P20 | Duplicate CRM writes or duplicate outreach | Idempotency keys | not_measured |
| Webhook robustness | P21 | Broken downstream state transitions | Payload validation | not_measured |
| AI maturity validity | P24, P25, P26 | Segment 4 pitch based on malformed or invented reasoning | Structured parser and rubric constraints | not_measured |
| Stub leakage | P27, P30 | Reviewer distrust from demo artifacts presented as production | Explicit stub/demo labels in artifacts | not_measured |

## Target Failure

The selected target is **signal over-claiming under defensive replies**. See
`probes/target_failure_mode.md` for the ACV arithmetic, rejected alternatives,
and why this failure is the best mechanism target.
