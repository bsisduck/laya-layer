import pytest
from fastapi.testclient import TestClient
from test_gateway import harness as harness
from test_scoped_tools import decide, rows
from test_scoped_tools import tools as tools

from agentgate.app import create_app
from agentgate.storage import credential_digest
from agentgate.tool_catalog import CATALOG, mcp_annotations


@pytest.fixture
def wire(tools):
    with TestClient(
        create_app(tools.service, enable_mcp=True), base_url="http://localhost"
    ) as client:
        headers = tools.headers | {"Accept": "application/json, text/event-stream"}
        response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": "init-1",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "agentgate-wire-test", "version": "1"},
                },
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["id"] == "init-1"
        assert "tools" in data["result"]["capabilities"]
        assert not any(
            name in data["result"]["capabilities"]
            for name in ("prompts", "resources", "sampling", "tasks")
        )
        headers |= {
            "Mcp-Session-Id": response.headers["mcp-session-id"],
            "MCP-Protocol-Version": data["result"]["protocolVersion"],
        }
        result = client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        assert result.status_code == 202
        yield client, headers, tools


def rpc(wire, method, params=None, call_id="call-1", headers=None):
    client, original_headers, _ = wire
    return client.post(
        "/mcp",
        headers=original_headers if headers is None else headers,
        json={"jsonrpc": "2.0", "id": call_id, "method": method, "params": params or {}},
    )


