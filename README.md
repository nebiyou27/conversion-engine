# Conversion Engine

AI agent for automated, evidence-backed sales outreach on behalf of Tenacious Consulting and Outsourcing. Built for TRP1 Week 10.

## Status

Core agent logic is implemented and covered by tests. The repository includes a
synthetic end-to-end thread that exercises evidence collection, claim building,
judgment, draft generation, gates, reply normalization, booking flow, and CRM
write-back using fixtures and provider mocks.

Live verification currently exists for email/SMS latency only. HubSpot,
Cal.com, HubSpot MCP, and Langfuse are implemented behind adapters and covered
by contract/unit tests, but should not be described as fully
production-verified.

See `PRD.md` for acceptance criteria and `progress.md` for the decision log.

## Architecture

Epistemic layering - the system is organized by the kind of truth claim each layer handles, not by function. See `CLAUDE.md` Section 2 for the full contract.

```
EVIDENCE  ->  CLAIMS  ->  JUDGMENT  ->  ACTIONS  ->  GATE
raw facts     tiered      interp.     drafts     pre-send
              assertions  over        with       validation
                          claims      citations
```

## Rubric Implementation Map

| Rubric component | Files | Test |
|---|---|---|
| Outbound Email Handler | `integrations/email_client.py`, `agent/handlers/email.py` | `tests/test_email_handler.py` |
| SMS Handler | `integrations/sms_client.py`, `agent/handlers/sms.py` | `tests/test_sms_handler.py` |
| CRM + Calendar | `integrations/hubspot_client.py`, `integrations/hubspot_mcp_client.py`, `agent/actions/schedule.py` | `tests/test_crm_calendar.py`, `tests/test_hubspot_mcp_client.py` |
| Signal Enrichment | `agent/evidence/sources/*.py`, `agent/evidence/enrichment.py` | `tests/test_signal_enrichment.py` |

## Enrichment Module Outputs

Every enrichment source writes raw `Fact` rows first. The reviewer-facing
visibility layer in `agent/evidence/enrichment.py` then emits a single
artifact with:

- `signals[]`: one row per enrichment module with `signal`, `implementation`,
  `status`, `confidence`, `evidence_count`, `latest_retrieved_at`, and
  `source_urls`.
- `per_signal_confidence`: compact `{signal: confidence}` map for demos,
  CRM write-back, and reviewer inspection.
- `evidence_count`: total raw evidence rows used to build the artifact.

| Enrichment module | Raw facts emitted | Confidence behavior | Downstream use |
|---|---|---|---|
| Crunchbase firmographics | `funding_round` facts with round, amount, announcement date, source URL, and retrieved timestamp | Starts high when present; absent records stay low (`0.15`) rather than becoming proof of no funding | Series A/B timing, Segment 1 qualification, and funding-trigger citations |
| Job posts | One `job_posting` fact per public posting with title, posted date/listing URL, source URL, and `method=playwright` for scraped pages | Starts moderate because public job pages are noisy; gains confidence with fresh and repeated rows | Hiring surge claims, AI-maturity justifications, and weak-hiring soft-language checks |
| Layoffs | One `layoff_event` fact per matched CSV row with event date, headcount, company, source URL, and `method=csv` | Starts medium-high when present; absent or non-matching rows stay very low (`0.05`) to avoid phantom restructuring claims | Segment 2 mid-market restructuring detection and sensitive interrogative phrasing |
| Leadership changes | `leadership_change` facts with event, person, effective date, source URL, and retrieved timestamp | Starts high when present; absent feed is low (`0.15`) and does not disprove a leadership change | Segment 3 leadership-transition routing and CTO/VP Eng timing claims |
| Company metadata | `company_metadata` snapshot with headcount plus optional HQ country and founded year | Highest base confidence when present; absent metadata is `0.0` because it is structural context, not a behavioral signal | Headcount bounds, ICP filters, and CRM context |

This section is intentionally about outputs, not provider completeness. The
verification matrix below still distinguishes fixture-backed, unit-tested,
contract-tested, and live-proven paths.

## Verification Matrix

| Component | Current verification | Evidence | Limitation |
|---|---|---|---|
| Resend email | Live staff-sink latency run | `outputs/runs/latency-20260423-201603/latency_summary.json` | No real prospect contact |
| Africa's Talking SMS | Sandbox/staff-sink latency run | same latency summary | No real prospect contact |
| HubSpot SDK | Contract-tested | `tests/test_crm_calendar.py` | Provider writes mocked in tests |
| HubSpot MCP | Unit-tested client | `tests/test_hubspot_mcp_client.py` | Remote MCP not exercised in CI |
| Cal.com | Adapter + synthetic flow | `agent/actions/schedule.py`, `tests/test_crm_calendar.py` | Live booking endpoint not proven in test suite |
| Langfuse | Wrapper implemented | `integrations/langfuse_client.py` | Current synthetic run does not prove remote trace delivery |

