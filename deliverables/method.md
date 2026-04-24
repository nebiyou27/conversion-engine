# Interim Submission Report - Conversion Engine

**Submitted by:** Nebiyou Abebe (nebiyoua@10academy.org)
**Date:** 2026-04-23

## 1. Architecture Rationale

Conversion Engine is built as an epistemic pipeline:

```text
EVIDENCE -> CLAIMS -> JUDGMENT -> ACTIONS -> GATE
raw facts  tiered    segment     drafts    pre-send
           claims    decisions   actions   validation
```

Every failure mode in outbound AI outreach is a truth-claim failure: the system
asserts something it cannot support. The code therefore separates raw evidence,
derived claims, judgment, actions, and pre-send gates. The strongest invariant
is that downstream layers consume claim rows and claim IDs, not unstructured
scraped text.

Email is the primary channel because it carries the full evidence-backed
message and creates an auditable reply path. SMS is a warm-lead channel only;
`agent/handlers/sms.py` raises `SMSChannelError` before any provider call if
the prospect is not warm.

## 2. Production Stack Status

The project has the required adapters implemented, but verification levels
differ. This matrix separates live evidence from contract tests and synthetic
demo coverage.

| Component | Current verification | Evidence | Limitation |
|---|---|---|---|
| Resend email | Live staff-sink latency run | `outputs/runs/latency-20260423-201603/latency_summary.json` | No real prospect contact |
| Africa's Talking SMS | Sandbox/staff-sink latency run | same latency summary | No real prospect contact |
| HubSpot SDK | Contract-tested | `tests/test_crm_calendar.py` | Automated tests mock provider writes |
| HubSpot MCP | Unit-tested client | `tests/test_hubspot_mcp_client.py` | Remote MCP path is not exercised in CI |
| Cal.com | Adapter plus synthetic flow | `agent/actions/schedule.py`, `tests/test_crm_calendar.py` | Live booking endpoint is not proven by tests |
| Langfuse | Wrapper implemented | `integrations/langfuse_client.py` | Current synthetic gate report does not prove remote trace delivery |

Email and SMS latency evidence from the 20-run harness:

- p50 email send: **0.581s**
- p95 email send: **2.927s**
- p50 SMS send: **0.572s**
- p95 SMS send: **0.775s**

The synthetic end-to-end thread at `outputs/runs/20260423-180101/` exercises
the internal pipeline with fixture evidence and provider mocks. It is useful as
a smoke test, not as a fully live provider-backed run.

## 3. Enrichment Pipeline

| Signal | Implementation | Current status |
|---|---|---|
| Crunchbase firmographics | `agent/evidence/sources/crunchbase.py` | Fixture-backed unless `CRUNCHBASE_ODM_ENDPOINT` is configured |
| Job posts | `agent/evidence/sources/job_posts.py` | Playwright parser implemented and tested |
| Layoffs | `agent/evidence/sources/layoffs.py` | Team CSV ingestion implemented; live page scraping is not required |
| Leadership changes | `agent/evidence/sources/leadership.py` | Normalizer implemented; no live feed configured |
| Company metadata | `agent/evidence/sources/company_metadata.py` | Fixture/snapshot-backed |

Layoff evidence uses the team-provided CSV when available. Rows are filtered by
company name, blank layoff counts are skipped, and missing layoff evidence is
treated as absence rather than inferred restructuring pressure.

## 4. Deterministic Judgment

The segment classifier in `agent/judgment/segment.py` is deterministic and
first-match-wins:

1. Recent layoff within 120 days + actionable funding + at least 3 open roles:
   `segment_2_mid_market_restructure`.
2. New CTO or VP Engineering within 90 days + headcount 50-500 + no concurrent
   CEO/CFO transition: `segment_3_leadership_transition`.
3. AI maturity score >= 2 + actionable hiring-surge claim:
   `segment_4_specialized_capability`.
4. Funding within 180 days: `segment_1_series_a_b`.
5. Otherwise: `abstain`.

AI maturity is LLM-adjudicated in `agent/judgment/ai_maturity.py`, but the
synthetic thread currently uses a hardcoded demo response and labels it as
`source: hardcoded_demo_stub` in `run.json`.

## 5. Honest Status

| Area | Status | Evidence |
|---|---|---|
| Evidence and claims | Implemented | `tests/test_evidence.py`, `tests/test_claims.py` |
| Deterministic segment logic | Implemented | `tests/test_judgment.py` |
| Citation and phrase gates | Implemented | `tests/test_citation_check.py`, gate modules |
| SMS warm-lead safety | Implemented | `tests/test_sms_handler.py` |
| Synthetic internal E2E | Implemented | `tests/test_end_to_end_thread.py`, `outputs/runs/20260423-180101/` |
| Real provider E2E | Partial | Email/SMS latency only; CRM/calendar not live-proven in tests |
| Competitor gap | Stub | `agent/judgment/competitor_gap.py` |

## 6. Remaining Work

- Run Act III probes and record trigger rates in `probes/failure_taxonomy.md`.
- Either provide peer evidence for competitor gap or keep it labeled as a
  framing draft.
- Run a real-world dry run with public inputs while preserving staff-sink
  outbound routing.
- Export the final PDF/report after artifact polish.
