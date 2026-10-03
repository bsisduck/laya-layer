"""Bounded loopback gateway transport and tools-only MCP discovery.

The MCP wire subset is deliberately small: initialize, initialized, tools/list,
tools/call. JSON responses are required (the gateway's pinned
transport); no server-initiated sampling, prompts, resources or arbitrary URLs.
"""

import asyncio
import json
import re
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx

ALIASES = {
    "documents.read": "documents_read",
    "memory.query": "memory_query",
    "mail.send": "mail_send",
}
MAX_BYTES = 262144


class ClientFailure(Exception):
    """Safe, content-free failure; never render server exception bodies."""

    def __init__(self, reason: str, *, trace: list[dict[str, Any]] | None = None) -> None:
        super().__init__(reason)
        self.trace = trace or []


def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def reject_constant(value: str) -> Any:
    raise ValueError("nonfinite JSON")


def decode(raw: str | bytes) -> dict[str, Any]:
    if len(raw) > MAX_BYTES:
        raise ClientFailure("response_too_large")
    try:
        value = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=reject_constant)
    except (ValueError, RecursionError) as error:
        raise ClientFailure("invalid_json") from error
    if not isinstance(value, dict):
        raise ClientFailure("invalid_object")
    return value


def gateway_origin(value: str) -> str:
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError as error:
        raise ClientFailure("gateway_requires_explicit_loopback_origin") from error
    if (
        url.scheme != "http"
        or url.hostname not in ("127.0.0.1", "::1")
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ("", "/")
        or not port
    ):
        raise ClientFailure("gateway_requires_explicit_loopback_origin")
    return value.rstrip("/")


class GatewayClient:
    def __init__(self, origin: str, token: str, *, timeout: float = 60) -> None:
        self.origin = gateway_origin(origin)
        if not token or len(token) > 512 or any(c.isspace() for c in token):
            raise ClientFailure("invalid_credential")
        if not 0 < timeout <= 120:
            raise ClientFailure("invalid_deadline")
        self.timeout = timeout
        self.http = httpx.AsyncClient(
            base_url=self.origin,
            headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"},
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        )
        self.session: str | None = None
        self.tools: dict[str, dict[str, Any]] = {}
        self.traces: list[dict[str, Any]] = []

    async def close(self) -> None:
        # Closing local sockets is sufficient; no implicit tool retry or model call.
        await self.http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any], httpx.Headers]:
        try:
            async with asyncio.timeout(self.timeout):
                async with self.http.stream(method, path, json=body, headers=headers) as response:
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise ClientFailure("compressed_response_unsupported")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BYTES:
                            raise ClientFailure("response_too_large")
                    data = decode(bytes(raw)) if raw else {}
                    return response.status_code, data, response.headers
        except (httpx.HTTPError, TimeoutError) as error:
            raise ClientFailure("transport_failed_no_retry") from error

    async def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        rpc_id = uuid.uuid4().hex
        headers = {"Accept": "application/json, text/event-stream"}
        if self.session:
            headers |= {"Mcp-Session-Id": self.session, "MCP-Protocol-Version": "2025-11-25"}
        status, data, returned = await self.request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params},
            headers=headers,
        )
        if status != 200 or data.get("id") != rpc_id or not isinstance(data.get("result"), dict):
            raise ClientFailure("mcp_rejected_no_retry")
        if method == "initialize":
            self.session = returned.get("mcp-session-id")
            if not self.session or data["result"].get("protocolVersion") != "2025-11-25":
                raise ClientFailure("mcp_contract_mismatch")
        return dict(data["result"])

    async def discover(self) -> list[dict[str, Any]]:
        initialized = await self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "agentgate-direct", "version": "1"},
            },
        )
        if set(initialized.get("capabilities", {})) - {"tools"}:
            raise ClientFailure("unexpected_mcp_capabilities")
        status, _, _ = await self.request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={
                "Accept": "application/json, text/event-stream",
                "Mcp-Session-Id": str(self.session),
                "MCP-Protocol-Version": "2025-11-25",
            },
        )
        if status != 202:
            raise ClientFailure("mcp_initialization_failed")
        listing = await self.rpc("tools/list", {})
        if listing.get("nextCursor") or not isinstance(listing.get("tools"), list):
            raise ClientFailure("unsupported_tool_discovery")
        status, rest, _ = await self.request("GET", "/v1/tools")
        if status != 200 or not isinstance(rest.get("tools"), list):
            raise ClientFailure("discovery_denied")
        self.tools = {}
        for tool in listing["tools"]:
            canonical = tool.get("name")
            if canonical not in ALIASES or canonical not in rest["tools"]:
                raise ClientFailure("unexpected_tool")
            alias = ALIASES[canonical]
            if alias in self.tools or not isinstance(tool.get("inputSchema"), dict):
                raise ClientFailure("invalid_tool_schema")
            self.tools[alias] = {
                "type": "function",
                "function": {
                    "name": alias,
                    "description": tool.get("description", ""),
                    "parameters": tool["inputSchema"],
                },
            }
        return list(self.tools.values())

    def record(self, operation: str, data: dict[str, Any], **fields: Any) -> None:
        # Correlation/status only: never prompts, arguments, results or credentials.
        self.traces.append(
            {
                "operation": operation,
                "trace_id": data.get("trace_id"),
                "status": data.get("status"),
                **fields,
            }
        )

    async def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, data, headers = await self.request("POST", "/v1/chat/completions", payload)
        self.record(
            "chat.completions", data, http_status=status, request_id=headers.get("x-request-id")
        )
        if status != 200:
            raise ClientFailure(f"model_rejected_{status}_no_retry")
        self.traces[-1]["trace_id"] = data.get("agentgate", {}).get("trace_id")
        calls = data.get("choices", [{}])[0].get("message", {}).get("tool_calls") or []
        self.traces[-1]["tool_call_ids"] = [call.get("id") for call in calls]
        self.traces[-1]["tool_result_ids"] = [
            message["tool_call_id"]
            for message in payload.get("messages", [])
            if message.get("role") == "tool"
        ]
        return data

    async def execute(
        self, name: str, arguments: dict[str, Any], *, transport: str
    ) -> dict[str, Any]:
        if name not in self.tools:
            raise ClientFailure("undiscovered_tool")
        canonical = next(key for key, value in ALIASES.items() if value == name)
        if transport == "rest":
            status, data, _ = await self.request(
                "POST",
                "/v1/actions/execute",
                {
                    "operation": canonical,
                    "arguments": arguments,
                },
            )
        elif transport == "mcp":
            result = await self.rpc("tools/call", {"name": canonical, "arguments": arguments})
            structured = result.get("structuredContent")
            if not isinstance(structured, dict):
                raise ClientFailure("invalid_tool_result")
            data = structured
            status = 403 if result.get("isError") else 200
        else:
            raise ClientFailure("invalid_transport")
        self.record(canonical, data, http_status=status)
        if status not in (200, 202):
            raise ClientFailure(f"tool_rejected_{status}_no_retry")
        return data

    async def resume(self, action_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", action_id):
            raise ClientFailure("invalid_action_id")
        status, data, _ = await self.request("POST", f"/v1/actions/{action_id}/resume", {})
        self.record("resume", data, http_status=status)
        if status not in (200, 202):
            raise ClientFailure(f"resume_rejected_{status}_no_retry")
        return data
