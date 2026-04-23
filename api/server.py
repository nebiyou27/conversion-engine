"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI

from agent.runtime import configure_logging
from api.routes.email_webhook import router as email_webhook_router
from api.routes.sms_webhook import router as sms_webhook_router

configure_logging()

app = FastAPI(title="Conversion Engine")
app.include_router(email_webhook_router)
app.include_router(sms_webhook_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
