# CLAUDE.md — Conversion Engine (TRP1 Week 10)

Read this fully before every response. This file defines the project, the architecture, the rules, and the skills available.

---

## 1. Project Context

**What this is:** An AI agent that finds tech companies likely to need Tenacious Consulting's engineering teams, researches them from public data, sends personalized evidence-backed emails, and books discovery calls — automatically.

**The real challenge:** Not the automation. The system makes claims about real companies to real decision-makers on behalf of a real brand using imperfect public data. Every design decision flows from that.

**Framing:** This is a trust engineering problem — building a system that earns the right to make a claim before it makes one, at machine speed, on behalf of a brand that cannot afford to be wrong.

### The Client
- **Tenacious Consulting and Outsourcing** — real B2B firm, talent outsourcing + consulting
- Typical deal: 3–12 engineers, 6–24 months, ~$288K ACV (conservative)
- Current pain: 30–40% of qualified conversations stall in first 2 weeks due to slow follow-up

### ICP Segments
- **Segment 1:** Recently funded startups
- **Segment 2:** Mid-market restructuring
- **Segment 3:** Leadership transition (new CTO/VP Eng)
- **Segment 4:** Specialized capability gaps (AI/ML) — only pitched at AI maturity ≥ 2

### Minimum Uplift
- Stall rate: 40% → below 20%
- Response time: hours → under 5 minutes (acknowledgment only)
- Incorrect claims: zero
- Deployment gate: citation coverage + shadow-review survival + forbidden-phrase pass (all three)

### Deadlines
- **Wed Apr 22, 21:00 UTC** — Acts I + II (baseline + production stack)
- **Sat Apr 25, 21:00 UTC** — Acts III–V + demo video

---

## 2. Architecture — Epistemic Layering

The system is organized by **what kind of truth claim lives at each level**, not by function. Every failure mode in this project is a truth-claim failure, so layers are defined by the truth contract they enforce.

```
┌─────────────────────────────────────────────────────────┐
│ EVIDENCE    Raw facts. Append-only. Source + timestamp.  │
├─────────────────────────────────────────────────────────┤
│ CLAIMS      Derived assertions. Confidence tier attached.│
├─────────────────────────────────────────────────────────┤
│ JUDGMENT    ICP, segment, AI maturity. Cites claim_ids.  │
├─────────────────────────────────────────────────────────┤
│ ACTIONS     Email draft, channel choice, scheduling.     │
├─────────────────────────────────────────────────────────┤
│ GATE        Citation + shadow-review + phrase-regex.     │
└─────────────────────────────────────────────────────────┘
```

### Layer Contracts

**Evidence layer** — raw facts only. Each row: `{fact, source_url, retrieved_at, method}`. Immutable. No interpretation, no scoring. If you can't point to the row, the fact doesn't exist.

**Claims layer** — derived assertions ("Acme closed Series B on Apr 3"). Each claim is built from ≥N evidence rows and carries a tier:
- **Verified** — ≥2 independent primary sources, ≤7 days old → indicative mood
- **Corroborated** — 1 primary + 1 secondary, ≤30 days → hedged indicative
- **Inferred** — signals only, no direct confirmation → interrogative only
- **Below threshold** — invisible to downstream layers

**Judgment layer** — deterministic where possible (ICP, segment). LLM-adjudicated with citations where not (AI maturity tier, gap significance). Every judgment references the claim_ids that justify it. Thin input → abstain, never guess.

**Actions layer** — email draft, channel choice, scheduling. Every factual sentence references the claim(s) justifying it. No citation → can't appear in output. Grammatical mood is inherited from claim tier; the model does not choose.

**Gate layer** — pre-send validation with three deterministic checks:
1. Citation coverage — every factual sentence maps to a claim_id
2. Shadow review — second model adversarially searches for unsupported claims
3. Forbidden-phrase regex — no future-tense staff availability, no over-claiming phrases

