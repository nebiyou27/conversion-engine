# Interim Submission Report

## Architecture Overview

Conversion Engine is organized by epistemic responsibility, not just by workflow. The pipeline moves from evidence collection to claims, then judgment, actions, and finally gating. That separation keeps raw facts, interpreted signals, and outbound messages from collapsing into one another.

## Key Design Decisions

- Epistemic layering is enforced in code and in directory structure.
- Claims are tiered so the system can distinguish verified, corroborated, inferred, and below-threshold states.
- Outbound messaging is gated before send-time so unsupported assertions do not leave the system.
- SMS is treated as a warm-lead channel and is blocked for cold outreach.
- HubSpot writes now support a remote MCP route, with the SDK kept as a local fallback for development.

## Production Stack Verification

The following integrations have been wired and smoke-tested in the repo:

- Resend for outbound email.
- HubSpot for CRM writes.
- Cal.com for booking.
- Langfuse for tracing.
- Africa's Talking for SMS.

## Enrichment Pipeline Status

The enrichment pipeline covers four source classes:

- Crunchbase ODM lookup.
- Job-post scraping via Playwright.
- layoffs.fyi CSV ingestion.
- Leadership-change normalization.

The merged enrichment artifact includes per-signal confidence values so the reviewer can inspect source-level strength instead of a single opaque score.

## End-to-End Evidence Thread

A synthetic prospect thread now runs end to end:

synthetic prospect -> evidence -> claims -> judgment -> email draft -> gate -> send -> reply normalization -> qualification -> booking -> HubSpot update

That run is written to `outputs/runs/<timestamp>/` for reviewer inspection.

## Baseline and Methodology

The official baseline artifacts from the challenge documents are checked into the repo deliverables package. They are treated as the source of truth for comparison rather than re-running a new baseline locally.

For the live latency sample, we ran `scripts/measure_email_sms_latency.py --runs 20 --live` and recorded the output under `outputs/runs/latency-20260423-201603/`. The measured totals were:

- p50 total latency: `1.1698s`
- p95 total latency: `3.5083s`
- p50 email send: `0.5811s`
- p95 email send: `2.9272s`
- p50 SMS send: `0.5725s`
- p95 SMS send: `0.7749s`

The normalization steps were effectively instantaneous relative to provider send time, which is expected because they are local webhook-shaping functions rather than provider round trips.

## What Works

- Core evidence, claims, judgment, actions, and gating layers are implemented.
- Email, SMS, CRM, and Cal.com integrations have contract tests.
- The synthetic thread demonstrates the intended handoff sequence.
- The enrichment sources are separately testable and documented.

## What Does Not Yet Work

- The interim PDF still needs to be exported from this draft.
- The competitor gap brief is present as a reviewer-facing artifact, but it is still seed-backed rather than live-scraped.

## Remaining-Day Plan

1. Export this draft into the required PDF submission.
2. Collect the latency sample and record p50/p95.
3. Do one last README and artifact polish pass.
