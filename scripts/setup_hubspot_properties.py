"""One-time setup: create the custom contact properties this engine writes."""
from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

from integrations.retry import retry_call

load_dotenv()

TOKEN = os.getenv("HUBSPOT_TOKEN") or os.getenv("HUBSPOT_ACCESS_TOKEN")
if not TOKEN:
    print("ERROR: HUBSPOT_TOKEN (or HUBSPOT_ACCESS_TOKEN) not set in .env")
    sys.exit(1)

PROPERTIES = [
    {"name": "icp_segment", "label": "ICP Segment", "type": "string", "fieldType": "text"},
    {"name": "calcom_booking_id", "label": "Cal.com Booking ID", "type": "string", "fieldType": "text"},
    {"name": "calcom_booking_url", "label": "Cal.com Booking URL", "type": "string", "fieldType": "text"},
    {"name": "calcom_booking_status", "label": "Cal.com Booking Status", "type": "string", "fieldType": "text"},
    {"name": "enrichment_timestamp", "label": "Enrichment Timestamp", "type": "string", "fieldType": "text"},
    {"name": "signal_enrichment", "label": "Signal Enrichment", "type": "string", "fieldType": "textarea"},
]

URL = "https://api.hubapi.com/crm/v3/properties/contacts"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
TIMEOUT_SECONDS = float(os.getenv("HUBSPOT_SETUP_TIMEOUT_SECONDS", "45"))


def create_property(prop: dict[str, str]) -> bool:
    body = {**prop, "groupName": "contactinformation"}

    try:
        r = retry_call(
            lambda: requests.post(URL, headers=HEADERS, json=body, timeout=TIMEOUT_SECONDS),
            attempts=4,
            base_delay_seconds=1.0,
            retry_on=(requests.RequestException,),
            operation_name=f"HubSpot property setup {prop['name']}",
        )
    except requests.RequestException as exc:
        print(f"FAIL {prop['name']}: request failed after retries: {exc}")
        return False

    if r.status_code in (200, 201):
        print(f"OK: created {prop['name']}")
        return True
    if r.status_code == 409:
        print(f"OK: {prop['name']} already exists")
        return True

    print(f"FAIL {prop['name']}: {r.status_code} {r.text[:200]}")
    return False


failed = 0
for prop in PROPERTIES:
    if not create_property(prop):
        failed += 1

if failed:
    print(f"Completed with {failed} failed propert{'y' if failed == 1 else 'ies'}")
    sys.exit(1)

print("Done: HubSpot custom properties are ready")
