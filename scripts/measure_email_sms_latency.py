"""Measure email + SMS flow latency across repeated runs."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agent.actions.email_draft import build_commitment_email
from agent.handlers import email as email_handler
from agent.handlers import sms as sms_handler
from integrations import sms_client


@dataclass(frozen=True)
class RunLatency:
    run_index: int
    total_seconds: float
    email_send_seconds: float
    email_reply_normalize_seconds: float
    sms_send_seconds: float
    sms_reply_normalize_seconds: float
    email_message_id: str
    sms_message_id: str
    timestamp_utc: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if len(values) == 1:
        return values[0]
    values = sorted(values)
    index = (len(values) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    if lower == upper:
        return values[lower]
    weight = index - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _require_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise SystemExit(f"{names[0]} is required for live latency measurement")


def _resolve_sink_phone(override: str | None) -> str:
    if override:
        return override
    value = os.getenv("STAFF_SINK_PHONE_NUMBER")
    if value:
        return value
    raise SystemExit(
        "STAFF_SINK_PHONE_NUMBER is required for live latency measurement "
        "(pass --sink-phone or set it in .env)"
    )


def _configure_sms_sink(sink_phone: str | None) -> str | None:
    resolved = _resolve_sink_phone(sink_phone)
    sms_client._SINK = resolved  # type: ignore[attr-defined]
    sms_handler.sms_client._SINK = resolved  # type: ignore[attr-defined]
    os.environ["STAFF_SINK_PHONE_NUMBER"] = resolved
    return resolved


def _build_email_subject(company_name: str) -> str:
    return f"Quick note for {company_name}"


def _build_email_body(company_name: str) -> str:
    draft = build_commitment_email(
        company_name=company_name,
        prospect_name="Prospect",
        claim_rows=[],
        segment_match="segment_4_specialized_capability",
    )
    return draft["body"]


def _run_single_iteration(*, run_index: int, live: bool, sink_phone: str | None) -> RunLatency:
    company_name = f"Latency Prospect {run_index}"
    email_body = _build_email_body(company_name)
    subject = _build_email_subject(company_name)

    start = time.perf_counter()

    email_send_start = time.perf_counter()
    if live:
        email_message_id = email_handler.send_outbound_email("prospect@example.com", subject, email_body)
    else:
        email_message_id = f"demo-email-{run_index}"
    email_send_seconds = time.perf_counter() - email_send_start

    email_reply_start = time.perf_counter()
    email_handler.handle_webhook_payload(
        {
            "event": "inbound.reply",
            "message_id": email_message_id,
            "from": "prospect@example.com",
            "to": "sales@tenacious.co",
            "subject": f"Re: {subject}",
            "text": "Thanks, let's continue over SMS.",
        }
    )
    email_reply_normalize_seconds = time.perf_counter() - email_reply_start

    sms_send_start = time.perf_counter()
    if live:
        sms_result = sms_handler.send_warm_lead_sms(
            _resolve_sink_phone(sink_phone),
            f"Thanks for the email, following up by SMS for {company_name}.",
            prior_email_reply=True,
            is_warm_lead=True,
            sender_id=os.getenv("AFRICASTALKING_SENDER_ID") or os.getenv("AT_SHORTCODE"),
        )
        sms_message_id = str(sms_result.get("message_id") or sms_result.get("raw") or f"sms-{run_index}")
    else:
        sms_message_id = f"demo-sms-{run_index}"
    sms_send_seconds = time.perf_counter() - sms_send_start

    sms_reply_start = time.perf_counter()
    sms_handler.handle_webhook_payload(
        {
            "event": "inbound.reply",
            "message_id": sms_message_id,
            "from": _resolve_sink_phone(sink_phone) if live else "+254700000000",
            "to": "sales@tenacious.co",
            "text": "Got it, thanks.",
        }
    )
    sms_reply_normalize_seconds = time.perf_counter() - sms_reply_start

    total_seconds = time.perf_counter() - start

    return RunLatency(
        run_index=run_index,
        total_seconds=total_seconds,
        email_send_seconds=email_send_seconds,
        email_reply_normalize_seconds=email_reply_normalize_seconds,
        sms_send_seconds=sms_send_seconds,
        sms_reply_normalize_seconds=sms_reply_normalize_seconds,
        email_message_id=email_message_id,
        sms_message_id=sms_message_id,
        timestamp_utc=_now_iso(),
    )


def _summarize(runs: list[RunLatency]) -> dict[str, Any]:
    totals = [run.total_seconds for run in runs]
    email_send = [run.email_send_seconds for run in runs]
    email_reply = [run.email_reply_normalize_seconds for run in runs]
    sms_send = [run.sms_send_seconds for run in runs]
    sms_reply = [run.sms_reply_normalize_seconds for run in runs]

    return {
        "count": len(runs),
        "p50_total_seconds": _percentile(totals, 0.5),
        "p95_total_seconds": _percentile(totals, 0.95),
        "p50_email_send_seconds": _percentile(email_send, 0.5),
        "p95_email_send_seconds": _percentile(email_send, 0.95),
        "p50_email_reply_normalize_seconds": _percentile(email_reply, 0.5),
        "p95_email_reply_normalize_seconds": _percentile(email_reply, 0.95),
        "p50_sms_send_seconds": _percentile(sms_send, 0.5),
        "p95_sms_send_seconds": _percentile(sms_send, 0.95),
        "p50_sms_reply_normalize_seconds": _percentile(sms_reply, 0.5),
        "p95_sms_reply_normalize_seconds": _percentile(sms_reply, 0.95),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure email + SMS flow latency.")
    parser.add_argument("--runs", type=int, default=20, help="Number of runs to record.")
    parser.add_argument("--live", action="store_true", help="Use live providers instead of demo mode.")
    parser.add_argument(
        "--sink-phone",
        default=None,
        help="Phone number that receives the warm-lead SMS during live measurement.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/runs",
        help="Directory where run artifacts and latency logs should be written.",
    )
    args = parser.parse_args()

    if args.runs < 20:
        raise SystemExit("--runs must be at least 20 for the rubric")

    if args.live:
        _require_env("RESEND_API_KEY")
        _require_env("AT_USERNAME", "AFRICASTALKING_USERNAME")
        _require_env("AT_API_KEY", "AFRICASTALKING_API_KEY")
        _configure_sms_sink(args.sink_phone)

    output_dir = Path(args.output_dir) / f"latency-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    runs: list[RunLatency] = []
    log_path = output_dir / "latency_log.jsonl"

    with log_path.open("w", encoding="utf-8") as fh:
        for i in range(1, args.runs + 1):
            record = _run_single_iteration(run_index=i, live=args.live, sink_phone=args.sink_phone)
            runs.append(record)
            fh.write(json.dumps(asdict(record), sort_keys=True) + "\n")
            fh.flush()

    summary = _summarize(runs)
    summary["mode"] = "live" if args.live else "demo"
    summary["output_dir"] = str(output_dir)
    summary_path = output_dir / "latency_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(str(output_dir))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
