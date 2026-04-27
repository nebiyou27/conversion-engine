"""HubSpot CRM wrapper with enrichment-aware writes."""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from integrations.retry import retry_call

load_dotenv()

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _get_client():
    try:
        from hubspot import HubSpot
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("hubspot-api-client package is not installed") from exc

    token = os.getenv("HUBSPOT_TOKEN")
    if not token:
        raise RuntimeError("HUBSPOT_TOKEN is required")
    return HubSpot(access_token=token)


def _use_mcp() -> bool:
    return os.getenv("USE_HUBSPOT_MCP", "false").lower() == "true"


def _get_mcp_client():
    from integrations.hubspot_mcp_client import HubSpotMCPClient

    return HubSpotMCPClient.from_env()


def _collect_missing_property_names(payload: Any) -> set[str]:
    missing: set[str] = set()
    if isinstance(payload, dict):
        error_code = payload.get("error") or payload.get("code")
        if error_code == "PROPERTY_DOESNT_EXIST":
            name = payload.get("name")
            if isinstance(name, str):
                missing.add(name)

            context = payload.get("context")
            if isinstance(context, dict):
                property_names = context.get("propertyName")
                if isinstance(property_names, list):
                    missing.update(name for name in property_names if isinstance(name, str))

        for value in payload.values():
            missing.update(_collect_missing_property_names(value))
    elif isinstance(payload, list):
        for item in payload:
            missing.update(_collect_missing_property_names(item))
    return missing


def _extract_missing_property_names(exc: BaseException) -> set[str]:
    texts = [str(getattr(exc, "body", "") or ""), str(exc)]
    missing: set[str] = set()
    for text in texts:
        if not text:
            continue
        try:
            missing.update(_collect_missing_property_names(json.loads(text)))
        except json.JSONDecodeError:
            pass
        missing.update(
            re.findall(r'Property \\"?([A-Za-z0-9_]+)\\"? does not exist', text)
        )
        missing.update(
            re.findall(r'"propertyName"\s*:\s*\[\s*"([^"]+)"\s*\]', text)
        )
    return missing


def _run_with_missing_property_fallback(
    operation: Callable[[dict[str, Any]], str],
    properties: dict[str, Any],
    *,
    api_exception_type: type[BaseException],
    operation_name: str,
) -> str:
    current = dict(properties)
    ignored: set[str] = set()

    while True:
        try:
            return operation(current)
        except api_exception_type as exc:
            missing = (_extract_missing_property_names(exc) & current.keys()) - {"email"}
            missing -= ignored
            if not missing:
                raise

            ignored.update(missing)
            current = {key: value for key, value in current.items() if key not in missing}
            logger.warning(
                "hubspot_unsupported_properties_ignored operation=%s properties=%s",
                operation_name,
                ",".join(sorted(missing)),
            )


