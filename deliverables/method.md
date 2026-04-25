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

## 5. Mechanism Design — Signal-Confidence-Aware Phrasing

### What it is

Signal-Confidence-Aware Phrasing is the challenge document's recommended
direction #1 made executable. Three components: a deterministic tier-mood
mapping that strips the LLM's freedom to escalate confidence, a sensitivity
axis that overrides mood to interrogative for claim kinds where even verified
evidence is presumptuous, and a bench-to-brief hard constraint that blocks
capacity claims without a bench snapshot citation. Confidence lives outside
the model; the model only writes prose.

### Re-implementable spec

**Epistemic layer contracts.** Five layers, each with a single truth contract:

```text
evidence rows -> claim rows -> judgment objects -> draft text -> gate report
```

- Evidence layer (`agent/evidence/`): raw facts only, append-only, each row
  carries `{fact, source_url, retrieved_at, method}`. No interpretation.
- Claims layer (`agent/claims/`): groups evidence into typed claims
  (`funding_round`, `hiring_surge`, `leadership_change`, `layoff_event`,
  `company_metadata`), assigns tier, carries evidence IDs forward.
- Judgment layer (`agent/judgment/`): reads claim rows and AI-maturity
  justifications, never raw scraped text.
- Actions layer (`agent/actions/`): factual sentences may only be written from
  claim rows or schema-shaped judgments.
- Gate layer (`agent/gate/`): blocks unsupported factual sentences before any
  provider call.

**Tier rule.**

| Tier | Rule |
|---|---|
| `verified` | >=2 independent primary URLs, event age <=7 days |
| `corroborated` | 1 primary + 1 secondary URL, event age <=30 days |
| `inferred` | one fresh primary signal, or secondary-only signal |
| `below_threshold` | stale, missing, or insufficient evidence; not visible downstream |

**Mood from tier.**

| Tier | Allowed mood |
|---|---|
| `verified` | indicative |
| `corroborated` | hedged indicative |
| `inferred` | interrogative |
| `below_threshold` | absent (not referenced) |

The model does not pick mood. The tier picks it. Question phrasing is not a
citation exemption: if a sentence makes a factual claim, `agent/gate/citation_check.py`
still requires a `{claim_id}` reference, regardless of punctuation.

**Sensitivity axis.** Even a verified claim can be presumptuous. A sensitive
claim kind overrides the mood-from-tier mapping to interrogative. The set
`SENSITIVE_CLAIM_KINDS = {layoff_event, ai_maturity_below_2,
capability_gap_primary_deficit, contradictory_signals}` covers the categories
where naming the situation as fact ("you laid off engineers and need help")
reads as accusatory or presumptuous regardless of evidence strength. The
A/B reply-rate inversion (-9.38 pp, n=32/arm in `eval/ab_reply_rate_report.json`)
showed that signal density past a threshold reduces reply likelihood; the
sensitivity axis is the lever that lowers density on exactly the topics where
density backfires.

**Gate pipeline.** Three deterministic checks run in order before any send:

1. `citation_check` — every factual sentence maps to a `{claim_id}` carried by
   the draft.
2. `shadow_review` — adversarial second-model pass searches for unsupported
   claims.
3. `forbidden_phrases` — regex blocks future-tense staff availability,
   prospect-facing "bench", and over-claiming phrases.

Any gate failure routes to the human queue. There is no retry loop; retrying a
truth-claim failure produces a different lie, not a corrected one.

**Bench-to-brief constraint.** Sentences implying engineer availability,
stack coverage, or delivery commitment must cite a row from the Tenacious
bench summary. This is a hard constraint enforced at the claim layer (no
`bench_capacity` claim without `data/bench/` evidence) and at the gate layer
(forbidden-phrase regex catches "engineers ready", "availability this week",
"can start", and similar future-tense capacity language). Capacity
over-commitment is a delivery-risk failure, not a tone failure, so it
gets a hard rule.

### Rationale (linked to target failure)

**Target failure:** signal over-claiming under defensive replies. The probe
in `probes/target_failure_mode.md` shows that once a prospect pushes back
("we're not actually restructuring"), a vanilla LLM tends to explain harder
and drift from "we saw a weak signal" into "you have this problem."

**Root cause:** mood drift is unobservable to the model. The model has no
internal representation of "I should be in interrogative mode for this
sentence", so under skepticism it raises confidence to defend itself. The
escalation is a generation-time artifact, not a reasoning failure, which
means a reasoning-level prompt patch does not fix it.

**How the mechanism addresses it:**

- Tier-mood mapping makes mood deterministic from evidence shape. The model
  cannot escalate mood without first escalating tier, and tier escalation
  requires fabricating evidence rows, which the citation gate catches.
- The sensitivity axis catches verified-but-presumptuous claims. Verified
  evidence is not licence to write the prospect's situation in declarative
  prose; sensitive kinds always become questions.
- The bench-to-brief guard blocks the capacity-over-commitment failure mode
  where the model invents engineer availability to close.
- The gate pipeline is post-generation and deterministic, so model
  drift cannot route around it.

### Hyperparameters (actual values used)

