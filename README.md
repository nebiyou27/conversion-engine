# Conversion Engine

AI agent for automated, evidence-backed sales outreach on behalf of Tenacious Consulting and Outsourcing. Built for TRP1 Week 10.

## Status

Core implementation is in place. Evidence, judgment, actions, gating, SMS, CRM/calendar, and MCP routing are all wired; the remaining work is submission packaging and final report polish.

See `PRD.md` for acceptance criteria and `progress.md` for the decision log.

## Architecture

Epistemic layering - the system is organized by the kind of truth claim each layer handles, not by function. See `CLAUDE.md` Section 2 for the full contract.

```
EVIDENCE  ->  CLAIMS  ->  JUDGMENT  ->  ACTIONS  ->  GATE
raw facts     tiered      interp.     drafts     pre-send
              assertions  over        with       validation
                          claims      citations
```

## Rubric Implementation Map

| Rubric component | Files | Test |
|---|---|---|
| Outbound Email Handler | `integrations/email_client.py`, `agent/handlers/email.py` | `tests/test_email_handler.py` |
| SMS Handler | `integrations/sms_client.py`, `agent/handlers/sms.py` | `tests/test_sms_handler.py` |
| CRM + Calendar | `integrations/hubspot_client.py`, `integrations/hubspot_mcp_client.py`, `agent/actions/schedule.py` | `tests/test_crm_calendar.py`, `tests/test_hubspot_mcp_client.py` |
| Signal Enrichment | `agent/evidence/sources/*.py`, `agent/evidence/enrichment.py` | `tests/test_signal_enrichment.py` |

## CRM

HubSpot writes support two paths:

- `USE_HUBSPOT_MCP=true` routes contact create and update operations through the remote HubSpot MCP server at `https://mcp.hubspot.com/`.
- `HUBSPOT_TOKEN` remains as a local SDK fallback for development and smoke testing.

The MCP route expects an access token minted from a HubSpot MCP auth app. The auth app is created in HubSpot under Development > MCP Auth Apps, and the MCP client uses the remote server with OAuth 2.1 + PKCE outside the agent hot path.

## Quick start

```bash
# 1. Create virtualenv
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# or: .venv\Scripts\activate     # Windows cmd/PowerShell

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env template and fill in keys
cp .env.example .env
# edit .env with real API keys (never commit)

# 4. Run Day 0 smoke tests
python scripts/day0_check.py

# 5. Run a single end-to-end prospect
python scripts/run_one_prospect.py
```

## Key files

- `CLAUDE.md` - architecture, rules, skills index (read first)
- `PRD.md` - what we are building and the acceptance criteria
- `progress.md` - decision log
- `deliverables/` - reviewer-facing artifacts
- `.claude/skills/` - project-scoped skills: `claim-audit`, `probe-author`, `gate-check`

## Safety

All outbound traffic routes to `STAFF_SINK_EMAIL` by default. Real prospect contact requires `ALLOW_REAL_PROSPECT_CONTACT=true` in `.env`, which is only set after program-staff + Tenacious-executive approval.