def build_contact_properties(
    email: str,
    *,
    icp_segment: str | None = None,
    signal_enrichment: dict[str, Any] | None = None,
    enrichment_timestamp: str | None = None,
    company_name: str | None = None,
    booking_id: str | None = None,
    booking_url: str | None = None,
    booking_status: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the HubSpot contact payload used by this project."""
    properties: dict[str, Any] = {
        "email": email,
        "enrichment_timestamp": enrichment_timestamp or _now(),
    }
    if company_name:
        properties["company"] = company_name
    if icp_segment:
        properties["icp_segment"] = icp_segment
    if signal_enrichment:
        properties["signal_enrichment"] = json.dumps(signal_enrichment, sort_keys=True)
    if booking_id:
        properties["calcom_booking_id"] = booking_id
    if booking_url:
        properties["calcom_booking_url"] = booking_url
    if booking_status:
        properties["calcom_booking_status"] = booking_status
    if extra:
        properties.update(extra)
    return properties


def upsert_contact(
    email: str,
    props: dict[str, Any] | None = None,
    *,
    icp_segment: str | None = None,
    signal_enrichment: dict[str, Any] | None = None,
    enrichment_timestamp: str | None = None,
    company_name: str | None = None,
    booking_id: str | None = None,
    booking_url: str | None = None,
    booking_status: str | None = None,
) -> str:
    """Create a contact enriched with ICP and signal data.

    The write is intentionally richer than basic identity data so the CRM
    record can carry the same prospect context used by the agent.
    """
    properties = build_contact_properties(
        email,
        icp_segment=icp_segment,
        signal_enrichment=signal_enrichment,
        enrichment_timestamp=enrichment_timestamp,
        company_name=company_name,
        booking_id=booking_id,
        booking_url=booking_url,
        booking_status=booking_status,
        extra=props,
    )

    def _upsert_once() -> str:
        if _use_mcp():
            logger.info("hubspot_upsert_attempt mode=mcp email=%s", email)
            return _get_mcp_client().upsert_contact(email=email, properties=properties)

        from hubspot.crm.contacts import SimplePublicObjectInputForCreate, SimplePublicObjectInput
        from hubspot.crm.contacts.exceptions import ApiException

        logger.info("hubspot_upsert_attempt mode=sdk email=%s", email)
        client = _get_client()
        try:
            return _run_with_missing_property_fallback(
                lambda create_properties: client.crm.contacts.basic_api.create(
                    SimplePublicObjectInputForCreate(properties=create_properties)
                ).id,
                properties,
                api_exception_type=ApiException,
                operation_name="create_contact",
            )
        except ApiException as exc:
            if exc.status != 409:
                raise
            match = re.search(r"Existing ID:\s*(\d+)", str(exc.body or ""))
            if not match:
                raise
            existing_id = match.group(1)
            logger.info("hubspot_upsert_existing email=%s contact_id=%s", email, existing_id)
            return _run_with_missing_property_fallback(
                lambda update_properties: (
                    client.crm.contacts.basic_api.update(
                        existing_id,
                        SimplePublicObjectInput(properties=update_properties),
                    ),
                    existing_id,
                )[1],
                properties,
                api_exception_type=ApiException,
                operation_name="upsert_existing_contact",
            )

    contact_id = retry_call(
        _upsert_once,
        attempts=3,
        base_delay_seconds=0.3,
        operation_name="HubSpot upsert",
    )
    logger.info("hubspot_upsert_success email=%s contact_id=%s", email, contact_id)
    return contact_id


def update_contact(
    contact_id: str,
    *,
    email: str,
    props: dict[str, Any] | None = None,
    icp_segment: str | None = None,
    signal_enrichment: dict[str, Any] | None = None,
    enrichment_timestamp: str | None = None,
    company_name: str | None = None,
    booking_id: str | None = None,
    booking_url: str | None = None,
    booking_status: str | None = None,
) -> str:
    """Update an existing HubSpot contact with the same enrichment payload."""
    properties = build_contact_properties(
        email,
        icp_segment=icp_segment,
        signal_enrichment=signal_enrichment,
        enrichment_timestamp=enrichment_timestamp,
        company_name=company_name,
        booking_id=booking_id,
        booking_url=booking_url,
        booking_status=booking_status,
        extra=props,
    )

    def _update_once() -> str:
        if _use_mcp():
            logger.info("hubspot_update_attempt mode=mcp contact_id=%s", contact_id)
            return _get_mcp_client().update_contact(contact_id, email=email, properties=properties)

        from hubspot.crm.contacts import SimplePublicObjectInput
        from hubspot.crm.contacts.exceptions import ApiException

        logger.info("hubspot_update_attempt mode=sdk contact_id=%s", contact_id)
        client = _get_client()
        return _run_with_missing_property_fallback(
            lambda update_properties: (
                client.crm.contacts.basic_api.update(
                    contact_id,
                    SimplePublicObjectInput(properties=update_properties),
                ),
                contact_id,
            )[1],
            properties,
            api_exception_type=ApiException,
            operation_name="update_contact",
        )

    updated_contact_id = retry_call(
        _update_once,
        attempts=3,
        base_delay_seconds=0.3,
        operation_name="HubSpot update",
    )
    logger.info("hubspot_update_success contact_id=%s email=%s", contact_id, email)
    return updated_contact_id


def record_booking(
    contact_id: str,
    *,
    email: str,
    booking_id: str,
    booking_url: str,
    booking_status: str = "booked",
    icp_segment: str | None = None,
    signal_enrichment: dict[str, Any] | None = None,
    enrichment_timestamp: str | None = None,
    company_name: str | None = None,
    props: dict[str, Any] | None = None,
) -> str:
    """Write booking state back to the same HubSpot prospect record."""
    return update_contact(
        contact_id,
        email=email,
        props=props,
        icp_segment=icp_segment,
        signal_enrichment=signal_enrichment,
        enrichment_timestamp=enrichment_timestamp,
        company_name=company_name,
        booking_id=booking_id,
        booking_url=booking_url,
        booking_status=booking_status,
    )