| Parameter | Value | Location |
|---|---:|---|
| `VERIFIED_MAX_AGE_DAYS` | 7 | `agent/claims/tiers.py` |
| `CORROBORATED_MAX_AGE_DAYS` | 30 | `agent/claims/tiers.py` |
| `HIRING_SURGE_MIN_POSTINGS` | 3 | `agent/claims/tiers.py` |
| `HIRING_SURGE_WINDOW_DAYS` | 30 | `agent/claims/tiers.py` |
| `JOB_VELOCITY_WINDOW_DAYS` | 60 | `agent/evidence/sources/job_posts.py` |
| Segment confidence threshold | 0.6 | `agent/judgment/segment.py` |
| AI maturity silent-company score | 0 | `agent/prompts/ai_maturity_rubric.md` |
| `LLM_BUDGET_USD` per run | 0.50 | `.env` (default in `integrations/llm.py`) |
| Stall threshold | 300 seconds | `eval/stall_rate.py` |
| `SENSITIVE_CLAIM_KINDS` | `{layoff_event, ai_maturity_below_2, capability_gap_primary_deficit, contradictory_signals}` | `agent/claims/sensitivity.py` |
| Weak-hiring soft-language threshold | <5 open eng roles | per challenge doc; enforced at segment-1 qualification |
| Competitor gap max findings | 3 | `data/tenacious_sales_data/schemas/competitor_gap_brief.schema.json` |

### Three ablation variants

- **Variant A — No tier-mood mapping.** Flag: `TIER_MOOD_MAP_DISABLED=true`.
  The drafter receives claim rows but no mood prescription; the LLM picks
  mood. Tests whether deterministic mapping is what prevents over-confidence,
  or whether the model would have stayed in correct mood anyway given the
  same evidence.
- **Variant B — Blanket question exemption gate.** Roll back to the
  pre-Phase-6 `agent/gate/citation_check.py` (git SHA pre-`ffa4fe6`), which
  exempted any sentence ending with `?` from citation requirements. Tests
  whether question phrasing remains a viable bypass for unsupported facts
  once the model learns it.
- **Variant C — No sensitivity axis.** Override `SENSITIVE_CLAIM_KINDS` to
  `frozenset()`. Verified-tier claims get indicative mood, including layoffs
  and capability deficits. Tests the A/B finding that sensitive claim kinds
  need interrogative mood regardless of tier strength — i.e., that mood is a
  function of *kind* as well as *evidence*.

### Statistical test plan

- **Comparison:** main method vs Variant A pass@1 on the tau2-bench retail
  dev slice (n=30 tasks).
- **Test:** two-proportion z-test, p<0.05 threshold.
- **Delta A:** `your_method - supplied_qwen_baseline`. Supplied baseline =
  Pass@1 0.7267, n=30, 5 trials averaged.
- **Power constraint:** the supplied baseline used 5 trials; the treatment
  budget allows 1 trial at n=30. The Wilson 95% CI on a single-trial pass@1
  is wide. To clear the baseline CI's upper edge in a single trial, the
  treatment must score approximately pass@1 >=0.93. This is reported as a
  known limitation of the 1-trial scope reduction documented in
  `docs/handoff_notes.md`, not a limitation of the mechanism itself.
- **Delta B (vs GEPA / AutoAgent):** intentionally not run. Documented in
  `docs/handoff_notes.md` as a scope reduction after the 2026-04-24 cut.
- **Delta C (vs published tau2-bench reference):** informational only; the
  published reference uses a different model and prompt baseline, so Delta C
  carries no causal claim about this mechanism.

### Tau2 transfer mechanism

The tau2 transfer applies the same principle: confidence lives outside the
generation step. `eval/tau2_agent_runtime.py` subclasses tau2's `LLMAgent`
and overrides only `system_prompt`, adding instructions to verify
irreversible or customer-state-changing actions against the most recent
tool output before committing. The first-pass adapter is deliberately
prompt-only; tool-call interception (`_generate_next_message` override)
is held in reserve.

`eval/tau2_custom_agent.py` is the unit-tested validation harness that
defines the rule shape — ambiguous tool output, missing action identifiers,
or low-confidence irreversible actions should produce a clarifying question
or re-plan rather than a commit. The runtime does not import these helpers
for the prompt-only pass; they document the rule precisely and prove it
works in isolation.

Decision rule for the single-trial treatment run:

| Treatment Pass@1 | Action |
|---:|---|
| >= 0.80 | Ship prompt-only. |
| 0.75-0.79 | Code-level fallback only if trace review shows under-asking. |
| < 0.75 | Add the `_generate_next_message` interception fallback and re-run. |
| < 0.73 | Report flat or negative Delta A honestly; mechanism did not transfer. |

### Result (filled in after F2 finishes)

- Treatment Pass@1: {TBD}
- 95% Wilson CI: {TBD}
- Delta vs supplied baseline (0.7267): {TBD}
- Two-proportion z-test p-value: {TBD}

The stall-rate measurement currently reports 0/20 runs over the 300-second
threshold. That validates orchestration latency, not mechanism quality;
mechanism quality is evaluated by Delta A, citation-gate failure rate,
probe trigger rate, and held-out task behavior.

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
