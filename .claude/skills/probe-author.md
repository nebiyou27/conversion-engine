---
name: probe-author
description: Generate a structured adversarial probe for Act III given a failure category. Use when building the probe library, when a real-world failure needs encoding as a test, or when stress-testing the agent against a specific weakness.
---

# Probe Author

Generate an adversarial probe in the structured format required for Act III deliverables.

## When to invoke

- Building out `probes/probe_library.md` (target: 30+ probes)
- After observing a failure in real runs — encode it as a probe so it can't regress
- When the user names a failure category that doesn't yet have coverage

## Probe categories (from the challenge doc)

1. ICP misclassification
2. Signal over-claiming
3. Bench over-commitment
4. Tone drift from Tenacious style guide
5. Multi-thread leakage
6. Cost pathology
7. Dual-control coordination
8. Scheduling edge cases (EU/US/East Africa timezones)
9. Signal reliability (false-positive rates)
10. Gap over-claiming from competitor brief

## Probe schema

```markdown
## Probe NNN — <short title>

**Category:** <one of the 10 above>
**Severity axis:** detectable | silent  ·  reversible | not  ·  one-target | many
**Priority:** harm × (1 / detectability)

### Scenario
<2-4 sentences: the synthetic prospect's profile and the input state>

### Expected failure mechanism
<What the agent is likely to do wrong, and why — mechanism, not symptom>

### Business cost
<Derived in Tenacious terms: ACV impact, stall-rate impact, or brand-reputation cost.
Use concrete dollar figures where possible (reference ~$288K ACV for a 4-engineer 9-month deal).>

### Detection method
<How you'd catch this in a trace or metric>

### Fix applied
<The mechanism change made — link to the file/function if implemented>

### Status
planned | triggered | fixed | monitoring
```

## Authoring rules

### R1 — Every probe must be adversarial, not happy-path
A probe that the agent passes on its first attempt is not a probe. A probe must describe a plausible failure mode.

### R2 — Business cost must be concrete
"Damages brand" is not a cost. "One mis-pitched Segment 4 email to a score-0 prospect costs a $288K potential deal plus N warm introductions in their network" is a cost.

### R3 — Severity axis is not optional
Silent, irreversible, many-target failures deserve the most mitigation budget. Classify explicitly.

### R4 — Mechanism over symptom
"The agent sent a bad email" is a symptom. "The agent treated a post-layoff company as Segment 1 because layoffs.fyi was queried after the funding check and the result was discarded" is a mechanism.

### R5 — Cite the trace
Where possible, reference a real trace ID from `trace_log.jsonl` that demonstrates the probe triggering. A probe without a trace is a hypothesis; a probe with a trace is evidence.

## Oracle Forge transfer

The user has prior experience with probe libraries from Oracle Forge. The schema here is a superset — same structure, new categories, plus the severity axis and business cost fields that are specific to this project's brand-safety focus.

## Example invocation

User says: "Give me a probe for ICP misclassification on a post-layoff company."

Assistant produces one complete probe following the schema, with concrete dollar cost, mechanism-level failure description, and a proposed fix. No padding, no commentary outside the probe.
