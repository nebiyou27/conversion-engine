# Target Failure Mode

## Named Failure

**Signal over-claiming under defensive replies.** When a prospect challenges a
signal, the agent can become more certain instead of re-grounding in the
evidence tier. This maps to the challenge category for hiring-signal
over-claiming and the probe-library mood/tier family.

## Business-Cost Derivation

- Typical ACV: $288K, modeled as a conservative 12-engineer, 24-month account.
- Stall baseline: 30-40% from Tenacious discovery context.
- Initial trigger estimate: 3% of Segment 2 conversations, pending measured
  canary runs.
- Lost-deal fraction on triggered failures: 50%.

Arithmetic: 1,000 leads x 0.03 trigger x 0.5 lost-deal fraction x $288K ACV =
**$4.32M/year exposure per 1,000 leads**.

## Alternatives Considered

**Bench over-commitment.** Similar ACV exposure, but addressable through a hard
bench-to-brief constraint: capacity claims must reference a bench summary.

**Tone drift after 5+ turns.** Important, but it requires turn-level memory and
conversation-state modeling beyond the current evidence-to-draft mechanism.

## Why This Target Wins

The failure is both high-cost and mechanism-addressable. Tier-mood mapping can
force inferred claims into questions, citation gates can block unsupported
claims, and shadow review can catch language that escalates beyond the claim
tier. That makes it a better near-term target than broader memory failures.
