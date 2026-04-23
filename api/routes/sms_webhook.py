"""Inbound SMS webhook route."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from agent.handlers.sms import (
    SmsHandlerError,
    SmsWebhookError,
    handle_webhook_payload,
)

router = APIRouter(prefix="/webhooks/sms", tags=["webhooks"])


@router.post("")
def receive_sms_webhook(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Receive an inbound SMS event and dispatch it downstream."""
    try:
        return handle_webhook_payload(payload)
    except SmsWebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SmsHandlerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
