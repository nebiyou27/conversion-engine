"""Contract tests for the HubSpot MCP client adapter."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from integrations.hubspot_mcp_client import HubSpotMCPClient


@dataclass
class FakeTool:
    name: str
    description: str
    inputSchema: dict


@dataclass
class FakeResult:
    structuredContent: dict | None = None
    content: list | None = None
    isError: bool = False


class FakeSession:
    def __init__(self, tools: list[FakeTool], result: FakeResult):
        self._tools = tools
        self._result = result
        self.calls: list[tuple[str, dict]] = []

    async def initialize(self) -> None:
        return None

    async def list_tools(self):
        return type("ToolsResult", (), {"tools": self._tools})()

    async def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        return self._result


def test_mcp_client_upsert_contact_uses_matching_tool(monkeypatch):
    session = FakeSession(
        [
            FakeTool(
                name="create_or_update_contact",
                description="Create or update a contact record",
                inputSchema={
                    "properties": {
                        "email": {"type": "string"},
                        "properties": {"type": "object"},
                    }
                },
            )
        ],
        FakeResult(structuredContent={"id": "contact_123"}),
    )

    @asynccontextmanager
    async def fake_open_session(self):
        yield session

    monkeypatch.setattr(HubSpotMCPClient, "_open_session", fake_open_session)

    client = HubSpotMCPClient(base_url="https://mcp.example.test", access_token="token")
    contact_id = client.upsert_contact(
        email="prospect@example.com",
        properties={"email": "prospect@example.com", "company": "Acme"},
    )

    assert contact_id == "contact_123"
    assert session.calls == [
        (
            "create_or_update_contact",
            {
                "email": "prospect@example.com",
                "properties": {"email": "prospect@example.com", "company": "Acme"},
            },
        )
    ]


def test_mcp_client_update_contact_includes_contact_id(monkeypatch):
    session = FakeSession(
        [
            FakeTool(
                name="update_contact",
                description="Update a contact record",
                inputSchema={
                    "properties": {
                        "contactId": {"type": "string"},
                        "email": {"type": "string"},
                        "properties": {"type": "object"},
                    }
                },
            )
        ],
        FakeResult(structuredContent={"contactId": "contact_456"}),
    )

    @asynccontextmanager
    async def fake_open_session(self):
        yield session

    monkeypatch.setattr(HubSpotMCPClient, "_open_session", fake_open_session)

    client = HubSpotMCPClient(base_url="https://mcp.example.test", access_token="token")
    contact_id = client.update_contact(
        "contact_456",
        email="prospect@example.com",
        properties={"calcom_booking_status": "booked"},
    )

    assert contact_id == "contact_456"
    assert session.calls == [
        (
            "update_contact",
            {
                "contactId": "contact_456",
                "email": "prospect@example.com",
                "properties": {"calcom_booking_status": "booked"},
            },
        )
    ]
