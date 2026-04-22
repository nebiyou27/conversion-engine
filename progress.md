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

## Next up

Phase 1 — Day 0 smoke tests for all 5 external services.