Any gate failure → human queue, not retry.

### Fast Path vs Commitment Path

Two distinct message categories with different truth obligations:

- **Acknowledgment path (≤5 min):** "Saw your note — pulling context, back within the hour with specifics." Makes no factual claim beyond what the prospect said about themselves.
- **Commitment path (15–60 min):** Full research + claim assembly + gate. If claims don't clear the gate, routes to human — never degrades silently into fluff.

---

## 3. Folder Structure

```
conversion-engine/
├── .env                            # Gitignored — API keys
├── .gitignore
├── CLAUDE.md                       # This file
├── PRD.md                          # Product requirements + acceptance criteria
├── README.md                       # Status, team, setup
├── progress.md                     # Decision journal — what was tried/rejected
├── requirements.txt
│
├── .claude/
│   └── skills/                     # Project-scoped skills (see Section 5)
│       ├── claim-audit.md
│       ├── probe-author.md
│       └── gate-check.md
│
├── agent/
│   ├── __init__.py
│   ├── core.py                     # High-level loop only — stays thin
│   ├── router.py                   # Channel selection, fast-vs-commitment path
│   ├── state.py                    # Conversation session state
│   │
│   ├── evidence/                   # Layer 1 — raw facts
│   │   ├── collector.py            # Append-only writer
│   │   ├── schema.py               # {fact, source_url, retrieved_at, method}
│   │   └── sources/
│   │       ├── crunchbase.py
│   │       ├── job_posts.py
│   │       ├── layoffs.py
│   │       └── leadership.py
│   │
│   ├── claims/                     # Layer 2 — derived assertions
│   │   ├── builder.py              # Evidence → claim construction
│   │   ├── tiers.py                # verified / corroborated / inferred
│   │   └── confidence.py           # Tier assignment rules
│   │
│   ├── judgment/                   # Layer 3 — interpretation
│   │   ├── icp.py                  # Deterministic classifier
│   │   ├── segment.py              # Deterministic
│   │   ├── ai_maturity.py          # LLM-adjudicated with citations
│   │   └── competitor_gap.py       # Capability-overlap based
│   │
│   ├── actions/                    # Layer 4 — outputs
│   │   ├── email_draft.py          # Mood inherited from claim tier
│   │   ├── channel.py              # Email/SMS/voice selection
│   │   └── schedule.py
│   │
│   ├── gate/                       # Layer 5 — enforcement
│   │   ├── citation_check.py       # Every factual sentence → claim_id
│   │   ├── shadow_review.py        # Adversarial second-model pass
│   │   └── forbidden_phrases.py    # Regex filter
│   │
│   ├── prompts/                    # All LLM prompts as .md (auditable)
│   │   ├── system.md
│   │   ├── outreach_verified.md
│   │   ├── outreach_corroborated.md
│   │   ├── outreach_inferred.md
│   │   ├── acknowledgment.md
│   │   ├── shadow_adversarial.md
│   │   └── style_guide.md
│   │
│   └── handlers/
│       ├── email.py
│       ├── sms.py
│       └── webhooks.py
│
├── integrations/                   # One wrapper per external service
│   ├── email_client.py
│   ├── sms_client.py
│   ├── hubspot_client.py
│   ├── calcom_client.py
│   └── langfuse_client.py
│
├── api/
│   ├── server.py
│   └── routes/
│       ├── email_webhook.py
│       └── sms_webhook.py
│
├── storage/
│   ├── db.py                       # SQLite
│   ├── cache.py                    # Enrichment disk cache
│   └── schema.sql
│
├── eval/
│   ├── tau2_harness.py
│   ├── score_log.json
│   └── trace_log.jsonl
│
├── probes/                         # Act III
│   ├── probe_library.md
│   └── failure_taxonomy.md
│
├── data/
│   ├── companies/                  # Real public company records
│   ├── contacts_synthetic/         # Synthetic contact identities
│   ├── bench/                      # Tenacious bench summary
│   ├── fixtures/                   # Eval-only test data
│   └── cache/
│
├── outputs/
│   └── runs/<timestamp>/
│       ├── evidence.jsonl
│       ├── claims.jsonl
│       ├── judgment.json
│       ├── draft.md
│       └── gate_report.json
│
├── deliverables/                   # What reviewers read
│   ├── baseline.md
│   ├── method.md
│   ├── memo.pdf
│   └── evidence_graph.json
│
├── docs/                           # Internal working docs
│   ├── architecture.md
│   └── methodology_notes.md
│
├── scripts/
│   └── day0_check.py
│
└── tests/
    ├── test_gate.py                # Trust layer tested FIRST
    ├── test_claims.py
    ├── test_judgment.py
    └── test_integrations.py
```

