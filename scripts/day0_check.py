"""Day 0 smoke tests. Verifies every external service is reachable.

Run from repo root:
    python scripts/day0_check.py

Exit code 0 if all pass, 1 if any fail.
"""
import os
import sys
import traceback
from pathlib import Path

# Make repo root importable when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()


def check_env_vars() -> tuple[bool, str]:
    """Verify required env vars are set."""
    required = [
        "OPENROUTER_API_KEY",
        "RESEND_API_KEY",
        "HUBSPOT_TOKEN",
        "CALCOM_API_KEY",
        "CALCOM_BOOKING_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "STAFF_SINK_EMAIL",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        return False, f"Missing env vars: {', '.join(missing)}"
    return True, "All required env vars set."


def check_resend() -> tuple[bool, str]:
    """Send a test email to the staff sink."""
    from integrations import email_client
    msg_id = email_client.send(
        to=os.getenv("STAFF_SINK_EMAIL"),
        subject="[Day 0 smoke test] Resend",
        html="<p>If you see this, Resend is working.</p>",
    )
    if not msg_id:
        return False, "Resend returned no message ID."
    return True, f"Resend OK — message ID: {msg_id}"


def check_hubspot() -> tuple[bool, str]:
    """Create a test contact and return its ID."""
    from integrations import hubspot_client
    import time
    test_email = f"day0-test-{int(time.time())}@example.com"
    contact_id = hubspot_client.upsert_contact(
        email=test_email,
        props={"firstname": "Day0", "lastname": "Smoke"},
    )
    return True, f"HubSpot OK — contact ID: {contact_id} ({test_email})"


def check_langfuse() -> tuple[bool, str]:
    """Log a trace and verify it flushes."""
    from integrations import langfuse_client
    t = langfuse_client.trace(
        name="day0-smoke-test",
        input={"check": "langfuse"},
        metadata={"phase": "day0"},
    )
    langfuse_client.flush()
    return True, f"Langfuse OK — trace logged."


def check_calcom() -> tuple[bool, str]:
    """Verify the booking URL is set (no API call — just config check)."""
    url = os.getenv("CALCOM_BOOKING_URL", "")
    if not url.startswith("https://cal.com/"):
        return False, f"CALCOM_BOOKING_URL looks invalid: {url}"
    return True, f"Cal.com booking URL set: {url}"


def main() -> int:
    checks = [
        ("Environment variables", check_env_vars),
        ("Resend (email)", check_resend),
        ("HubSpot (CRM)", check_hubspot),
        ("Langfuse (tracing)", check_langfuse),
        ("Cal.com (scheduling)", check_calcom),
    ]
    results = []
    for name, fn in checks:
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"EXCEPTION: {e}\n{traceback.format_exc()}"
        results.append((name, ok, msg))
        symbol = "PASS" if ok else "FAIL"
        print(f"[{symbol}] {name}: {msg}")

    print()
    failures = [r for r in results if not r[1]]
    if failures:
        print(f"{len(failures)} check(s) failed. See above.")
        return 1
    print("ALL DAY 0 SMOKE TESTS PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
