# Progress — Decision Journal

Running log of architectural decisions, what was tried, what was rejected, and why.
Append-only. Date every entry.

---

## 2026-04-21 — Phase 0: Repo scaffolded

**What:** Created full folder tree following epistemic layering (evidence → claims → judgment → actions → gate). All Python package skeletons in place. Dependencies pinned in `requirements.txt`.

**Why epistemic layering instead of functional:** Every failure mode in this project is a truth-claim failure. A functional architecture (enrichment → draft → send) can't prevent over-claiming because it treats raw facts and interpretations as the same kind of thing. Epistemic layering forces the distinction at directory level — the evidence collector cannot interpret, the claim builder cannot assert without a tier, the gate cannot be bypassed.

**Why tier → grammatical mood is hard-coded, not passed as a number:** Passing a confidence number to the LLM and hoping it hedges is the approach most systems take, and it's where over-claiming sneaks in. Instead, the tier (verified / corroborated / inferred / below-threshold) deterministically constrains the sentence mood (indicative / hedged / interrogative / absent). A regex at the gate can detect violations. Violations become bugs, not stylistic opinions.

**Why competitor selection by capability overlap, not sector:** "Sector" groups a community bank with a fintech API — useless for this domain. "Hires the same role titles for the same stack" is queryable from public job boards and directly relevant to Tenacious's pitch. Also more defensible to a skeptical CTO.

**Rejected:** A flat `agent/policy/` directory. Trust rules live at every layer, not in a single module. Policy is the gate's orchestration, but the evidence layer's append-only contract is also a trust rule, and so is the claims layer's tier requirement.

**Deferred:**
- Real API scraping (Crunchbase, job boards, layoffs.fyi) — fixtures suffice for Wednesday
- Market-space map (stretch goal, only if everything else ships)
- SMS-first flows — email primary per the doc

## Open questions

- What specific score cutoffs for AI maturity tiers? Document claims "per-signal justification" but doesn't define weights. Tentative plan: LLM-adjudicated rubric with cited evidence, not weighted-sum formula.
- What exact thresholds for verified vs corroborated? Tentative: verified = ≥2 independent primary, ≤7 days; corroborated = 1 primary + 1 secondary, ≤30 days.
- How to calibrate shadow-review disagreement rate into a reliability metric? Tentative: treat as filter only, not metric; calibration data comes from periodic hand-labeling.

## 2026-04-22 — Phase 1: Day 0 smoke tests green

**What:** All 5 external services verified reachable — Resend, HubSpot, Cal.com, Langfuse, τ²-Bench env vars. HubSpot contact confirmed visually in dashboard.

## 2026-04-22 — Phase 2: Storage layer

**What:** SQLite DDL at `storage/schema.sql` with 5 tables (evidence, claims, judgments, drafts, gate_reports). Thin Python API at `storage/db.py` exposes one insert + one read per layer. File-based JSON cache at `storage/cache.py` under `data/cache/`. 9 contract tests in `tests/test_storage.py`, all green.

**Why append-only by API contract, not DB trigger:** R5 — the contract is "no update/delete functions exist on the module." A test locks this by introspecting `storage.db` for `update_*` / `delete_*` / `remove_*` and failing if any are added. A trigger would be belt-and-braces ceremony for the same guarantee.

**Why CHECK constraints on tier/kind/channel/path/decision:** These enumerations are the epistemic contract (R2, R4). Invalid values must fail loud at insert time, not sneak through and corrupt downstream reasoning. `test_claim_rejects_invalid_tier` locks this.

**Why evidence_ids / claim_ids as JSON arrays, not a join table:** Every read path needs the full array together (no "find claims citing evidence X" query yet). R5 — a join table would be premature for a one-use access pattern. Revisit if cross-layer queries appear.

**Why a single DB at `data/conversion.db`:** Runs are ephemeral (`outputs/runs/<ts>/`) and will pull snapshots. The DB is the durable ground truth across runs. Already gitignored by `*.db`.

## 2026-04-22 — Phase 3: Evidence collector + fixture loaders

