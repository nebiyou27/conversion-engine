"""Contract tests for the outbound email handler."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from agent.handlers import email as email_handler
from api.server import app


def teardown_module() -> None:
    email_handler.clear_event_handler()


def test_send_outbound_email_raises_when_message_id_missing(monkeypatch):
    monkeypatch.setattr(email_handler.email_client, "send", lambda **_: "")

    with pytest.raises(email_handler.EmailDeliveryError, match="missing message id"):
        email_handler.send_outbound_email("prospect@example.com", "Hello", "<p>Hi</p>")


def test_handle_webhook_payload_dispatches_reply_event():
    seen: list[email_handler.NormalizedEmailEvent] = []
    previous = email_handler.register_event_handler(seen.append)
    try:
        result = email_handler.handle_webhook_payload({
            "event": "inbound.reply",
            "message_id": "msg_123",
            "from": "prospect@example.com",
            "to": "sales@tenacious.co",
            "subject": "Re: Intro",
            "text": "Let's talk next week.",
        })
    finally:
        email_handler.register_event_handler(previous)

    assert result["ok"] is True
    assert result["event_type"] == "reply"
    assert result["handled"] is True
    assert len(seen) == 1
    assert seen[0].event_type == "reply"
    assert seen[0].message_id == "msg_123"


def test_handle_webhook_payload_is_idempotent():
    seen: list[email_handler.NormalizedEmailEvent] = []
    previous = email_handler.register_event_handler(seen.append)
    try:
        first = email_handler.handle_webhook_payload({
            "event": "inbound.reply",
            "message_id": "msg_idempotent",
            "from": "prospect@example.com",
            "to": "sales@tenacious.co",
            "subject": "Re: Intro",
            "text": "Let's talk next week.",
        })
        second = email_handler.handle_webhook_payload({
            "event": "inbound.reply",
            "message_id": "msg_idempotent",
            "from": "prospect@example.com",
            "to": "sales@tenacious.co",
            "subject": "Re: Intro",
            "text": "Let's talk next week.",
        })
    finally:
        email_handler.register_event_handler(previous)

    assert first["replayed"] is False
    assert second["replayed"] is True
    assert len(seen) == 1


def test_handle_webhook_payload_rejects_malformed_payload():
    with pytest.raises(email_handler.EmailWebhookError, match="missing event type"):
        email_handler.handle_webhook_payload({"message_id": "msg_123"})


def test_email_webhook_route_returns_400_on_malformed_payload():
    client = TestClient(app)
    response = client.post("/webhooks/email", json={"message_id": "msg_123"})
    assert response.status_code == 400
    assert "missing event type" in response.json()["detail"]
