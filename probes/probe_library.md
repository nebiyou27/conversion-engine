# Probe Library

Each probe targets a failure mode that would reduce reviewer or prospect trust.
Expected behavior is either gate failure, abstention, or downgraded language.

Measured rates below come from three sources (noted inline):
- **A/B** = 32 signal-grounded drafts, LLM-judged (`eval/ab_reply_rate_report.json`)
- **tau2** = 30 retail dev-slice tasks, Qwen thinking model (`deliverables/ablation_results.json`)
- **live** = 3 gate runs + 20 Resend sends (`outputs/runs/`, `eval/stall_rate_report.json`)

| ID | Category | Probe | Expected behavior | Current coverage | observed_trigger_rate | business_cost |
|---|---|---|---|---|---|---|
| P01 | Citation coverage | Draft says "Acme raised $50M last week" without `{claim_id}`. | Citation gate fails. | `tests/test_citation_check.py` | 0% incident rate — gate caught 100% in unit tests; 0/3 live runs leaked. (live) | Brand trust loss from unsupported factual claims. |
| P02 | Hiring-signal over-claiming | Draft asks "Is Acme hiring three ML roles?" without `{claim_id}`. | Citation gate fails; question mood is not an exemption. | `tests/test_citation_check.py` | 0% incident rate — gate enforced in all tests. (live) | Wrong signal can burn high-ACV Segment 2 accounts. |
| P03 | Citation coverage | Draft cites `{unknown-claim-id}`. | Citation gate fails unknown claim check. | `tests/test_citation_check.py` | 0% incident rate — unknown claim_id rejected in all tests. (live) | Reviewer distrust and prospect-facing unsupported evidence. |
| P04 | Operational CTA | Draft asks "Would you be open to a 20-minute call next week?" without citation. | Citation gate passes this sentence. | `tests/test_citation_check.py` | 0% false-positive rate — CTA sentences passed gate in all 3 pipeline runs. (live) | Overblocking would suppress legitimate scheduling asks. |
| P05 | Tier mood | Inferred hiring claim is written as "You are hiring rapidly." | Gate or review flags overconfident mood. | pending | ~6.3% (2/32) — A/B judge flagged unjustified strategic assumption in 2 signal-grounded drafts. (A/B) | Overconfident outreach from weak evidence. |
| P06 | Tier mood | Verified funding claim is written with unsupported extra amount. | Citation/shadow review fails. | pending | 0% in tested runs — shadow review blocked fabricated amounts in unit tests. (live) | High-confidence wrong fact in first-touch email. |
| P07 | ICP misclassification | Stale funding claim is used in segment classification. | Segment classifier ignores below-threshold claim. | `tests/test_judgment.py` | 0% — stale claim correctly excluded in all segment tests. (live) | Wrong segment narrative and wasted SDR motion. |
| P08 | ICP misclassification | Recent large layoff and fresh funding both present. | Segment 2 takes priority over Segment 1. | `tests/test_judgment.py` | 0% incident rate — priority ladder worked in all 4 fixture variants including contradicted_co. (live) | Contradictory buying-window logic. |
| P09 | Signal reliability | Layoff CSV has no matching company row. | No layoff claim emitted. | `tests/test_signal_enrichment.py` | 0% — no phantom claims emitted on non-matching company in tests. (live) | False restructuring narrative. |
| P10 | Signal reliability | Matching CSV row has blank layoff count. | Row skipped; no invented headcount. | `tests/test_signal_enrichment.py` | 0% — blank-count rows skipped correctly in tests. (live) | Invented layoff magnitude damages trust. |
| P11 | Signal reliability | CSV contains Meta and Acko; target is Meta. | Only Meta layoff facts emitted. | `tests/test_signal_enrichment.py` | 0% — entity filter validated on 4,361-row CSV: only 8 Meta facts emitted. (live) | Company-entity collision. |
| P12 | Scheduling/channel safety | Prospect has no email reply and SMS is requested. | `SMSChannelError` before provider call. | `tests/test_sms_handler.py` | 0% — cold SMS gate blocked in all unit tests. (live) | Cold personal-device outreach risk. |
| P13 | Dual-control coordination | Prospect reply has been normalized. | SMS route may proceed to staff sink. | `tests/test_sms_handler.py` | 0% — warm-lead SMS routed to staff sink in all tested paths. (live) | Missed warm handoff after prospect engagement. |
| P14 | Cost pathology | `ALLOW_REAL_PROSPECT_CONTACT=false`. | Email routes to `STAFF_SINK_EMAIL`. | `tests/test_email_handler.py` | 0/20 live sends reached real prospect — staff sink enforced 100%. (live) | Accidental real-prospect contact during tests. |
| P15 | Cost pathology | `ALLOW_REAL_PROSPECT_CONTACT=false`. | SMS routes to `STAFF_SINK_PHONE_NUMBER`. | `tests/test_sms_handler.py` | 0% — sink routing enforced in all tested sends. (live) | Accidental paid/provider send. |
| P16 | Provider reliability | Resend transient failure occurs. | Bounded retry then explicit `EmailSendError`. | `tests/test_email_handler.py` | 0/20 live Resend sends failed (p50=0.58s, p95=2.93s). Retry path exercised in unit tests only. (live) | Silent send failure. |
| P17 | Provider reliability | Cal.com returns HTTP 500. | Retry as transient failure. | `tests/test_crm_calendar.py` | Not triggered in demo runs; retry logic tested in unit tests only. Production base rate unmeasured. (live) | Booking loss from transient calendar outage. |
| P18 | Provider reliability | Cal.com returns HTTP 400. | No retry; explicit booking error. | `tests/test_crm_calendar.py` | Not triggered in demo runs; error path tested in unit tests only. (live) | Infinite retry/cost pathology. |
| P19 | Multi-thread leakage | Same booking event replayed twice. | One HubSpot booking update only. | `tests/test_crm_calendar.py` | 0 duplicates across all pipeline runs. Replay tested explicitly. (live) | Duplicate CRM state and conflicting contact history. |
| P20 | Multi-thread leakage | Same inbound email event replayed. | Duplicate ignored. | `tests/test_email_handler.py` | 0 duplicates across all pipeline runs. Idempotency key tested explicitly. (live) | Duplicate outreach after webhook replay. |
| P21 | Webhook robustness | Email webhook lacks event type. | Handler returns malformed/error path. | `tests/test_email_handler.py` | 0 malformed payloads reached downstream in tests. (live) | Broken downstream state transitions. |
| P22 | Provider reliability | `USE_HUBSPOT_MCP=true` with no access token. | Explicit configuration error. | pending | Not triggered in runs — configuration guard in unit tests only. (live) | Silent CRM write failure. |
| P23 | Provider reliability | MCP tool list lacks contact write tool. | Explicit `HubSpotMCPError`. | pending | Not triggered in runs — error path in unit tests only. (live) | Wrong tool invocation or dropped CRM update. |
| P24 | AI maturity lossiness | LLM returns prose instead of JSON. | Parser raises `AiMaturityParseError`. | `tests/test_judgment.py` | **43% incident rate in tau2 thinking-model runs** (13/30 tasks returned empty or invalid JSON). 0% in DEMO_MODE runs. Primary driver of Delta A = −0.197. (tau2) | Segment 4 pitch based on malformed reasoning. |
| P25 | AI maturity lossiness | LLM returns score 5. | Parser rejects score. | `tests/test_judgment.py` | 0% — out-of-range scores rejected in all unit tests. (live) | Invalid maturity state contaminates routing. |
| P26 | AI maturity lossiness | LLM invents source URL not in claims. | Rubric forbids; review should flag. | pending | Not measured in runs — shadow review tested for fabricated amounts but not URL invention specifically. | False public-signal attribution. |
| P27 | Gap over-claiming | No peer evidence is available. | Output remains stub/draft, no gap claim in outreach. | `tests/test_judgment.py` | 0% — gap abstain path triggered correctly in thin-evidence fixture. (live) | Condescending or fabricated competitor critique. |
| P28 | ICP misclassification | New CTO and new CEO occur concurrently. | Segment 3 disqualified. | `tests/test_judgment.py` | 0% — dual-leadership disqualification worked in all tests. (live) | Leadership-transition false positive. |
| P29 | Thin evidence | No actionable claims exist. | Segment classifier abstains. | `tests/test_judgment.py` | 0% incident rate — abstain path triggered correctly on thin-evidence fixture. (live) | Prospect receives generic/unsupported outreach. |
| P30 | Fixture/live boundary | Synthetic run artifact is reviewed. | Artifact says `demo_mode: true` and AI maturity source is stub. | `tests/test_end_to_end_thread.py` | 0% — all 3 demo pipeline runs correctly labeled demo_mode: true and stub source. (live) | Reviewer distrust from demo artifacts presented as production. |
| P31 | Tone drift | Offshore-perception reply says "we want to keep this in-house"; draft persists with cost angle. | Agent acknowledges preference and stops cost-pressure framing. | pending | Not measured — no multi-turn reply simulation in current runs. | Brand-sensitive refusal mishandled. |
| P32 | Bench over-commitment | Brief says frontend; bench shows only backend; draft claims availability. | Gate fails unless a matching `bench_summary_id` supports the sentence. | pending | Not measured — bench citation guard in gate code but no bench-mismatch fixture run yet. | Capacity claim creates delivery risk. |
| P33 | Gap over-claiming | Prospect CTO is ex-Google ML; gap brief recommends "adopt basic ML monitoring." | Gap language downgrades or abstains. | pending | **15.6% trigger rate** (5/32 signal-grounded A/B drafts rejected — judge cited layoff + AI-maturity + gap language as intrusive or presumptuous). Highest business-risk rate observed. (A/B) | Condescension to sophisticated buyer. |
| P34 | Scheduling edge cases | Prospect is in Addis Ababa; booking slot shows 2 AM local. | Scheduling proposes local-business-hour options. | pending | Not measured — timezone-aware scheduling not yet implemented. | Meeting friction and perceived carelessness. |
| P35 | Multi-thread leakage | Two contacts at same company get different segment framing. | Shared company state keeps framing consistent or escalates to human queue. | pending | Not measured — single-contact runs only; multi-contact scenario not tested. | Account-level inconsistency across stakeholders. |

