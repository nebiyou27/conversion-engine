"""Inbound email webhook route."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from agent.handlers.email import (
    EmailHandlerError,
    EmailWebhookError,
    handle_webhook_payload,
)

router = APIRouter(prefix="/webhooks/email", tags=["webhooks"])


@router.post("")
def receive_email_webhook(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Receive an inbound email event and dispatch it downstream."""
    try:
        return handle_webhook_payload(payload)
    except EmailWebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmailHandlerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
