# Tenacious Conversion Engine - Decision Memo
**To:** Tenacious CEO and CFO  **From:** Nebiyou Abebe  **Date:** 2026-04-25

## Executive Summary
We built an evidence-tiered outbound conversion engine that turns public signals into cited claims, segment judgments, gated drafts, and CRM/calendar handoff. The delivery path looks solved: **0/20 stalled threads = 0.0%** versus the **30-40%** manual stall baseline; claim-quality is still unproven because signal-grounded outbound lost to generic outbound by **-9.38 percentage points** in a small LLM-judged A/B test. **Recommendation: run a controlled 30-day Segment 2 A/B pilot at 150 qualified leads per week and $1,200 weekly budget, with generic as the control arm and grounded timing-signal copy as the treatment.**

## Cost Per Qualified Lead
**Qualified lead:** a prospect with an actionable segment match whose draft clears citation, shadow, and forbidden-phrase gates. In the current run artifacts, all **5/5** pipeline runs meet that definition: 3 Acme runs and 2 Meta runs passed the gate with non-abstain segment judgments (`outputs/runs/*/run.json`).

Headline pilot CPQL is the operating envelope, not the sandbox trace artifact:

| Input | Weekly pilot amount | Source / basis |
|---|---:|---|
| LLM + operator buffer | **$800** | pilot budget |
| Rig, enrichment, and review overhead | **$400** | hosted-runner/API/reviewer allowance |
| Total weekly budget | **$1,200** | recommendation |
| Qualified leads | **150/week** | pilot scope |

Pilot CPQL = **$1,200 / 150 qualified leads = $8.00 per qualified lead**, below a $20 challenge envelope and below a manual SDR touched-lead benchmark of roughly $45-80.

The sandbox ledger is only a sanity check that cost logging works:

| Input | Current measured amount | Source |
|---|---:|---|
| LLM spend | **$0.00041848** | `outputs/runs/20260425-033848/invoice_summary.json` |
| Rig usage | **local/sandbox only; no hosted minutes billed** | `outputs/runs/*` |
| Enrichment APIs | **$0.00 recorded** | fixture, public CSV, and sandbox paths |
| Qualified leads | **5** | gate-passed, actionable run artifacts |

Sandbox ledger CPQL = **$0.00041848 / 5 = $0.000084 per qualified lead**. Do not treat that as production economics; it excludes hosted rig time, paid enrichment, and human review.

## Speed-To-Lead Delta
**Stalled** means no outbound action within **300 seconds** of inbound reply normalization. The live staff-sink/sandbox latency run measured **0 stalled threads out of 20**, so the stalled-thread rate is **0.0%** (`eval/stall_rate_report.json`).

Against the manual baseline of **30-40%**, the measured delta is **-30 to -40 percentage points**. Caveat: this was not real-prospect production traffic; it proves the delivery path and reply normalization path under controlled conditions.

## Outbound Reply-Rate Delta
The completed A/B test compared two first-touch variants over **32 trials per arm** (`eval/ab_reply_rate_report.json`):

| Variant | Definition | Replies | Reply rate |
|---|---|---:|---:|
| Signal-grounded | cites claim IDs, AI maturity, and gap/timing signals | 27/32 | **84.38%** |
| Generic | normal SDR opener without research-grounded claims | 30/32 | **93.75%** |

Signal-grounded delta = **84.38% - 93.75% = -9.38 pp** with **p = 0.0905**. This contradicts a broad "grounded is better" rollout. It also does **not** prove that grounded timing-signal copy without gap language beats generic copy, because the treatment bundled timing signals with AI-maturity and competitor-gap language.

The follow-up A/B needed to isolate that mechanism is now defined as `timing_grounded` versus `generic` in `eval/ab_reply_rate.py`: run `python eval/ab_reply_rate.py --variants timing_grounded generic --output eval/ab_reply_rate_timing_only_report.json --run-id ab-reply-rate-timing-only`. The timing-only A/B was scoped, prompted, and tested but not executed in this submission window: OpenRouter returned `403 Key limit exceeded (weekly limit)`. The harness and prompt are in place; the run will execute on quota reset without code changes. Until that second report exists, the pilot recommendation is a learning design, not a claimed reply-rate lift.

## Pilot Scope
Proceed with a constrained A/B pilot, not broad autopilot.

- **Segment:** Segment 2 mid-market restructuring, because the stall baseline and defensive-reply risk are most directly tied to this motion.
- **Volume:** 150 qualified leads per week for 4 weeks, split 50/50 between generic control and grounded timing-signal treatment.
- **Budget:** $1,200 per week, split as $800 LLM / operator buffer and $400 enrichment, rig, and review overhead.
- **Success criterion:** within 30 days, grounded timing-signal treatment reaches **>=12%** human-judged reply rate and beats generic control by **>=2 pp**, stalled-thread rate remains **0%**, and wrong-signal or gap-condescension incidents stay **<5%** over any 100-email review window.
- **Expansion condition:** only add Segment 4 capability-gap language after the pilot shows grounded copy beats generic copy on real prospects.

## Public-Signal Lossiness In AI Maturity
AI maturity scoring is intentionally based on public signals, so it has predictable lossiness.

**False positive - AI-washing Series B.** A company can score high because public materials use AI language, but the company has no named AI leadership, no credible AI hiring, and no visible operating maturity. The agent's wrong action is to pitch Segment 4 capability help as if the need were established. Business impact: the outreach reads inattentive or condescending, wasting the touch and damaging Tenacious's brand with an engineering-generalist prospect.

**False negative - Silent Sophisticate.** A mature AI team can have private repos, no public ML roles, and no blog posts. The `silent_sophisticate` fixture captures this case: strong Series C and senior engineering hiring, but zero public AI vocabulary (`data/fixtures/companies/silent_sophisticate.json`). The agent's wrong action is to under-score AI maturity and skip a Segment 4 pitch, leaving potential ACV on the table.

## Unresolved Failure
The mechanism still does not fully solve **gap-condescension / signal over-claiming when several sensitive truths are combined**. This is probe **P33** in the probe library: **5/32 signal-grounded drafts = 15.6%** were rejected because the judge flagged layoff, AI-maturity, or competitor-gap language as intrusive or presumptuous (`probes/failure_taxonomy.md`).

The target failure doc models the related defensive-reply failure at **3% of Segment 2 conversations**, with **50%** of triggered failures losing a **$288K ACV** opportunity. On the normalized basis in that doc, **1,000 leads x 0.03 x 0.5 x $288K = $4.32M at-risk ACV per 1,000 leads** (`probes/target_failure_mode.md`). At the proposed pilot run-rate of **150 leads/week**, the 30-day exposure basis is **600 x 0.03 x 0.5 x $288K = $2.59M at-risk ACV**; annualized at the same run-rate, **7,800 x 0.03 x 0.5 x $288K = $33.7M**. Deploy anyway only with a kill switch: if wrong-signal rate exceeds 5% or P33 exceeds 5% in a rolling 100-email review, pause real prospect contact and route drafts to human review.
