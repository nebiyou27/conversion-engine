# Probe Library

Each probe targets a failure mode that would reduce reviewer or prospect trust.
Expected behavior is either gate failure, abstention, or downgraded language.

| ID | Category | Probe | Expected behavior | Current coverage |
|---|---|---|---|---|
| P01 | Citation coverage | Draft says "Acme raised $50M last week" without `{claim_id}`. | Citation gate fails. | `tests/test_citation_check.py` |
| P02 | Citation coverage | Draft asks "Is Acme hiring three ML roles?" without `{claim_id}`. | Citation gate fails; question mood is not an exemption. | `tests/test_citation_check.py` |
| P03 | Citation coverage | Draft cites `{unknown-claim-id}`. | Citation gate fails unknown claim check. | gate tests pending |
| P04 | Operational CTA | Draft asks "Would you be open to a 20-minute call next week?" without citation. | Citation gate passes this sentence. | `tests/test_citation_check.py` |
| P05 | Tier mood | Inferred hiring claim is written as "You are hiring rapidly." | Gate or review flags overconfident mood. | pending |
| P06 | Tier mood | Verified funding claim is written with unsupported extra amount. | Citation/shadow review fails. | pending |
| P07 | Below threshold | Stale funding claim is used in segment classification. | Segment classifier ignores below-threshold claim. | `tests/test_judgment.py` |
| P08 | Layoff contradiction | Recent large layoff and fresh funding both present. | Segment 2 takes priority over Segment 1. | `tests/test_judgment.py` |
| P09 | Layoff absence | Layoff CSV has no matching company row. | No layoff claim emitted. | `tests/test_signal_enrichment.py` |
| P10 | Layoff data quality | Matching CSV row has blank layoff count. | Row skipped; no invented headcount. | pending |
| P11 | Company filter | CSV contains Meta and Acko; target is Meta. | Only Meta layoff facts emitted. | `tests/test_signal_enrichment.py` |
| P12 | Cold SMS | Prospect has no email reply and SMS is requested. | `SMSChannelError` before provider call. | `tests/test_sms_handler.py` |
| P13 | Warm SMS | Prospect reply has been normalized. | SMS route may proceed to staff sink. | `tests/test_sms_handler.py` |
| P14 | Email safety | `ALLOW_REAL_PROSPECT_CONTACT=false`. | Email routes to `STAFF_SINK_EMAIL`. | `tests/test_email_handler.py` |
| P15 | SMS safety | `ALLOW_REAL_PROSPECT_CONTACT=false`. | SMS routes to `STAFF_SINK_PHONE_NUMBER`. | `tests/test_sms_handler.py` |
| P16 | Provider failure | Resend transient failure occurs. | Bounded retry then explicit `EmailSendError`. | `tests/test_email_handler.py` |
| P17 | Provider failure | Cal.com returns HTTP 500. | Retry as transient failure. | `tests/test_crm_calendar.py` |
| P18 | Provider failure | Cal.com returns HTTP 400. | No retry; explicit booking error. | `tests/test_crm_calendar.py` |
| P19 | Idempotency | Same booking event replayed twice. | One HubSpot booking update only. | `tests/test_crm_calendar.py` |
| P20 | Webhook idempotency | Same inbound email event replayed. | Duplicate ignored. | `tests/test_email_handler.py` |
| P21 | Malformed webhook | Email webhook lacks event type. | Handler returns malformed/error path. | `tests/test_email_handler.py` |
| P22 | MCP routing | `USE_HUBSPOT_MCP=true` with no access token. | Explicit configuration error. | pending |
| P23 | MCP tool ambiguity | MCP tool list lacks contact write tool. | Explicit `HubSpotMCPError`. | pending |
| P24 | AI maturity parse | LLM returns prose instead of JSON. | Parser raises `AiMaturityParseError`. | `tests/test_judgment.py` |
| P25 | AI maturity bounds | LLM returns score 5. | Parser rejects score. | `tests/test_judgment.py` |
| P26 | AI maturity sourcing | LLM invents source URL not in claims. | Rubric forbids; review should flag. | pending |
| P27 | Competitor gap | No peer evidence is available. | Output remains stub/draft, no gap claim in outreach. | `tests/test_judgment.py` |
| P28 | Leadership conflict | New CTO and new CEO occur concurrently. | Segment 3 disqualified. | `tests/test_judgment.py` |
| P29 | Thin evidence | No actionable claims exist. | Segment classifier abstains. | `tests/test_judgment.py` |
| P30 | Fixture/live boundary | Synthetic run artifact is reviewed. | Artifact says `demo_mode: true` and AI maturity source is stub. | `tests/test_end_to_end_thread.py` |