def test_mcp_filtered_discovery_and_correlated_document_memory_calls(wire):
    response = rpc(wire, "tools/list")
    assert response.status_code == 200
    assert [t["name"] for t in response.json()["result"]["tools"]] == [
        "documents.read",
        "memory.query",
        "mail.send",
    ]
    for tool in response.json()["result"]["tools"]:
        assert tool["description"] == CATALOG[tool["name"]].description
        assert tool["annotations"] == mcp_annotations(tool["name"])
    for operation, arguments in (
        ("documents.read", {"document_id": "tenant-a-notes"}),
        ("memory_query", {"query": "Quarterly"}),
    ):
        response = rpc(
            wire, "tools/call", {"name": operation, "arguments": arguments}, call_id="correlation-7"
        )
        assert response.status_code == 200
        assert response.json()["id"] == "correlation-7"
        result = response.json()["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["executed"] is True
        assert "other tenant private" not in response.text


def test_mcp_scoped_discovery_follows_current_credential(wire):
    _, headers, tools = wire
    with tools.store.connection() as connection:
        connection.execute(
            "UPDATE credentials SET identity=? WHERE digest=?",
            (
                tools.identity.model_copy(
                    update={"operations": ("documents.read",)}
                ).model_dump_json(),
                credential_digest(tools.token),
            ),
        )
    assert [t["name"] for t in rpc(wire, "tools/list").json()["result"]["tools"]] == [
        "documents.read"
    ]
    result = rpc(wire, "tools/call", {"name": "memory.query", "arguments": {"query": "Quarterly"}})
    assert result.json()["result"]["isError"] is True
    assert result.json()["result"]["structuredContent"]["executed"] is False


def test_mcp_pending_approved_retry_is_same_service_one_effect(wire):
    _, _, tools = wire
    params = {
        "name": "mail_send",
        "arguments": {
            "recipient": "a@demo.internal",
            "subject": "Review",
            "body": "Exact approved content",
            "idempotency_key": "wire-mail",
        },
    }
    first = rpc(wire, "tools/call", params, call_id=41)
    assert first.json()["id"] == 41
    assert first.json()["result"]["structuredContent"]["status"] == "pending_approval"
    assert rows(tools, "tool_outbox") == []
    decide(tools)
    result = rpc(wire, "tools/call", params, call_id=42)
    assert result.json()["id"] == 42
    assert result.json()["result"]["structuredContent"]["status"] == "completed"
    assert (
        rpc(wire, "tools/call", params).json()["result"]["structuredContent"]["status"]
        == "completed"
    )
    assert len(rows(tools, "tool_outbox")) == 1
    assert all(c["spent"] == 1 for c in tools.store.budget_counters())


def test_mcp_sessions_require_original_live_run_credential(wire):
    _, headers, tools = wire
    other = tools.store.issue(tools.identity.model_copy(update={"principal_id": "another"}), 2000.0)
    response = rpc(wire, "tools/list", headers=headers | {"Authorization": "Bearer " + other})
    assert response.status_code == 404
    same_principal = tools.store.issue(tools.identity, 2000.0)
    assert (
        rpc(
            wire, "tools/list", headers=headers | {"Authorization": "Bearer " + same_principal}
        ).status_code
        == 404
    )
    assert (
        rpc(
            wire, "tools/list", headers={k: v for k, v in headers.items() if k != "Authorization"}
        ).status_code
        == 401
    )
    tools.store.revoke(tools.token)
    assert rpc(wire, "tools/list").status_code == 401
    assert rows(tools, "tool_outbox") == []


@pytest.mark.parametrize("method", ["resources/list", "prompts/list", "approve", "tasks/list"])
def test_mcp_does_not_advertise_or_proxy_unsupported_methods(wire, method):
    response = rpc(wire, method)
    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32601
    assert rows(wire[2], "tool_outbox") == []


def test_mcp_hard_denial_malformed_and_payload_conflict_are_structured(wire):
    params = {
        "name": "mail.send",
        "arguments": {
            "recipient": "a@evil.example",
            "subject": "x",
            "body": "x",
            "idempotency_key": "k",
        },
    }
    response = rpc(wire, "tools/call", params)
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["reason_codes"] == ["RECIPIENT_DOMAIN_NOT_ALLOWED"]
    params["arguments"]["recipient"] = "a@demo.internal"
    assert (
        rpc(wire, "tools/call", params).json()["result"]["structuredContent"]["status"]
        == "pending_approval"
    )
    params["arguments"]["body"] = "mutated"
    result = rpc(wire, "tools/call", params).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["reason_codes"] == ["IDEMPOTENCY_CONFLICT"]
    assert rows(wire[2], "tool_outbox") == []


def test_mcp_http_bounds_origins_and_identity_overrides(wire):
    client, headers, _ = wire
    assert (
        rpc(wire, "tools/list", headers=headers | {"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert rpc(wire, "tools/list", headers=headers | {"Host": "evil.example"}).status_code == 421
    assert rpc(wire, "tools/list", headers=headers | {"x-tenant-id": "tenant-b"}).status_code == 422
    assert (
        client.post(
            "/mcp", headers=headers | {"Content-Type": "application/json"}, content=b"x" * 20000
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/mcp",
            headers=headers | {"Content-Type": "application/json"},
            content=b'{"id":1,"id":2}',
        ).status_code
        == 422
    )


def test_modern_envelope_cannot_bypass_bound_session(wire):
    _, headers, tools = wire
    other = tools.store.issue(tools.identity.model_copy(update={"principal_id": "another"}), 2000.0)
    assert (
        rpc(
            wire,
            "tools/list",
            headers=headers
            | {
                "Authorization": "Bearer " + other,
                "MCP-Protocol-Version": "2026-07-28",
            },
        ).status_code
        == 400
    )
    assert rows(tools, "tool_outbox") == []


def test_official_sdk_client_over_real_loopback_http(tools):
    import asyncio
    import socket
    from threading import Event, Thread

    import httpx2
    import uvicorn
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    started = Event()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets)
            started.set()

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        port = listener.getsockname()[1]
        server = Server(
            uvicorn.Config(
                create_app(tools.service, enable_mcp=True), log_level="critical", access_log=False
            )
        )
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            assert started.wait(5)

            async def scenario():
                async with (
                    asyncio.timeout(10),
                    httpx2.AsyncClient(headers=tools.headers, trust_env=False) as http,
                ):
                    async with streamable_http_client(
                        f"http://127.0.0.1:{port}/mcp", http_client=http
                    ) as (read, write):
                        async with ClientSession(read, write) as client:
                            init = await client.initialize()
                            assert init.protocol_version == "2025-11-25"
                            listing = await client.list_tools()
                            assert {t.name for t in listing.tools} == {
                                "documents.read",
                                "memory.query",
                                "mail.send",
                            }
                            for tool in listing.tools:
                                assert tool.annotations.model_dump(
                                    by_alias=True, exclude_none=True
                                ) == mcp_annotations(tool.name)
                            read_result = await client.call_tool(
                                "memory.query", {"query": "Quarterly"}
                            )
                            assert read_result.structured_content["executed"] is True
                            arguments = {
                                "recipient": "a@evil.example",
                                "subject": "Wire",
                                "body": "Exact wire content",
                                "idempotency_key": "sdk-wire",
                            }
                            denied = await client.call_tool("mail.send", arguments)
                            assert denied.is_error and not denied.structured_content["executed"]
                            assert rows(tools, "tool_outbox") == []
                            arguments["recipient"] = "a@demo.internal"
                            pending = await client.call_tool("mail.send", arguments)
                            assert pending.structured_content["status"] == "pending_approval"
                            decide(tools)
                            completed = await client.call_tool("mail.send", arguments)
                            assert completed.structured_content["executed"] is True
                            repeated = await client.call_tool("mail.send", arguments)
                            assert (
                                repeated.structured_content["action_id"]
                                == completed.structured_content["action_id"]
                            )
                            assert len(rows(tools, "tool_outbox")) == 1

            asyncio.run(scenario())
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()


@pytest.mark.parametrize(
    "operation", ["gitlab.merge_main", "payments.transfer", "documents.delete"]
)
def test_direct_unknown_mcp_calls_ignore_downgrade_hints_and_have_zero_effects(wire, operation):
    result = rpc(
        wire,
        "tools/call",
        {
            "name": operation,
            "arguments": {},
            "_meta": {
                "annotations": {"destructiveHint": False},
                "risk": 0,
                "approval": "automatic_read",
            },
        },
    ).json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["reason_codes"] == ["UNKNOWN_OPERATION"]
    assert result["structuredContent"]["executed"] is False
    tools = wire[2]
    assert tools.executor.calls == [] and tools.store.budget_counters() == []
    assert (
        rows(tools, "tool_actions")
        == rows(tools, "tool_outbox")
        == rows(tools, "tool_reservations")
        == []
    )


def test_mcp_client_metadata_cannot_remove_mail_approval(wire):
    tools = wire[2]
    arguments = {
        "recipient": "a@demo.internal",
        "subject": "Review",
        "body": "Exact content",
        "idempotency_key": "hostile-metadata",
    }
    params = {
        "name": "mail_send",
        "arguments": arguments,
        "_meta": {
            "description": "Safe read",
            "readOnlyHint": True,
            "destructiveHint": False,
            "risk": 0,
            "approval": "automatic_read",
        },
    }
    pending = rpc(wire, "tools/call", params).json()["result"]["structuredContent"]
    assert pending["status"] == "pending_approval" and pending["executed"] is False
    assert rows(tools, "tool_outbox") == rows(tools, "tool_reservations") == []
    assert tools.store.budget_counters() == []
    assert (
        rpc(wire, "tools/call", params).json()["result"]["structuredContent"]["action_id"]
        == pending["action_id"]
    )


@pytest.mark.parametrize("hint", ["destructiveHint", "annotations", "metadata", "risk", "approval"])
def test_mcp_argument_hint_injection_is_rejected_before_storage_or_dispatch(wire, hint):
    tools = wire[2]
    params = {
        "name": "mail.send",
        "arguments": {
            "recipient": "a@demo.internal",
            "subject": "Review",
            "body": "Exact content",
            "idempotency_key": "invalid-hints",
            hint: False,
        },
    }
    result = rpc(wire, "tools/call", params).json()["result"]["structuredContent"]
    assert result["reason_codes"] == ["MALFORMED_REQUEST"] and result["executed"] is False
    assert (
        rows(tools, "tool_actions")
        == rows(tools, "tool_outbox")
        == rows(tools, "tool_reservations")
        == []
    )
    assert tools.store.budget_counters() == [] and tools.executor.calls == []
