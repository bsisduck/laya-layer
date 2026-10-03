import pytest
from fastapi.testclient import TestClient
from test_gateway import harness as harness
from test_scoped_tools import decide, rows
from test_scoped_tools import tools as tools

from agentgate.app import create_app


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
                __import__("agentgate.storage", fromlist=["credential_digest"]).credential_digest(
                    tools.token
                ),
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