**What:** `Fact` dataclass in `agent/evidence/schema.py` (frozen, `__post_init__` rejects empty source_url — audit trail is mandatory). Four pure fixture loaders under `agent/evidence/sources/` (crunchbase, job_posts, layoffs, leadership). Thin dispatch collector in `agent/evidence/collector.py`. One synthetic fixture at `data/fixtures/companies/acme_series_b.json` with all 4 sections (layoffs intentionally empty). 17 tests green.

**Why fail-loud-on-malformed, clean-on-absent:** These are different failure semantics. Missing section = source returned nothing today — a normal state, 0 facts. Present-but-malformed = corrupted input — must raise, because silent degradation looks identical to "no evidence" downstream and would let the system over-claim confidence later. R7 is about thin input at the judgment layer; the evidence layer is upstream of that and has the opposite obligation.

**Why underscore-prefixed keys skipped in collector:** The fixture carries a top-level `_note` disclaimer and the collector tolerates arbitrary `_`-prefixed keys inside `sources` too. Cheap protection: reviewers can add provenance annotations without crashing a loader.

**Why one Phase-2 extension (retrieved_at kwarg on insert_evidence):** Tier thresholds are time-based (≤7d verified, ≤30d corroborated). Phase 4 will need aged fixture signals to exercise tier-downgrade paths. Adding the override as a kwarg with default None preserves existing behavior and keeps one connection-handling pattern (tightening #4).

**Why kind lives on Fact but is merged into raw_payload at DB write time:** DB schema has no kind column — raw_payload (JSON) is the right home since kind is source-specific taxonomy. Keeping kind as a typed dataclass field (not buried in payload) makes it visible to future claim-builder code without requiring a schema change now.

## 2026-04-22 — Phase 4: Claims layer

**What:** Tier computation (pure function) + claim builder (DB-aware) that aggregates evidence into tiered assertions. Added `kind` column to claims table with CHECK constraint on the four kinds (funding_round, hiring_surge, leadership_change, layoff_event). 13 tests green — total 39/39.

**Why primary/secondary is claim-relative, not source-relative:** job_posts are the primary signal for "hiring_surge" but only a corroborating secondary signal for "funding_round." A single evidence row can feed multiple claim kinds at different roles. Captured in `PRIMARY`/`SECONDARY` lookup tables in `agent/claims/tiers.py`.

**Why lenient corroborated (≥1 primary + ≥1 other, age≤30d) instead of literal (1 primary + 1 secondary):** Two primaries where the most recent is 10 days old would fall to below_threshold under literal reading — clearly wrong. Under lenient rule, it falls from verified to corroborated on age, which matches intuition. Locked by `test_tier_verified_downgrades_to_corroborated_on_age`.

**Why single-primary-within-7d → inferred (not corroborated, not below_threshold):** Corroboration requires a second source by definition. A lone primary is real evidence but uncorroborated — the honest downstream posture is interrogative mood ("Has Acme finalized the CTO transition?"). Below-threshold would silence evidence that genuinely exists. Locked by `test_tier_single_primary_within_7d_is_inferred` and its aged counterpart.

**Why age clock = event date, not retrieved_at:** What the prospect cares about is fact freshness, not observation freshness. A Series B from 6 months ago is stale regardless of when we scraped the page. Retrieved_at is the fallback only when the source carries no event-date field.

**Why below_threshold claims are persisted, not dropped:** "Invisible to downstream" means judgment/actions/gate filter them out, not that they never touch the DB. The row is an audit trail of "we had evidence but chose not to act." When Phase 5+ starts producing human-queue routing decisions, this history justifies the no-op. `test_builder_persists_below_threshold_claim` locks it.

**Why hiring_surge below 3 postings emits no claim at all (not even below_threshold):** 2 job postings aren't a surge — they're background noise. Emitting below_threshold would pollute the audit log with non-signals. Different from the below_threshold-but-real-signal case (stale funding round), where we DO want the row. Locked by `test_builder_hiring_surge_below_postings_threshold_not_emitted`.

**Why the tier check runs `p==1 ∧ s==0 ∧ age≤7` BEFORE the "p==0 ∧ s≥1" check:** Ordering matters because both branches return INFERRED but represent different epistemic states. Keeping them distinct (not merged) makes future probe categorization easier — we can separately measure "single-source claims" vs "no-primary claims" failure rates.

**Minor Phase-2 extension:** added `kind` column + CHECK to claims table, `kind` param to `db.insert_claim`. Three existing test_storage.py tests updated to pass `kind="funding_round"` etc. Same pattern as tier CHECK; no schema drift.

## 2026-04-23 — Debt payment: 3 fixtures + LLM wrapper

**What:** Three coverage-extending fixtures (`shadow_startup`, `contradicted_co`, `silent_sophisticate`) and `integrations/llm.py` — the OpenRouter wrapper with cost ledger and per-run budget ceiling. 53/53 tests green (44 claims/storage/evidence + 9 LLM contract).

**Why fixtures bracket behavior space, not happy paths:**
- `shadow_startup` — exercises 4 distinct abstain mechanisms in one fixture (stale primary, under-count threshold, stale single-primary, absent)
- `contradicted_co` — funding + layoff coexist; locks the invariant that claims layer surfaces both independently (resolution is Phase 5 segment-classifier work)
- `silent_sophisticate` — strong firmographics + zero AI signal; instantiates the memo's named Skeptic's Appendix risk so the answer is a real trace, not a hypothetical. The no-AI-keywords guard test prevents future contributors from silently invalidating the false-negative scenario.

**Why a single LLM wrapper for everything:** Every LLM call going through `integrations/llm.complete()` means three guarantees compound — cost is tracked, Langfuse trace exists, budget ceiling enforced. Bypassing the wrapper means losing all three. Tests lock the contract.

**Why "check before, add after" budget ordering:** The call that crosses the ceiling completes; the next call is blocked. Failing mid-call is harder to reason about than failing at the next gate. `test_complete_completes_call_then_blocks_next_when_over_ceiling` locks this.

**Why hardcoded pricing table, not OpenRouter cost-in-response:** The cost-in-response feature requires an experimental flag and is Anthropic-routed-model-specific. A small explicit table (PRICING dict) for the 3 models we use is cheaper to read and easier to update. Unknown models pass through with cost=0 — explicit ignorance over hidden assumptions.

**Why Langfuse failures are silent:** Tracing is observability, not correctness. A Langfuse outage must not block agent work. `_log_call` catches everything, comment explains why.

**Why default budget is $0.50/run, env-overridable:** Per-run ceiling protects against runaway loops. $0.50 is ~570 haiku tool-calls or ~10 sonnet drafts — enough headroom for honest iteration, tight enough to fail loud on a stuck loop. `LLM_BUDGET_USD` overrides for τ²-Bench full runs.

**Cost discipline tier table** (model selection by phase):

| Phase / use | Model | OpenRouter ID | Rationale |
|---|---|---|---|
| Phase 5 — AI maturity | haiku | `anthropic/claude-haiku-4.5` | LLM-as-judge with rubric, not reasoning-heavy |
| Phase 6 — drafting (iteration) | haiku | `anthropic/claude-haiku-4.5` | structured input → templated output |
| Phase 6 — drafting (memo / demo) | sonnet | `anthropic/claude-sonnet-4.5` | only on evidenced runs |
| Phase 7 — shadow review | haiku | `anthropic/claude-haiku-4.5` | adversarial search, not generative |
| Phase 8 — τ²-Bench (smoke) | haiku | `anthropic/claude-haiku-4.5` | $0.50 budget cap → ~3 tasks for harness validation |
| Phase 8 — τ²-Bench (final) | sonnet | `anthropic/claude-sonnet-4.5` | 2 trials × 30 tasks; explicit budget bump via env var |

## Named non-goals

These are failure modes the architecture does NOT solve. Naming them prevents accidental scope-drift and gives the memo's Skeptic's Appendix concrete material.

- **"Technically correct but useless" emails.** A draft that passes citation-coverage, tier-mood, and forbidden-phrase checks may still be a forgettable email. The system guarantees correctness; it does not guarantee compellingness. No probe in the library catches this.
- **Real-time scraping.** All evidence is fixture-driven this week. The collector contract supports `method` field for "api"/"scrape", but no live scrapers ship pre-approval.
- **Real prospect contact.** `ALLOW_REAL_PROSPECT_CONTACT=false` by default; staff-sink override is the only channel.
- **Subjective tone evaluation.** Shadow review catches unsupported claims, not stylistic missteps. Tone calibration requires hand-labeled samples — out of scope for the week, named in the memo.
- **Cross-thread leakage prevention.** Multi-prospect concurrent runs are not in scope for the interim deliverable; `run_id` threading exists in the LLM wrapper but not yet plumbed through evidence/claims.
- **Job-title-aware signal mining.** Current claims layer counts job posts; titles are stored in payload but not yet used for segment-relevant feature extraction. Phase 5 judgment may add this; flagged here as known omission, not bug.
- **Leadership-state aging philosophical correctness.** Treating "new CTO" as decay-eligible at >7d is a defensible approximation, not a real epistemic stance. Real fix would split `leadership_change` (fact, doesn't decay) from `leadership_transition_window` (judgment, decays fast). Deferred.

## 2026-04-23 — Seed materials reconciliation (pre-Phase-5)

**What:** Tenacious seed pack (`Challenge_Documents/tenacious_sales_data/seed/`) resolved three open questions and forced six adjustments against Phase-4 assumptions. Architecture unchanged — only constants, thresholds, and output shapes.

**Open questions closed by seed:**
- **AI maturity scoring** → structured object, not bare integer. Schema: `{score, confidence, justifications: [{signal, status, weight, confidence, source_url}, ...]}`. Six named signals: `ai_adjacent_open_roles`, `named_ai_ml_leadership`, `github_org_activity`, `executive_commentary`, `modern_data_ml_stack`, `strategic_communications`. Closes the Phase-0 "per-signal justification weights" gap.
- **Segment priority on multi-match** → 5-step ladder: (1) layoff+funding → S2, (2) new CTO → S3, (3) capability gap + AI≥2 → S4, (4) funding alone → S1, (5) otherwise abstain. Deterministic classifier, no LLM.
- **Abstain threshold** → `segment_confidence < 0.6`. Was deferred as "thin input → abstain" without a number; now explicit.

**Six adjustments vs Phase-4 assumptions:**

1. **S2 layoff-overrides-funding window is 120 days**, not "recent." Segment classifier must match the 120d window on `layoff_event` + fresh `funding_round`.
2. **Hiring surge threshold split:** claims-layer `HIRING_SURGE_MIN_POSTINGS = 3` stays (the assertion is still real at 3 postings). **Segment 1 qualification requires ≥5 open eng roles** — a judgment-layer filter on top of the claim, not a change to the claim tier. S2's post-layoff "≥3 open eng roles" matches the existing constant.
3. **S3 is narrower than the doc implied:** CTO/VP Eng change within 90 days AND headcount 50–500 AND no concurrent CFO/CEO transition. All three are judgment-layer filters on `leadership_change` claims.
4. **AI maturity output is fixed by schema** — prompt must return the justifications array, not a scalar. LLM wrapper already returns strings; prompt + response parser own the structured shape.
5. **Bench is real now.** Code reads `Challenge_Documents/tenacious_sales_data/seed/bench_summary.json` (36 engineers, 7 stacks, `fullstack_nestjs` committed to Modo Compass through Q3 2026). The Phase-4 example file becomes a placeholder-only demo. Availability claims must respect the committed-stack flag.
6. **Forbidden phrases list is authoritative, not hand-rolled.** Phase-7 `forbidden_phrases.py` codes against the seed style guide: "top talent," "world-class," "A-players," "rockstar," "ninja," unsubstantiated "cost savings," "bench" in prospect-facing text, plus subject-line and signature rules. Defers the rich regex list to Phase 7 but locks the source-of-truth now.

**Why these are constants-in-code, not live reads of seed files:** The seed pack is a one-time input. Translating its rules into constants in `agent/judgment/` and one bench-loader in `agent/evidence/sources/bench.py` keeps the judgment layer testable without file-system coupling. Exception: `bench_summary.json` is read at runtime because availability is a live fact, not a rule.

**New artifacts not yet read (non-blocking for Phase 5):**
- `schemas/competitor_gap_brief.schema.json` — Segment 4's output contract; Phase 5 `competitor_gap.py` can stub until Phase 6 needs it
- `schemas/discovery_call_context_brief.md` — Phase 8 integration point for Cal.com booking
- `seed/email_sequences/{cold,warm,reengagement}.md` — Phase 6 prompt inputs
- 5 discovery transcripts — optional few-shot grounding for Phase 6

## 2026-04-23 — Phase 5: Judgment layer

**What:** Four judgment modules implemented. `segment.py` (deterministic 5-step ladder), `icp.py` (thin DB-writing wrapper), `competitor_gap.py` (schema-valid stub), `ai_maturity.py` (LLM-adjudicated scorer with parser). Plus rubric prompt at `agent/prompts/ai_maturity_rubric.md`. 28 new tests in `tests/test_judgment.py`. Total: 86/86 green (target was ~70).

**Why the 5-step ladder is priority-ordered, not scored:** The ICP definition specifies strict priority: S2 dominates S1, S3 dominates S4. A scoring approach (sum weights, pick highest) would violate this — a company with a perfect S1 score but a marginal S2 layoff signal should still be S2. The ladder encodes priority as code structure (return on first match), not as weights that could be gamed by implementation drift.

**Why competitor_gap.py ships as a stub:** The competitor_gap_brief schema requires 5–10 peer companies scored on the same AI maturity rubric. This requires either live web scraping (not shipped yet) or a fixture pack of peer-company data (not in scope for Phase 5). The stub returns a schema-valid empty shape so downstream code can depend on the type contract without crashing. Honest: `gap_quality_self_check.all_peer_evidence_has_source_url = false`.

**Why ai_maturity.py exposes `parse_response()` as a public function:** The parser/validator is the testable surface — 12 tests exercise it against canned JSON without any LLM calls. The `judge()` function (which calls the LLM) is integration-tested separately. This separation keeps the 86-test suite free of network/cost dependencies.

**Why absent signals get weight ≤ "low" and unknown gets weight 0:** This is the Phase 5 decision on the memo's open question about absence semantics. "Absent" means we looked and found nothing — that IS weak evidence (a company with zero AI job postings probably isn't doing AI). "Unknown" means we couldn't check — that's missing data, not evidence of absence. The distinction prevents false-negative AI maturity scores from blocking S4 pitches to companies we simply haven't fully scraped yet.

**Bonus fix: builder now persists claim payload.** `_build_payload()` existed in `agent/claims/builder.py` but was never passed to `db.insert_claim`. The judgment layer needs structured payload data (amounts, dates, headcounts) to classify segments. One-line fix: added `payload=_build_payload(kind, relevant)` to the insert call. All existing claims tests still pass — the payload column was always nullable.

**Why segment confidence uses filter-count, not tier-weight:** Confidence = (qualifying filters fired) / (total qualifying filters for that segment). Simple, auditable, and matches the ICP definition's instruction: "confidence based on how many qualifying filters fired versus how many relied on weak or inferred signals." Tier bonuses (+0.05 per verified/corroborated claim) are additive — they reward evidence quality without dominating filter-count.

**Evidence test fix:** `test_collector_round_trip_via_db` and `test_collector_ignores_underscore_prefixed_keys` expected 5 evidence rows; now expect 6 after the company_metadata fixture addition in Phase 4.5.

## 2026-04-23 — Act I baseline: tau2-bench smoke run

**What:** Ran the first `tau2-bench` baseline with haiku 4.5 on both agent and user sides. Result was `0.50` average reward: 2/3 tasks solved, 1 infra-skipped. The skipped task hit an OpenAI auth failure because a third component is still reading a placeholder API key (`your_key_here`) instead of the OpenRouter-backed key.

**What failed:**
- `exchange_delivered_order_items` missed at the agent-logic level, not infra.
- One task passed cleanly.
- One task failed after 3 retries due to auth, likely from the judge / NL-assertion path or another default OpenAI initializer.

**Why this matters:** The baseline is usable, but it is not yet a fair read on model quality until the infra path is fully pointed at OpenRouter. The reward number is therefore a mix of real behavior and one environment issue.

**Next fix:** Trace the remaining OpenAI reference in `tau2-bench` and either point it to `OPENROUTER_API_KEY` + `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, or reconfigure that component to use the same OpenRouter-backed model path as the rest of the run.

## Next up

Phase 6 — actions layer. Email drafting with tier-inherited mood, channel selection, scheduling. The competitor_gap stub will be filled when peer-company fixtures or live scraping ships.
## 2026-04-23 â€” Interim submission packaging

**What:** Imported the official baseline artifacts from `Challenge_Documents/` into the repo deliverables package: `deliverables/baseline.md`, `eval/score_log.json`, and `eval/trace_log.jsonl`. Added `submission_checklist.md` as a local working tracker and ignored it in `.gitignore` so it stays out of the submission bundle.

**Why the challenge artifacts became the source of truth:** The tutor-provided baseline is the official comparison point for submission. Re-running our own baseline would only create noise and a risk of mismatched numbers. Copying the provided artifacts keeps the submission honest and aligned with the rubric.

**Why the checklist lives locally only:** The checklist is an execution aid, not a reviewer artifact. Ignoring it avoids accidental submission of an internal progress tracker.

## 2026-04-23 â€” CRM + calendar bridge

**What:** Upgraded the CRM/calendar path so HubSpot writes include ICP segment classification, signal enrichment payloads, enrichment timestamp, and booking state. Added a callable Cal.com booking wrapper and a scheduling action that books a discovery call and then writes the booking back to the same HubSpot prospect record. Added contract tests covering the handoff.

**Why the booking bridge matters:** The rubric does not just want a booking API wrapper; it wants the booking event to be traceable back into CRM for the same prospect. The scheduling action makes that relationship explicit instead of leaving it to caller discipline.

**Why the CRM payload is richer than identity-only contact data:** The prospect record needs to carry the same evidence context the agent used for the outreach decision. Segment, enrichment data, and timestamps make the CRM record an audit artifact instead of a bare address book entry.

## 2026-04-23 â€” Signal enrichment pipeline

**What:** Added a reviewer-facing structured enrichment artifact at `agent/evidence/enrichment.py` and added live-facing helper entrypoints for Crunchbase ODM lookup, Playwright job-post scraping, layoffs.fyi CSV parsing, and leadership-change normalization. Added contract tests that prove the artifact carries per-signal confidence scores and that the source helpers parse representative inputs.

**Why the enrichment artifact sits above the evidence layer:** The raw loaders still do one job each â€” emit facts. The new artifact is a separate reviewer-facing summary that turns those facts into a structured, per-signal view without collapsing the provenance trail.

**Why the live-facing helper names matter:** The rubric asked for concrete pipeline coverage, so the helper entrypoints name the real acquisition mode directly instead of hiding behind fixture-only loader names. That keeps the code honest about what is still synthetic and what is ready to be wired to approved live inputs.

## 2026-04-23 â€” SMS warm-lead channel

**What:** Implemented the SMS handler path with an Africa's Talking wrapper, inbound webhook normalization, a downstream event callback, and a warm-lead gate that blocks cold outreach. Added the channel-selection helper and FastAPI route wiring, plus contract tests for outbound and inbound SMS behavior.

**Why SMS is gated behind prior email reply:** SMS is treated as a warm-lead channel, not a cold-outreach channel. The gate makes that hierarchy explicit in code so the caller cannot accidentally bypass it.

**Why the webhook route normalizes payloads instead of dead-ending:** Inbound replies need a downstream interface, even if the immediate consumer is just a callback. Normalization gives the rest of the system a stable provider-neutral event shape.

## 2026-04-23 â€” Synthetic end-to-end thread

**What:** Added a demo orchestrator in `agent/core.py` plus a CLI runner at `scripts/run_one_prospect.py` that executes one full synthetic prospect thread: evidence collection, claim building, judgment, citation-backed email draft, gate pass, outbound send, inbound reply normalization, qualification, scheduling, HubSpot update, and Cal.com booking. The script writes a run artifact under `outputs/runs/<timestamp>/`.

**Why the demo thread is synthetic but still useful:** The rubric wants one complete thread, and the safest way to prove it without depending on live credentials is to make the thread runnable in demo mode while preserving the same step ordering and artifact shape. That keeps the evidence honest and repeatable.

**Why the gate needed one extra signature exception:** The first pass correctly rejected the signature line as a “factual sentence.” Treating the project signature as a signature, not a claim, keeps citation enforcement strict without making normal email signoffs impossible.
## 2026-04-23 â€” Job-post source wiring

**What:** Tightened the job-post source so the Playwright path is a first-class live entrypoint instead of just a parsing helper. Added a configurable Playwright factory hook for testability, a live-facing `load_live_job_posts()` alias, and a browser-automation dependency entry in `requirements.txt`.

**Why the factory hook matters:** The live scraping path needs to be usable in production and still testable without a real browser in CI. Injecting the factory lets us verify the browser flow without depending on the external package being installed in the test runner.

**Why this is the first live source to wire:** Job posts are the most obviously routeable signal in the enrichment set and the least ambiguous to validate with rendered HTML. That makes it the right place to start before tackling the more source-specific CSV and ODM paths.

## 2026-04-23 â€” Layoffs CSV wiring

**What:** Added a live-facing layoffs CSV entrypoint with a `fetch_layoffs_csv()` helper and a `load_live_layoffs_csv()` alias. The parser now has a fetch layer that reads public CSV text without any login or captcha-bypass logic, and the enrichment tests cover the fetch path.

**Why layoffs stayed CSV-first:** Layoffs data is the cleanest source in the set to keep public and auditable. A CSV fetch path is enough to prove the ingestion contract while staying within the no-login, no-bypass rule.

**Why the helper split matters:** The fixture loader still handles synthetic tests, while the live-facing helper makes the public CSV ingestion path obvious and separately testable. That keeps the repo honest about what is simulated versus externally fetched.

## 2026-04-23 â€” HubSpot MCP route

**What:** Added a remote HubSpot MCP client wrapper for CRM writes and routed `integrations/hubspot_client.py` through it when `USE_HUBSPOT_MCP=true`. The SDK fallback remains in place for local dev, while the MCP path uses the remote server and an auth-app access token.

**Why this is the right compromise:** It gives us a real MCP integration without breaking the current smoke suite or forcing the repo to depend on a live OAuth flow during tests. Reviewers can see both the MCP implementation and the local fallback clearly.

## 2026-04-23 â€” Submission report draft

**What:** Added `deliverables/method.md` as a PDF-ready interim report draft and refreshed the README status line so it reflects the current implementation state instead of the early scaffold stage.

**Why this is the right packaging step:** The report draft makes the remaining submission work concrete. We can now export a real interim PDF from a current artifact instead of writing the narrative from scratch at the end.

## 2026-04-23 â€” Competitor gap brief

**What:** Added a reviewer-facing competitor gap brief under `deliverables/competitor_gap_brief.json` with a matching short markdown summary. The artifact is seed-backed and aligned to the challenge schema, so the submission package now includes the required one-prospect research brief.

**Why this is the right interim state:** The brief is honest about being seed-backed rather than live-scraped, which keeps the package credible while still satisfying the reviewer-facing artifact requirement.

## 2026-04-23 â€” Latency measurement harness

**What:** Added `scripts/measure_email_sms_latency.py` and documented the live-mode command in `README.md`. The script records per-run email send, email reply normalization, SMS send, SMS reply normalization, and total wall-clock timings into a JSONL log plus a summary JSON file.

**Why this is the right measurement shape:** The rubric asks for p50/p95 from real runs of the email + SMS flow. Timing each step separately makes the final report more transparent and gives us a reusable artifact if the reviewers ask how the numbers were derived.

## 2026-04-23 â€” Latency harness sink-phone fix

**What:** Added a `--sink-phone` override to the latency harness so live runs do not depend on `STAFF_SINK_PHONE_NUMBER` being present in `.env`. The harness now cleanly separates the Africa's Talking sender ID from the sink recipient number.

**Why this mattered:** The previous live invocation failed because the SMS wrapper had no sink destination to route to. The override makes the command self-contained and avoids accidental dependence on local env drift.

## 2026-04-23 â€” Live latency sample collected

**What:** Ran `scripts/measure_email_sms_latency.py --runs 20 --live` successfully and captured the live timing summary under `outputs/runs/latency-20260423-201603/`. The measured totals were p50 `1.1698s` and p95 `3.5083s`.

**Why this matters:** This closes the last rubric-required measurement gap in the interim package. The report can now cite real live timing data instead of synthetic estimates.
