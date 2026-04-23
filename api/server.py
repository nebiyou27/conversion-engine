"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI

from api.routes.email_webhook import router as email_webhook_router

app = FastAPI(title="Conversion Engine")
app.include_router(email_webhook_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
