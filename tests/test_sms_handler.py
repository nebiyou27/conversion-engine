"""Contract tests for the SMS handler."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from agent.actions.channel import can_use_sms, choose_channel
from agent.handlers import sms as sms_handler
from api.server import app
from integrations import sms_client


def teardown_module() -> None:
    sms_handler.clear_event_handler()


def test_send_warm_lead_sms_blocks_cold_outreach(monkeypatch):
    monkeypatch.setattr(sms_client, "send_message", lambda *args, **kwargs: {"raw": "ok"})

    with pytest.raises(sms_handler.SmsChannelError, match="warm leads"):
        sms_handler.send_warm_lead_sms(
            "+254700000000",
            "Hello",
            prior_email_reply=False,
            is_warm_lead=False,
        )


def test_send_warm_lead_sms_calls_provider(monkeypatch):
    calls: list[tuple[str, str, dict]] = []

    def fake_send_message(to: str, message: str, **kwargs):
        calls.append((to, message, kwargs))
        return {"raw": {"messages": [{"status": "Success"}]}}

    monkeypatch.setattr(sms_client, "send_message", fake_send_message)
    monkeypatch.setattr(sms_handler.sms_client, "send_message", fake_send_message)

    result = sms_handler.send_warm_lead_sms(
        "+254700000000",
        "Hi there",
        prior_email_reply=True,
        is_warm_lead=True,
    )

    assert result["ok"] is True
    assert result["channel"] == "sms"
    assert result["warm_lead"] is True
    assert calls[0][0] == "+254700000000"


def test_sms_webhook_dispatches_reply_event():
    seen: list[sms_handler.NormalizedSmsEvent] = []
    previous = sms_handler.register_event_handler(seen.append)
    try:
        result = sms_handler.handle_webhook_payload({
            "event": "inbound.reply",
            "message_id": "sms_123",
            "from": "+254700000000",
            "to": "+254711111111",
            "text": "Thanks, let's talk.",
        })
    finally:
        sms_handler.register_event_handler(previous)

    assert result["ok"] is True
    assert result["event_type"] == "reply"
    assert result["handled"] is True
    assert len(seen) == 1
    assert seen[0].body == "Thanks, let's talk."


def test_sms_webhook_route_returns_400_on_malformed_payload():
    client = TestClient(app)
    response = client.post("/webhooks/sms", json={"message_id": "sms_123"})
    assert response.status_code == 400
    assert "missing event type" in response.json()["detail"]


def test_channel_gates_sms_to_warm_leads():
    assert can_use_sms(prior_email_reply=True, is_warm_lead=True) is True
    assert can_use_sms(prior_email_reply=False, is_warm_lead=True) is False
    assert choose_channel(prefer_sms=True, prior_email_reply=True, is_warm_lead=True) == "sms"
    assert choose_channel(prefer_sms=True, prior_email_reply=False, is_warm_lead=True) == "email"