## CRM

HubSpot writes support two paths:

- `USE_HUBSPOT_MCP=true` routes contact create and update operations through the remote HubSpot MCP server at `https://mcp.hubspot.com/`.
- `HUBSPOT_TOKEN` remains as a local SDK fallback for development and smoke testing.

The MCP route expects an access token minted from a HubSpot MCP auth app. The auth app is created in HubSpot under Development > MCP Auth Apps, and the MCP client uses the remote server with OAuth 2.1 + PKCE outside the agent hot path.

## Quick start

```bash
# 1. Create virtualenv
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# or: .venv\Scripts\activate     # Windows cmd/PowerShell

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env template and fill in keys
cp .env.example .env
# edit .env with real API keys (never commit)

# 4. Run Day 0 smoke tests
python scripts/day0_check.py

# 5. Run a single end-to-end prospect
python scripts/run_one_prospect.py
```

## Run Order

1. `python -m pytest -q`
2. `python scripts/day0_check.py`
3. `python scripts/run_one_prospect.py`
4. `python eval/stall_rate.py`
5. `python scripts/measure_email_sms_latency.py --runs 20 --live --sink-phone +2547XXXXXXXX`

The live latency command is only needed when provider credentials and staff
sink routing are configured.

## Directory Index

| Path | Purpose |
|---|---|
| `agent/` | Evidence, claims, judgment, actions, gates, handlers, and orchestration. |
| `api/` | Webhook/server route wrappers. |
| `Challenge_Documents/` | Supplied challenge baselines and reference artifacts. |
| `data/` | Fixtures, schemas, local bench summaries, and SQLite data. |
| `deliverables/` | Reviewer-facing method, baseline, competitor-gap, and evidence graph artifacts. |
| `docs/` | Architecture, methodology, handoff notes, and execution plans. |
| `eval/` | Measurement and benchmark scripts. |
| `integrations/` | Provider clients for LLM, email, SMS, CRM, calendar, and Langfuse. |
| `outputs/` | Generated run artifacts and latency measurements. |
| `probes/` | Failure taxonomy and probe library. |
| `scripts/` | Operator scripts for smoke runs and latency collection. |
| `storage/` | SQLite schema and append-only storage API. |
| `tests/` | Unit and contract tests. |

## Latency Measurement

To collect the rubric-required email + SMS timings, run the dedicated measurement script in live mode:

```bash
python scripts/measure_email_sms_latency.py --runs 20 --live --sink-phone +2547XXXXXXXX
```

Required env vars for live mode:

- `RESEND_API_KEY`
- `AFRICASTALKING_USERNAME`
- `AFRICASTALKING_API_KEY`
- `STAFF_SINK_PHONE_NUMBER` if you do not pass `--sink-phone`

The script writes:

- `outputs/runs/latency-<timestamp>/latency_log.jsonl`
- `outputs/runs/latency-<timestamp>/latency_summary.json`

Use the summary file for `p50` and `p95` in the interim report.

## Operational Hardening

The runtime now favors operator visibility and safe replays:

- `LOG_LEVEL` controls structured log verbosity for send attempts, webhook receipt, booking confirmation, and CRM writes.
- `IDEMPOTENCY_CACHE_DIR` can be set to persist replay protection across restarts. If it is unset, replay protection stays in-memory for the current process.
- Resend, Africa's Talking, Cal.com, and HubSpot writes use bounded retries with backoff for transient provider failures.
- Email and SMS webhook handlers reject malformed payloads and ignore duplicate replays.
- Booking write-backs to HubSpot are replay-safe for the same booking id.

## Key files

- `CLAUDE.md` - architecture, rules, skills index (read first)
- `PRD.md` - what we are building and the acceptance criteria
- `progress.md` - decision log
- `deliverables/` - reviewer-facing artifacts
- `.claude/skills/` - project-scoped skills: `claim-audit`, `probe-author`, `gate-check`

## Safety

All outbound traffic routes to `STAFF_SINK_EMAIL` by default. Real prospect contact requires `ALLOW_REAL_PROSPECT_CONTACT=true` in `.env`, which is only set after program-staff + Tenacious-executive approval.
