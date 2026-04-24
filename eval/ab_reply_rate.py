"""Run A/B outreach draft variants and LLM-judge likely reply rate.

Phase A4 measurement:
  - 4 fixtures x 2 variants x 8 trials = 64 Qwen draft calls
  - 64 DeepSeek judge calls: "Would a busy CTO reply? yes/no."
  - emit eval/ab_reply_rate_report.json with rates, n, and delta pp
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.claims import builder
from agent.evidence import collector
from agent.judgment import segment
from integrations.llm import MODELS, BudgetLedger, complete
from storage import db

NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
DEFAULT_FIXTURES = [
    Path("data/fixtures/companies/acme_series_b.json"),
    Path("data/fixtures/companies/contradicted_co.json"),
    Path("data/fixtures/companies/shadow_startup.json"),
    Path("data/fixtures/companies/silent_sophisticate.json"),
]
DEFAULT_OUTPUT = Path("eval/ab_reply_rate_report.json")
PROMPT_DIR = Path("agent/prompts")
VARIANTS = {
    "signal_grounded": PROMPT_DIR / "outreach_signal_grounded.md",
    "generic": PROMPT_DIR / "outreach_generic.md",
}


@dataclass(frozen=True)
class DraftResult:
    subject: str
    body: str


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _claims_for_company(conn: sqlite3.Connection, company_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM claims WHERE company_id = ? ORDER BY built_at, claim_id",
        (company_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("payload")
    if not raw:
        return {}
    return json.loads(raw) if isinstance(raw, str) else raw


def _heuristic_ai_maturity(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Cheap local score so A4 spends calls only on draft + reply judge."""
    titles: list[str] = []
    for claim in claims:
        if claim.get("kind") == "hiring_surge":
            titles.extend(_payload(claim).get("titles") or [])

    ai_terms = ("ai", "ml", "machine learning", "data science", "llm")
    hits = [title for title in titles if any(term in title.lower() for term in ai_terms)]
    if len(hits) >= 2:
        score = 3
    elif hits:
        score = 2
    else:
        score = 0

    return {
        "score": score,
        "confidence": 0.75 if hits else 0.3,
        "signals": [
            {
                "signal": "ai_adjacent_open_roles",
                "status": f"{len(hits)} matching role(s)" if hits else "absent",
                "confidence": "high" if hits else "low",
                "examples": hits[:3],
            }
        ],
    }


def _competitor_gap_stub(ai_maturity: dict[str, Any], segment_result: dict[str, Any]) -> dict[str, Any]:
    has_gap = (
        ai_maturity["score"] >= 2
        and segment_result["primary_segment_match"] == "segment_4_specialized_capability"
    )
    return {
        "status": "suggestive_gap" if has_gap else "not_established",
        "confidence": "medium" if has_gap else "low",
        "summary": (
            "AI maturity plus hiring suggests a specialized capability gap."
            if has_gap
            else "No high-confidence competitor gap established in this fixture."
        ),
    }


def build_context(fixture_path: Path) -> dict[str, Any]:
    fixture = _load_json(fixture_path)
    conn = db.connect(":memory:")
    try:
        db.init(conn)
        collector.collect(fixture, conn)
        builder.build(conn, fixture["company_id"], now=NOW)
        claims = _claims_for_company(conn, fixture["company_id"])
        ai_maturity = _heuristic_ai_maturity(claims)
        segment_result = segment.classify(
            claims,
            now=NOW,
            ai_maturity_score=ai_maturity["score"],
        )
    finally:
        conn.close()

    return {
        "company_id": fixture["company_id"],
        "company_name": fixture["name"],
        "prospect_role": "CTO",
        "claims": [
            {
                "claim_id": c["claim_id"],
                "kind": c["kind"],
                "tier": c["tier"],
                "assertion": c["assertion"],
                "payload": _payload(c),
            }
            for c in claims
        ],
        "segment": segment_result,
        "ai_maturity": ai_maturity,
        "competitor_gap": _competitor_gap_stub(ai_maturity, segment_result),
    }


