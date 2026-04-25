# Handoff Notes

## Known Limitations

- Synthetic demo runs use the real LLM by default. Set `DEMO_MODE=true` to fall
  back to the hardcoded AI maturity stub for offline tests; those artifacts
  label AI maturity as `source: hardcoded_demo_stub`. Non-demo runs call
  `agent.judgment.ai_maturity.judge()` through the Qwen-backed LLM wrapper.
- Job-post scraping is limited to BuiltIn, Wellfound, and public LinkedIn jobs
  search. A fourth domain should not be added without robots.txt verification
  and site-specific anchor tuning.
- Market Space Mapping is intentionally skipped. The distinguished-tier version
  needs hand-labeled peer validation that is outside the remaining budget.
- Automated-optimization baselines such as GEPA or AutoAgent were not run.
  Delta B is documented as a scope limitation after the 2026-04-24 reduction.
- The sealed held-out 20-task partition was not delivered in
  `Challenge_Documents/`; tau2 evaluation should disclose use of the 30-task
  dev slice.
- Voice is not implemented. The agent books discovery; a human Tenacious lead
  handles the actual call.
