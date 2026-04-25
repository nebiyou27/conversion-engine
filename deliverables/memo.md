# Tenacious Conversion Engine - Decision Memo
**To:** Tenacious CEO and CFO  **From:** Nebiyou Abebe  **Date:** 2026-04-25

## 1. Problem
Tenacious loses opportunity in two places: it stalls after the first meaningful reply, and it sometimes sounds too certain when the signal is thin or sensitive. The measured stall rate in the live staff-sink / sandbox latency run is **0.0% (0/20)** with stall defined as "no outbound action within 300s of inbound reply normalization" ([eval/stall_rate_report.json](../eval/stall_rate_report.json)). That is materially better than the 30-40% stall baseline we were working from, so the delivery path is not the main bottleneck anymore.

The bigger problem is trust at machine speed. Reviewers expected us to build an agent that can move fast without hallucinating confidence. We did that by making the pipeline epistemic: **evidence -> claims -> judgment -> actions -> gate**. Downstream text only sees claim rows and confidence tiers, not raw scraps of web data. That is the core design choice that makes the rest of the memo meaningful ([docs/architecture.md](../docs/architecture.md), [deliverables/evidence_graph.json](../deliverables/evidence_graph.json)).

## 2. Mechanism
The mechanism is **signal-confidence-aware phrasing**. Confidence lives outside the model. The tier chosen from evidence shape determines the mood allowed in the draft, and the sensitivity axis can override that mood when even verified evidence would read as presumptuous.

| Tier | Mood allowed | What it means |
|---|---|---|
| verified | indicative | We have strong evidence and can state the claim plainly. |
| corroborated | hedged indicative | The signal is real, but we should keep a light hedge. |
| inferred | interrogative | The signal is suggestive, so the draft should ask rather than assert. |
| below_threshold | absent | Do not mention it downstream. |

Sensitivity matters because some claims are socially risky even when they are factually true. The sensitivity axis routes these kinds to interrogative or human-reviewed treatment: layoffs, AI maturity below threshold, capability-gap claims, and contradictory signals. That is what prevents the "verified but condescending" failure mode.

This is the practical fix for the target failure: the model cannot escalate tone unless it first escalates evidence tier, and tier escalation requires fabricating evidence rows that the gate will reject.

## 3. A/B Finding
The signal-grounded variant did **27/32 = 84.38%** reply rate, while the generic opener did **30/32 = 93.75%** ([eval/ab_reply_rate_report.json](../eval/ab_reply_rate_report.json)). The delta is **-9.38 pp** with **p = 0.0905**, so the result is directionally informative but not statistically decisive at this sample size.

The failure mode is **gap-condescension**. When the draft combines funding, hiring, AI maturity, and competitor-gap language, it can cross from "this may be relevant" into "we know your problem better than you do." That is especially risky on contradicted or sensitive companies. In other words, more signal was not automatically better; at some point it became socially expensive signal.

The takeaway is not that generic beats grounded. The takeaway is that grounded drafts need a sensitivity gate and a tighter rule for when to ask versus when to assert.

## 4. Delta A
On tau2 retail dev, our method scored **pass@1 = 0.529** versus the supplied Qwen baseline at **0.7267**, so the honest delta is **-0.197** ([deliverables/ablation_results.json](../deliverables/ablation_results.json), [deliverables/baseline.md](../deliverables/baseline.md)). This is a real shortfall, not a reframing exercise.

The most plausible reason is parser fragility on hard tasks: the thinking model sometimes returned empty or invalid JSON on the hardest cases, and the scorer treated that as a miss. So the mechanism itself is not necessarily the only thing underperforming; the evaluation path is also punishing structure failures as if they were full reasoning failures.

What would fix it:
- force the tau2 prompt to emit a strict schema with an explicit `abstain` object;
- add a repair pass for empty or invalid JSON before scoring;
- retry once on malformed structure instead of counting immediate failure;
- increase trials per task so the estimate is less noisy.

This is why Delta A should be read as "honest current performance," not "mechanism disproved."

\newpage

## 5. Pilot Recommendation
Use the system first on **timing signals**: funding, hiring velocity, and leadership transitions. Those are the positive signals most likely to help the team move faster without sounding accusatory. They are also the least likely to trigger the gap-condescension problem.

Gate **sensitive signals** to human review or force them into interrogative mode: layoffs, capability gaps, contradictory signals, and any claim that would sound like a diagnosis if a prospect read it back to us. That is the right balance between speed and respect.

For tau2, instruct the model to never emit empty JSON and to output an explicit abstain object when confidence is low. That change would make the eval reflect actual reasoning more faithfully and would reduce false misses from structure failure.

Recommendation: run a 30-day Segment 2 pilot, but only on timing signals at first. If reply quality holds and wrong-signal incidents stay below the guardrail, expand. If the gate starts catching too much condescension, keep the system as an evidence collector and not an autopilot.