def _draft_messages(variant: str, context: dict[str, Any], trial_index: int) -> list[dict[str, str]]:
    prompt = VARIANTS[variant].read_text(encoding="utf-8")
    if variant == "generic":
        context = {
            "company_name": context["company_name"],
            "prospect_role": context["prospect_role"],
        }
    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                "Return only valid JSON with keys subject and body. "
                "Do not include markdown fences or explanatory text.\n"
                f"trial_index: {trial_index}\n"
                f"context: {json.dumps(context, sort_keys=True)}"
            ),
        },
    ]


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


def parse_draft(text: str) -> DraftResult:
    try:
        parsed = _extract_json_object(text)
        subject = str(parsed.get("subject", "")).strip()
        body = str(parsed.get("body", "")).strip()
    except json.JSONDecodeError:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        subject = ""
        body_lines: list[str] = []
        in_body = False
        for line in lines:
            lower = line.lower()
            if lower.startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                in_body = False
            elif lower.startswith("body:"):
                body_lines.append(line.split(":", 1)[1].strip())
                in_body = True
            elif in_body:
                body_lines.append(line)
        body = "\n".join(body_lines).strip()
    if not subject or not body:
        raise ValueError(f"Draft response missing subject/body: {text!r}")
    return DraftResult(subject=subject, body=body)


def _judge_messages(context: dict[str, Any], draft: DraftResult) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are judging outbound email quality for a busy CTO. "
                "Answer only JSON: {\"reply\": true|false, \"reason\": \"...\"}. "
                "Reply true only if the CTO would plausibly respond."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "company_name": context["company_name"],
                    "prospect_role": context["prospect_role"],
                    "subject": draft.subject,
                    "body": draft.body,
                },
                sort_keys=True,
            ),
        },
    ]


def parse_judgment(text: str) -> dict[str, Any]:
    parsed = _extract_json_object(text)
    reply_raw = parsed.get("reply")
    if isinstance(reply_raw, str):
        reply = reply_raw.strip().lower() in {"true", "yes", "y"}
    else:
        reply = bool(reply_raw)
    return {
        "reply": reply,
        "reason": str(parsed.get("reason", "")).strip(),
    }


def _draft_once(
    *,
    variant: str,
    context: dict[str, Any],
    trial_index: int,
    run_id: str,
    ledger: BudgetLedger,
    client: Any | None,
    attempt: int,
) -> tuple[DraftResult, Any]:
    draft_resp = complete(
        _draft_messages(variant, context, trial_index),
        run_id=run_id,
        ledger=ledger,
        model=MODELS["qwen"],
        max_tokens=600 + ((attempt - 1) * 300),
        temperature=0.7 if attempt == 1 else 0.3,
        client=client,
        metadata={
            "name": "ab_draft",
            "variant": variant,
            "company_id": context["company_id"],
            "trial_index": trial_index,
            "attempt": attempt,
        },
    )
    return parse_draft(draft_resp.text), draft_resp


def draft_with_retries(
    *,
    variant: str,
    context: dict[str, Any],
    trial_index: int,
    run_id: str,
    ledger: BudgetLedger,
    client: Any | None,
    max_attempts: int = 3,
) -> tuple[DraftResult, Any, int]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            draft, resp = _draft_once(
                variant=variant,
                context=context,
                trial_index=trial_index,
                run_id=run_id,
                ledger=ledger,
                client=client,
                attempt=attempt,
            )
            return draft, resp, attempt
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
    raise ValueError(
        f"Could not parse draft after {max_attempts} attempts for "
        f"{context['company_id']} {variant} trial={trial_index}: {last_error}"
    )