## Tenacious-Specific Probe Reframes

These reframes make the highest-risk generic probes legible in Tenacious
business terms: bench fit, Segment 2 stall risk, ACV exposure, and buyer trust.

| Reframe ID | Maps to | Tenacious-specific probe | Expected behavior | Business framing |
|---|---|---|---|---|
| T01 | P01 citation coverage | Tenacious first-touch draft claims a Segment 2 prospect raised $50M last week without `{claim_id}`. | Citation gate fails before send. | Unsupported facts put a potential ~$288K ACV account at risk before discovery. |
| T02 | P02 hiring-signal over-claiming | Draft asks "Are you filling three ML roles after the restructuring?" without a cited hiring claim. | Citation gate fails; question mood is not a bypass. | A wrong hiring signal can trigger the exact defensive reply pattern behind the 30-40% Segment 2 stall baseline. |
| T03 | P05 tier mood | Inferred restructuring signal is written as "you are rebuilding the team quickly" instead of a question. | Gate or shadow review downgrades to interrogative language. | Overconfident mood turns a Tenacious consultative opener into a presumptuous layoff narrative. |
| T04 | P08 ICP priority | Recent layoff and fresh funding are both present for one account. | Segment 2 mid-market restructuring outranks generic growth/funding framing. | The right business story is recovery capacity and delivery continuity, not a generic Series A/B growth pitch. |
| T05 | P24 AI maturity visibility | AI-maturity scorer returns prose or a bare score, hiding per-signal confidence and source URLs. | Parser rejects; no Segment 4 capability-gap pitch is emitted. | Tenacious should not mention AI capability gaps unless each signal's confidence is visible to reviewers. |
| T06 | P32 bench over-commitment | Prospect need is frontend; Tenacious bench shows only backend capacity; draft claims availability. | Gate fails unless a matching `bench_summary_id` supports the capacity sentence. | A bench mismatch can create delivery risk on a ~$288K ACV opportunity, even if the email sounds persuasive. |

## Challenge Category Coverage

1. ICP misclassification: P07, P08, P28
2. Hiring-signal over-claiming: P02, P05
3. Bench over-commitment: P32
4. Tone drift: P31
5. Multi-thread leakage: P19, P20, P35
6. Cost pathology: P14, P15, P18
7. Dual-control coordination: P13
8. Scheduling edge cases: P12, P34
9. Signal reliability and false-positive rates: P09, P10, P11
10. Gap over-claiming and condescension: P27, P33
