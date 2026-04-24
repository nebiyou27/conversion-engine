# Probe Library

Each probe targets a failure mode that would reduce reviewer or prospect trust.
Expected behavior is either gate failure, abstention, or downgraded language.

| ID | Category | Probe | Expected behavior | Current coverage | observed_trigger_rate | business_cost |
|---|---|---|---|---|---|---|
| P01 | Citation coverage | Draft says "Acme raised $50M last week" without `{claim_id}`. | Citation gate fails. | `tests/test_citation_check.py` | not_measured | Brand trust loss from unsupported factual claims. |
| P02 | Hiring-signal over-claiming | Draft asks "Is Acme hiring three ML roles?" without `{claim_id}`. | Citation gate fails; question mood is not an exemption. | `tests/test_citation_check.py` | not_measured | Wrong signal can burn high-ACV Segment 2 accounts. |
| P03 | Citation coverage | Draft cites `{unknown-claim-id}`. | Citation gate fails unknown claim check. | gate tests pending | not_measured | Reviewer distrust and prospect-facing unsupported evidence. |
| P04 | Operational CTA | Draft asks "Would you be open to a 20-minute call next week?" without citation. | Citation gate passes this sentence. | `tests/test_citation_check.py` | not_measured | Overblocking would suppress legitimate scheduling asks. |
| P05 | Tier mood | Inferred hiring claim is written as "You are hiring rapidly." | Gate or review flags overconfident mood. | pending | not_measured | Overconfident outreach from weak evidence. |
| P06 | Tier mood | Verified funding claim is written with unsupported extra amount. | Citation/shadow review fails. | pending | not_measured | High-confidence wrong fact in first-touch email. |
| P07 | ICP misclassification | Stale funding claim is used in segment classification. | Segment classifier ignores below-threshold claim. | `tests/test_judgment.py` | not_measured | Wrong segment narrative and wasted SDR motion. |
| P08 | ICP misclassification | Recent large layoff and fresh funding both present. | Segment 2 takes priority over Segment 1. | `tests/test_judgment.py` | not_measured | Contradictory buying-window logic. |
| P09 | Signal reliability | Layoff CSV has no matching company row. | No layoff claim emitted. | `tests/test_signal_enrichment.py` | not_measured | False restructuring narrative. |
| P10 | Signal reliability | Matching CSV row has blank layoff count. | Row skipped; no invented headcount. | pending | not_measured | Invented layoff magnitude damages trust. |
| P11 | Signal reliability | CSV contains Meta and Acko; target is Meta. | Only Meta layoff facts emitted. | `tests/test_signal_enrichment.py` | not_measured | Company-entity collision. |
| P12 | Scheduling/channel safety | Prospect has no email reply and SMS is requested. | `SMSChannelError` before provider call. | `tests/test_sms_handler.py` | not_measured | Cold personal-device outreach risk. |
| P13 | Dual-control coordination | Prospect reply has been normalized. | SMS route may proceed to staff sink. | `tests/test_sms_handler.py` | not_measured | Missed warm handoff after prospect engagement. |
| P14 | Cost pathology | `ALLOW_REAL_PROSPECT_CONTACT=false`. | Email routes to `STAFF_SINK_EMAIL`. | `tests/test_email_handler.py` | not_measured | Accidental real-prospect contact during tests. |
| P15 | Cost pathology | `ALLOW_REAL_PROSPECT_CONTACT=false`. | SMS routes to `STAFF_SINK_PHONE_NUMBER`. | `tests/test_sms_handler.py` | not_measured | Accidental paid/provider send. |
| P16 | Provider reliability | Resend transient failure occurs. | Bounded retry then explicit `EmailSendError`. | `tests/test_email_handler.py` | not_measured | Silent send failure. |
| P17 | Provider reliability | Cal.com returns HTTP 500. | Retry as transient failure. | `tests/test_crm_calendar.py` | not_measured | Booking loss from transient calendar outage. |
| P18 | Provider reliability | Cal.com returns HTTP 400. | No retry; explicit booking error. | `tests/test_crm_calendar.py` | not_measured | Infinite retry/cost pathology. |
| P19 | Multi-thread leakage | Same booking event replayed twice. | One HubSpot booking update only. | `tests/test_crm_calendar.py` | not_measured | Duplicate CRM state and conflicting contact history. |
| P20 | Multi-thread leakage | Same inbound email event replayed. | Duplicate ignored. | `tests/test_email_handler.py` | not_measured | Duplicate outreach after webhook replay. |
| P21 | Webhook robustness | Email webhook lacks event type. | Handler returns malformed/error path. | `tests/test_email_handler.py` | not_measured | Broken downstream state transitions. |
| P22 | Provider reliability | `USE_HUBSPOT_MCP=true` with no access token. | Explicit configuration error. | pending | not_measured | Silent CRM write failure. |
| P23 | Provider reliability | MCP tool list lacks contact write tool. | Explicit `HubSpotMCPError`. | pending | not_measured | Wrong tool invocation or dropped CRM update. |
| P24 | AI maturity lossiness | LLM returns prose instead of JSON. | Parser raises `AiMaturityParseError`. | `tests/test_judgment.py` | not_measured | Segment 4 pitch based on malformed reasoning. |
| P25 | AI maturity lossiness | LLM returns score 5. | Parser rejects score. | `tests/test_judgment.py` | not_measured | Invalid maturity state contaminates routing. |
| P26 | AI maturity lossiness | LLM invents source URL not in claims. | Rubric forbids; review should flag. | pending | not_measured | False public-signal attribution. |
| P27 | Gap over-claiming | No peer evidence is available. | Output remains stub/draft, no gap claim in outreach. | `tests/test_judgment.py` | not_measured | Condescending or fabricated competitor critique. |
| P28 | ICP misclassification | New CTO and new CEO occur concurrently. | Segment 3 disqualified. | `tests/test_judgment.py` | not_measured | Leadership-transition false positive. |
| P29 | Thin evidence | No actionable claims exist. | Segment classifier abstains. | `tests/test_judgment.py` | not_measured | Prospect receives generic/unsupported outreach. |
| P30 | Fixture/live boundary | Synthetic run artifact is reviewed. | Artifact says `demo_mode: true` and AI maturity source is stub. | `tests/test_end_to_end_thread.py` | not_measured | Reviewer distrust from demo artifacts presented as production. |
| P31 | Tone drift | Offshore-perception reply says "we want to keep this in-house"; draft persists with cost angle. | Agent acknowledges preference and stops cost-pressure framing. | pending | not_measured | Brand-sensitive refusal mishandled. |
| P32 | Bench over-commitment | Brief says frontend; bench shows only backend; draft claims availability. | Gate fails unless a matching `bench_summary_id` supports the sentence. | pending | not_measured | Capacity claim creates delivery risk. |
| P33 | Gap over-claiming | Prospect CTO is ex-Google ML; gap brief recommends "adopt basic ML monitoring." | Gap language downgrades or abstains. | pending | not_measured | Condescension to sophisticated buyer. |
| P34 | Scheduling edge cases | Prospect is in Addis Ababa; booking slot shows 2 AM local. | Scheduling proposes local-business-hour options. | pending | not_measured | Meeting friction and perceived carelessness. |
| P35 | Multi-thread leakage | Two contacts at same company get different segment framing. | Shared company state keeps framing consistent or escalates to human queue. | pending | not_measured | Account-level inconsistency across stakeholders. |

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
