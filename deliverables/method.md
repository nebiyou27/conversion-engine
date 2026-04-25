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

Competitor gap judgment is deterministic in `agent/judgment/competitor_gap.py`.
It reads the prospect's AI-maturity justifications plus a static sector peer
fixture, then emits a schema-shaped `competitor_gap_brief` only when at least
five peers and one valid gap are available. Missing peer data returns `None`
rather than a schema-invalid soft fallback.

## 5. Mechanism: Signal-Confidence-Aware Phrasing

**Mechanism name:** Signal-Confidence-Aware Phrasing. Internally, this is the
combination of tier-mood mapping, citation gates, competitor-gap self-checks,
and a bench-to-brief constraint.

**Reimplementable rule.** The agent converts source data into progressively
stronger truth objects:

```text
evidence rows -> claim rows -> judgment objects -> draft text -> gate report
```

The evidence layer stores raw facts with source URLs. The claims layer groups
facts into `funding_round`, `hiring_surge`, `leadership_change`, `layoff_event`,
and `company_metadata`, assigns a tier, and carries evidence IDs forward. The
judgment layer reads claim rows and AI-maturity justifications, not raw scraped
text. The actions layer may write factual sentences only from claim rows or
schema-shaped judgments. The gate layer blocks unsupported factual sentences
before any provider call.

**Tier-mood mapping.**

| Claim tier | Rule | Allowed outreach mood |
|---|---|---|
| `verified` | At least two primary URLs and event age <= 7 days | Indicative |
| `corroborated` | At least one primary plus one secondary URL and event age <= 30 days | Hedged indicative |
| `inferred` | One fresh primary signal, or secondary-only signal | Interrogative / soft |
| `below_threshold` | Stale, missing, or insufficient evidence | Do not use downstream |

Question phrasing is not a citation exemption. If a sentence contains a factual
claim, `agent/gate/citation_check.py` still requires a `{claim_id}` reference.
The shadow review reuses the citation check, and the forbidden-phrase gate
blocks style-guide violations such as prospect-facing use of "bench".

**Competitor-gap constraint.** Gap findings are capped at three and sorted by
confidence. A high-confidence gap requires at least three top-quartile peers and
an absent prospect signal with medium-or-better confidence. With six SaaS peers,
top quartile is two companies, so high confidence is intentionally unreachable;
small peer sets can support useful questions but not hard gap claims.

**Bench-to-brief constraint.** Capacity claims must be grounded in the Tenacious
bench snapshot. Drafts should not claim available engineers or stack coverage
unless the corresponding bench summary supports that commitment. This is a hard
constraint because capacity over-commitment is not a tone problem; it is a
delivery-risk problem.

**Rationale.** The target failure is signal over-claiming under defensive
replies: once challenged, an LLM tends to explain harder and drift from "we saw
a weak signal" into "you have this problem." The mechanism makes confidence
external to the model. Evidence tier determines sentence mood, gap self-checks
determine whether peer comparisons can be asserted or only asked about, and the
gate checks citations after drafting.

The A/B reply-rate run exposed the sensitivity axis. In `eval/ab_reply_rate_report.json`,
the signal-grounded variant scored 84.38% judged reply likelihood against
93.75% for the generic variant, a -9.38 percentage-point delta at n=32 per arm.
That does not invalidate signal grounding; it says specificity has a dosage
limit. Signal-grounded lost because it raised evidence density above the
prospect's tolerance threshold for a cold first-touch email. The variable is not
"more evidence is better"; it is **evidence density tuned to channel and
relationship stage**. The mechanism should use signal confidence to decide both
**what can be said** and **how much evidence to surface in a first touch**.
Low-confidence or medium-confidence gap material should become one short
question, not a crowded research memo in email form.

**Hyperparameters.**

| Parameter | Value | Location |
|---|---:|---|
| `VERIFIED_MAX_AGE_DAYS` | 7 | `agent/claims/tiers.py` |
| `CORROBORATED_MAX_AGE_DAYS` | 30 | `agent/claims/tiers.py` |
| `HIRING_SURGE_MIN_POSTINGS` | 3 | `agent/claims/tiers.py` |
| `HIRING_SURGE_WINDOW_DAYS` | 30 | `agent/claims/tiers.py` |
| Segment minimum confidence | 0.6 | `agent/judgment/segment.py` |
| Competitor peer count | 5-10 | `data/tenacious_sales_data/schemas/competitor_gap_brief.schema.json` |
| Competitor gap max findings | 3 | same schema |
| Stall threshold | 300 seconds | `eval/stall_rate_report.json` |

**Ablations.**

| Ablation | Change | Expected readout |
|---|---|---|
| No tier-mood mapping | Let the LLM choose confidence and sentence posture | More over-claiming on inferred or contradicted signals |
| Blanket question exemption | Allow factual questions without `{claim_id}` | Unsupported facts bypass the citation gate |
| No segment threshold | Emit segments below confidence 0.6 | More weak-evidence outreach and false-positive ICP matches |
| Evidence-density cap off | Allow all claim/gap details in first touch | Higher specificity, but lower reply likelihood as shown by the A/B inversion |

The stalled-thread measurement currently reports 0/20 runs over the 300-second
threshold. That validates orchestration latency, not mechanism quality; the
mechanism is evaluated by citation failures, probe results, reply-rate deltas,
and later held-out task behavior.

## 6. Honest Status

| Area | Status | Evidence |
|---|---|---|
| Evidence and claims | Implemented | `tests/test_evidence.py`, `tests/test_claims.py` |
| Deterministic segment logic | Implemented | `tests/test_judgment.py` |
| Citation and phrase gates | Implemented | `tests/test_citation_check.py`, gate modules |
| SMS warm-lead safety | Implemented | `tests/test_sms_handler.py` |
| Synthetic internal E2E | Implemented | `tests/test_end_to_end_thread.py`, `outputs/runs/20260423-180101/` |
| Real provider E2E | Partial | Email/SMS latency only; CRM/calendar not live-proven in tests |
| Competitor gap | Deterministic peer-fixture implementation | `agent/judgment/competitor_gap.py`, `tests/test_judgment.py` |
| Mechanism documentation | Implemented | This section, `probes/target_failure_mode.md` |

## 7. Remaining Work

- Run Act III probes and record trigger rates in `probes/failure_taxonomy.md`.
- Wire real-source acquisition into the main run path instead of fixture-first
  collection.
- Run a real-world dry run with public inputs while preserving staff-sink
  outbound routing.
- Add the bench-to-brief guard as executable code, not only a documented
  mechanism constraint.
- Export the final PDF/report after artifact polish.