---

## 4. Rules (Non-Negotiable)

These rules govern how code is proposed and reviewed in this project. Violations are failures, not style preferences.

### R1 — Plan Before Coding
For any change touching more than one file or introducing new logic: propose a plan first. Wait for approval. No speculative implementation.

### R2 — Epistemic Layering Is Sacred
- Evidence layer never interprets
- Claims layer never asserts without tier + source
- Judgment layer never reads raw evidence (only claims)
- Actions layer never creates claims (only consumes them)
- Gate layer never modifies drafts (only passes or rejects)

Cross-layer leakage is a bug, not a shortcut.

### R3 — Every Factual Sentence Needs a Citation
No email draft may contain a factual claim without a `{claim_id}` annotation. Rendering without citation → gate rejection.

### R4 — Tier Dictates Mood
The LLM does not choose sentence mood. Claim tier does:
- Verified → indicative
- Corroborated → hedged indicative
- Inferred → interrogative
- Below threshold → not referenced

Violations are detectable with regex at the gate.

### R5 — Simplicity First
- No features beyond what was asked
- No abstractions for single-use code
- No error handling for impossible scenarios
- If 200 lines can be 50, rewrite

### R6 — Surgical Changes
- Don't improve adjacent code
- Don't refactor things that aren't broken
- Match existing style
- Every changed line traces to the user's request

### R7 — Abstain on Thin Input
If evidence is below threshold, the system abstains. It does not guess, does not degrade gracefully into generics, does not "hedge into fluff." Human queue is the fallback.

### R8 — No Future-Tense Staff Availability
Gate-level regex forbids phrases like "engineers ready," "availability this week," or any claim about specific timing without a bench-summary citation. Claim-level rule: any sentence implying availability needs a citation to `data/bench/`.

### R9 — Synthetic Contacts Only This Week
Every outbound message this week routes to the staff sink. Real prospect contact requires explicit approval flag in `.env`. Default: sink.

### R10 — Cost Discipline
Total budget: under $20/week. Every LLM call logs to Langfuse with cost. Runaway token usage is a probe category, not a bug to ignore.

---

## 5. Skills Available (`.claude/skills/`)

Project-scoped skills for common tasks. Invoke with `/claim-audit`, `/probe-author`, `/gate-check`.

| Skill | Purpose |
|---|---|
| `claim-audit` | Given a draft email, check citation coverage + tier-mood compliance |
| `probe-author` | Given a failure category, generate a structured adversarial probe |
| `gate-check` | Run all pre-send validators on a draft and produce a gate report |

See individual skill files for invocation details.

---

## 6. Session Resume Protocol

Open every new chat with:

> "Read CLAUDE.md, PRD.md, README.md, and progress.md in order. Confirm understanding and tell me where we left off."

This replaces ad-hoc memory checks. 30 seconds, full context restored.

---

## 7. User Profile

- Trainee at 10 Academy (nebiyoua@10academy.org)
- Oracle Forge veteran — familiar with probe/eval methodology from prior project
- Prefers plain-English, conversational answers over formal writing
- Pushes back when answers sound like document summaries
- Presents insights on Slack and in standups
