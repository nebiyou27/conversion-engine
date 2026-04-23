"""HubSpot MCP client wrapper for CRM writes."""
from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
from dotenv import load_dotenv

load_dotenv()

try:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client
except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
    ClientSession = None  # type: ignore[assignment]
    streamable_http_client = None  # type: ignore[assignment]
    _MCP_IMPORT_ERROR = exc
else:
    _MCP_IMPORT_ERROR = None


class HubSpotMCPError(RuntimeError):
    """Raised when the HubSpot MCP transport or tool call fails."""


@dataclass(frozen=True)
class _ToolRef:
    name: str
    description: str
    schema: dict[str, Any]


class HubSpotMCPClient:
    """Minimal remote HubSpot MCP client."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        access_token: str | None = None,
        timeout_seconds: float = 30.0,
        create_contact_tool: str | None = None,
        update_contact_tool: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("HUBSPOT_MCP_URL") or "https://mcp.hubspot.com/").rstrip("/") + "/"
        self.access_token = access_token or os.getenv("HUBSPOT_MCP_ACCESS_TOKEN")
        self.timeout_seconds = timeout_seconds
        self.create_contact_tool = create_contact_tool or os.getenv("HUBSPOT_MCP_CREATE_CONTACT_TOOL")
        self.update_contact_tool = update_contact_tool or os.getenv("HUBSPOT_MCP_UPDATE_CONTACT_TOOL")

        if not self.access_token:
            raise HubSpotMCPError("HUBSPOT_MCP_ACCESS_TOKEN is required when USE_HUBSPOT_MCP=true")
        if _MCP_IMPORT_ERROR is not None:
            raise HubSpotMCPError("mcp package is not installed") from _MCP_IMPORT_ERROR

    @classmethod
    def from_env(cls) -> "HubSpotMCPClient":
        return cls()

    @asynccontextmanager
    async def _open_session(self):
        if ClientSession is None or streamable_http_client is None:  # pragma: no cover - import guard
            raise HubSpotMCPError("mcp package is not installed")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers) as http_client:
            async with streamable_http_client(self.base_url, http_client=http_client) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    yield session

    @staticmethod
    def _tool_text(tool: Any) -> str:
        name = getattr(tool, "name", "")
        description = getattr(tool, "description", "") or ""
        return f"{name} {description}".lower()

    @staticmethod
    def _tool_schema(tool: Any) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        if schema is None:
            return {}
        if hasattr(schema, "model_dump"):
            schema = schema.model_dump()
        if isinstance(schema, dict):
            return schema
        return {}

    @staticmethod
    def _normalize_tools(result: Any) -> list[_ToolRef]:
        tools = getattr(result, "tools", result)
        normalized: list[_ToolRef] = []
        for tool in tools or []:
            normalized.append(
                _ToolRef(
                    name=getattr(tool, "name", ""),
                    description=getattr(tool, "description", "") or "",
                    schema=HubSpotMCPClient._tool_schema(tool),
                )
            )
        return normalized

    def _select_tool(self, tools: list[_ToolRef], *, action: str) -> _ToolRef:
        override = {
            "create": self.create_contact_tool,
            "update": self.update_contact_tool,
        }.get(action)
        if override:
            for tool in tools:
                if tool.name == override:
                    return tool
            raise HubSpotMCPError(f"Configured HubSpot MCP tool {override!r} was not found")

        scored: list[tuple[int, _ToolRef]] = []
        for tool in tools:
            text = self._tool_text(tool)
            score = 0
            if action == "create":
                if "create or update" in text or "upsert" in text:
                    score += 100
                if "create" in text and "contact" in text:
                    score += 60
                if "email" in text and "contact" in text:
                    score += 20
            elif action == "update":
                if "update" in text and "contact" in text:
                    score += 100
                if "edit" in text and "contact" in text:
                    score += 50
                if "properties" in text and "contact" in text:
                    score += 10
            if score:
                scored.append((score, tool))

        if scored:
            scored.sort(key=lambda item: item[0], reverse=True)
            return scored[0][1]

        available = ", ".join(tool.name for tool in tools) or "<none>"
        raise HubSpotMCPError(f"Could not find a HubSpot MCP tool for {action!r}. Available tools: {available}")

    def _build_arguments(
        self,
        tool: _ToolRef,
        *,
        email: str,
        properties: dict[str, Any],
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        schema_properties = tool.schema.get("properties", {})
        if not isinstance(schema_properties, dict):
            schema_properties = {}

        arguments: dict[str, Any] = {}
        key_map = {
            "email": ["email", "contactEmail", "contact_email"],
            "contact_id": ["contactId", "contact_id", "id", "objectId", "object_id", "recordId", "record_id", "hs_object_id"],
            "properties": ["properties", "contactProperties", "contact_properties", "propertyValues", "property_values"],
        }

        def _maybe_set(target: str, value: Any) -> None:
            for candidate in key_map[target]:
                if candidate in schema_properties or not schema_properties:
                    arguments[candidate] = value
                    return

        _maybe_set("email", email)
        _maybe_set("properties", properties)
        if contact_id is not None:
            _maybe_set("contact_id", contact_id)

        if not arguments:
            arguments = {"email": email, "properties": properties}
            if contact_id is not None:
                arguments["contact_id"] = contact_id

        return arguments

    @staticmethod
    def _extract_contact_id(result: Any) -> str:
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            for key in ("id", "contactId", "contact_id", "objectId", "recordId", "hs_object_id"):
                value = structured.get(key)
                if value not in (None, ""):
                    return str(value)
            for value in structured.values():
                if isinstance(value, dict):
                    for key in ("id", "contactId", "contact_id", "objectId", "recordId", "hs_object_id"):
                        nested = value.get(key)
                        if nested not in (None, ""):
                            return str(nested)

        content = getattr(result, "content", []) or []
        for block in content:
            text = getattr(block, "text", None)
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                for key in ("id", "contactId", "contact_id", "objectId", "recordId", "hs_object_id"):
                    value = parsed.get(key)
                    if value not in (None, ""):
                        return str(value)
            match = re.search(r"(?i)(?:contact|object|record)?[_-]?id[\"'=: ]+([A-Za-z0-9_-]+)", text)
            if match:
                return match.group(1)

        raise HubSpotMCPError("HubSpot MCP tool call returned no contact id")

    async def _call_tool(
        self,
        *,
        action: str,
        email: str,
        properties: dict[str, Any],
        contact_id: str | None = None,
    ) -> str:
        async with self._open_session() as session:
            tools_result = await session.list_tools()
            tools = self._normalize_tools(tools_result)
            tool = self._select_tool(tools, action=action)
            arguments = self._build_arguments(tool, email=email, properties=properties, contact_id=contact_id)
            result = await session.call_tool(tool.name, arguments=arguments)
            if getattr(result, "isError", False):
                raise HubSpotMCPError(f"HubSpot MCP tool {tool.name!r} returned an error")
            return self._extract_contact_id(result)

    async def _upsert_contact_async(self, email: str, properties: dict[str, Any]) -> str:
        return await self._call_tool(action="create", email=email, properties=properties)

    async def _update_contact_async(
        self,
        contact_id: str,
        email: str,
        properties: dict[str, Any],
    ) -> str:
        return await self._call_tool(action="update", email=email, properties=properties, contact_id=contact_id)

    def upsert_contact(self, *, email: str, properties: dict[str, Any]) -> str:
        return anyio.run(self._upsert_contact_async, email, properties)

    def update_contact(self, contact_id: str, *, email: str, properties: dict[str, Any]) -> str:
        return anyio.run(self._update_contact_async, contact_id, email, properties)
