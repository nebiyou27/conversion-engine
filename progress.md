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

## Next up

Phase 4 — claims layer. Evidence → tiered assertions with `verified` / `corroborated` / `inferred` / `below_threshold`. Tier thresholds are time-based; aged-retrieved_at path is already wired for this.