def judge_with_retries(
    *,
    context: dict[str, Any],
    draft: DraftResult,
    variant: str,
    trial_index: int,
    run_id: str,
    ledger: BudgetLedger,
    client: Any | None,
    max_attempts: int = 3,
) -> tuple[dict[str, Any], Any, int]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        judge_resp = complete(
            _judge_messages(context, draft),
            run_id=run_id,
            ledger=ledger,
            model=MODELS["deepseek"],
            max_tokens=300,
            temperature=0.0,
            client=client,
            metadata={
                "name": "ab_reply_judge",
                "variant": variant,
                "company_id": context["company_id"],
                "trial_index": trial_index,
                "attempt": attempt,
            },
        )
        try:
            return parse_judgment(judge_resp.text), judge_resp, attempt
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
    raise ValueError(
        f"Could not parse judge after {max_attempts} attempts for "
        f"{context['company_id']} {variant} trial={trial_index}: {last_error}"
    )


def build_report(
    *,
    trials: int = 8,
    fixture_paths: list[Path] | None = None,
    run_id: str = "ab-reply-rate-a4",
    ledger: BudgetLedger | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    fixture_paths = fixture_paths or DEFAULT_FIXTURES
    ledger = ledger or BudgetLedger(run_id=run_id)
    details: list[dict[str, Any]] = []

    for fixture_path in fixture_paths:
        context = build_context(fixture_path)
        for variant in VARIANTS:
            for trial_index in range(1, trials + 1):
                draft, draft_resp, draft_attempts = draft_with_retries(
                    variant=variant,
                    context=context,
                    trial_index=trial_index,
                    client=client,
                    run_id=run_id,
                    ledger=ledger,
                )

                judgment, judge_resp, judge_attempts = judge_with_retries(
                    context=context,
                    draft=draft,
                    variant=variant,
                    trial_index=trial_index,
                    run_id=run_id,
                    ledger=ledger,
                    client=client,
                )

                details.append({
                    "company_id": context["company_id"],
                    "variant": variant,
                    "trial_index": trial_index,
                    "subject": draft.subject,
                    "body": draft.body,
                    "judge_reply": judgment["reply"],
                    "judge_reason": judgment["reason"],
                    "draft_cost_usd": draft_resp.cost_usd,
                    "judge_cost_usd": judge_resp.cost_usd,
                    "draft_attempts": draft_attempts,
                    "judge_attempts": judge_attempts,
                })

    variants: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        rows = [row for row in details if row["variant"] == variant]
        replies = sum(1 for row in rows if row["judge_reply"])
        n = len(rows)
        variants[variant] = {
            "n": n,
            "reply_count": replies,
            "reply_rate": replies / n if n else None,
        }

    sg = variants["signal_grounded"]["reply_rate"]
    generic = variants["generic"]["reply_rate"]
    delta_pp = None if sg is None or generic is None else round((sg - generic) * 100, 2)

    return {
        "run_id": run_id,
        "definition": "LLM-judged likely CTO reply to first-touch outbound email",
        "judge_question": "Would a busy CTO reply?",
        "fixtures": [str(path) for path in fixture_paths],
        "trials_per_fixture_per_variant": trials,
        "variants": variants,
        "delta_pp_signal_grounded_minus_generic": delta_pp,
        "sample_size_caveat": "n=32/arm is suggestive, not a production reply-rate estimate.",
        "ledger": ledger.get_summary(),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run A/B judged reply-rate evaluation.")
    parser.add_argument("--trials", type=int, default=8)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--run-id", default="ab-reply-rate-a4")
    parser.add_argument("--budget-usd", type=float, default=0.50)
    args = parser.parse_args()

    ledger = BudgetLedger(run_id=args.run_id, ceiling_usd=args.budget_usd)
    report = build_report(trials=args.trials, run_id=args.run_id, ledger=ledger)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "variants": report["variants"],
        "delta_pp_signal_grounded_minus_generic": report["delta_pp_signal_grounded_minus_generic"],
        "spent_usd": report["ledger"]["spent_usd"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
