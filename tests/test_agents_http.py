"""Actual gateway HTTP/SQLite enforcement, with a deterministic model-provider fixture."""

import asyncio
import json
import socket
from threading import Event, Thread

import pytest
import uvicorn
from test_gateway import harness as harness
from test_models import ObservedProvider
from test_scoped_tools import decide, rows
from test_scoped_tools import tools as tools

from agentgate.agents.client import ClientFailure, GatewayClient
from agentgate.agents.direct import DirectAgent
from agentgate.app import create_app
from agentgate.model_config import ModelPolicy, ResourceLimits
from agentgate.models import ModelService


@pytest.fixture
def live_agent_gateway(tools):
    tools.identity = tools.identity.model_copy(
        update={"operations": ("chat.completions", "documents.read", "memory.query", "mail.send")}
    )
    tools.token = tools.store.issue(tools.identity, 2000.0)
    tools.service.policy = tools.service.policy.model_copy(update={"models": ModelPolicy()})

    class ScriptedProvider(ObservedProvider):
        def __init__(self, store):
            super().__init__(store)
            self.operation = "documents_read"
            self.arguments = {"document_id": "tenant-a-notes"}

        def complete(self, payload):
            self.tool_calls = None
            if not any(m["role"] == "tool" for m in payload["messages"]):
                self.tool_calls = [
                    {
                        "id": "provider-call-7",
                        "type": "function",
                        "function": {
                            "name": self.operation,
                            "arguments": json.dumps(self.arguments),
                        },
                    }
                ]
                self.content = None
            else:
                self.content = "Summary of inspected tool result"
            return super().complete(payload)

    provider = ScriptedProvider(tools.store)
    model = ModelService(tools.service, provider)
    started = Event()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets)
            started.set()

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = Server(
            uvicorn.Config(
                create_app(tools.service, model, enable_mcp=True),
                log_level="critical",
                access_log=False,
            )
        )
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            assert started.wait(5)
            yield tools, provider, model, origin
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()


def run_agent(fixture, transport="rest", prompt="Read the notes", state=None):
    tools, _, _, origin = fixture

    async def run():
        client = GatewayClient(origin, tools.token)
        try:
            return await DirectAgent(client, transport=transport).run(
                prompt, state=state
            ), client.traces
        finally:
            await client.close()

    return asyncio.run(run())


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_real_http_model_tool_model_preserves_correlation_and_root(live_agent_gateway, transport):
    tools, provider, model, _ = live_agent_gateway
    result, traces = run_agent(live_agent_gateway, transport)
    assert result["status"] == "completed"
    assert len(provider.calls) == 2 and len(tools.executor.calls) == 1
    returned = provider.calls[1]["messages"][-1]
    assert returned["role"] == "tool" and returned["tool_call_id"] == "provider-call-7"
    assert json.loads(returned["content"])["executed"] is True
    assert [t["operation"] for t in traces] == [
        "chat.completions",
        "documents.read",
        "chat.completions",
    ]
    assert all(e.root_run_id == tools.identity.root_run_id for e in tools.store.events())
    assert any(c["scope"] == "root_run" and c["spent"] > 0 for c in model.ledger.counters())


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_real_http_pending_then_explicit_resume_one_outbox_effect(live_agent_gateway, transport):
    tools, provider, _, _ = live_agent_gateway
    tools.service.policy = tools.service.policy.model_copy(
        update={"output": tools.service.policy.output.model_copy(update={"redact_emails": False})}
    )
    provider.operation = "mail_send"
    provider.arguments = {
        "recipient": "a@demo.internal",
        "subject": "Review",
        "body": "Exact content",
        "idempotency_key": "agent-mail",
    }
    first, _ = run_agent(live_agent_gateway, transport)
    assert first["status"] == "pending_approval" and len(provider.calls) == 1
    assert rows(tools, "tool_outbox") == []
    decide(tools)
    completed, _ = run_agent(live_agent_gateway, transport, state=first["state"])
    assert completed["status"] == "completed"
    assert len(rows(tools, "tool_outbox")) == 1
    assert provider.calls[-1]["messages"][-1]["tool_call_id"] == "provider-call-7"


@pytest.mark.parametrize(
    "scenario",
    [
        "invalid_operation",
        "cross_tenant",
        "budget",
        "secret",
        "output_blocked",
        "forbidden_destination",
    ],
)
@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_real_http_denials_have_no_effect_or_retry(live_agent_gateway, scenario, transport):
    tools, provider, _, _ = live_agent_gateway
    prompt = "Read notes"
    expected_dispatches = 1
    if scenario == "invalid_operation":
        provider.operation = "terminal"
    elif scenario == "cross_tenant":
        provider.arguments = {"document_id": "tenant-b-notes"}
    elif scenario == "budget":
        tools.service.policy = tools.service.policy.model_copy(
            update={
                "models": ModelPolicy(root_run=ResourceLimits(calls=1, tokens=100000, micro_usd=0))
            }
        )
    elif scenario == "secret":
        prompt = "AGENTGATE_SECRET[synthetic]"
        expected_dispatches = 0
    elif scenario == "output_blocked":
        provider.arguments = {"document_id": "AGENTGATE_SECRET[synthetic]"}
    else:
        provider.operation = "mail_send"
        provider.arguments = {
            "recipient": "a@evil.example",
            "subject": "No",
            "body": "No",
            "idempotency_key": "denied",
        }
    with pytest.raises(ClientFailure):
        run_agent(live_agent_gateway, transport, prompt)
    assert len(provider.calls) == expected_dispatches
    assert rows(tools, "tool_outbox") == []
    assert len(tools.executor.calls) == (1 if scenario == "budget" else 0)
    assert any(
        e.event_type in ("action_denied", "output_blocked") or e.reason_codes
        for e in tools.store.events()
    )


def test_real_http_revocation_does_not_renew_or_reset_authority(live_agent_gateway):
    tools, provider, _, _ = live_agent_gateway
    run_agent(live_agent_gateway)
    counters = tools.store.budget_counters()
    tools.store.revoke(tools.token)
    with pytest.raises(ClientFailure):
        run_agent(live_agent_gateway)
    assert len(provider.calls) == 2
    assert tools.store.budget_counters() == counters
