"""Client protocol fixtures, separate from gateway HTTP enforcement and real inference."""

import asyncio
import json

import httpx
import pytest

from agentgate.agents.client import ClientFailure, GatewayClient, decode, gateway_origin
from agentgate.agents.direct import DirectAgent, private_read, save_state


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com",
        "http://localhost:8080",
        "http://127.0.0.1:2/v1",
        "http://u:p@127.0.0.1:2",
        "http://127.0.0.1:2/?url=x",
    ],
)
def test_only_explicit_gateway_origin(value):
    with pytest.raises(ClientFailure):
        gateway_origin(value)


@pytest.mark.parametrize(
    "raw", ['{"x":1,"x":2}', '{"x":NaN}', "[]", '{"x":"' + "a" * 262144 + '"}']
)
def test_bounded_strict_json(raw):
    with pytest.raises(ClientFailure):
        decode(raw)


def test_private_state_refuses_overwrite_symlink_and_public_files(tmp_path):
    path = tmp_path / "state"
    save_state(path, {"state": "pending"})
    assert json.loads(private_read(path)) == {"state": "pending"}
    with pytest.raises(ClientFailure):
        save_state(path, {})
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ClientFailure):
        private_read(link)
    path.chmod(0o644)
    with pytest.raises(ClientFailure):
        private_read(path)


def test_transport_does_not_retry_or_follow_redirect():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "http://127.0.0.1:9999"})

    async def run():
        client = GatewayClient("http://127.0.0.1:8080", "scoped-token")
        await client.http.aclose()
        client.http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=client.origin
        )
        try:
            with pytest.raises(ClientFailure, match="model_rejected_307"):
                await client.complete({})
        finally:
            await client.close()

    asyncio.run(run())
    assert len(calls) == 1


class ProtocolFixture:
    def __init__(self, *, pending=False, repeated=False):
        self.traces = []
        self.calls = []
        self.pending = pending
        self.repeated = repeated

    async def discover(self):
        return [{"type": "function", "function": {"name": "documents_read"}}]

    async def request(self, *args):
        return 200, {"data": [{"id": "local-demo"}]}, {}

    async def complete(self, payload):
        self.calls.append(json.loads(json.dumps(payload)))
        if len(self.calls) == 1 or self.repeated:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "exact-call-7",
                                    "type": "function",
                                    "function": {
                                        "name": "documents_read",
                                        "arguments": '{"document_id":"notes"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "Summary"}, "finish_reason": "stop"}
            ]
        }

    async def execute(self, *args, **kwargs):
        if self.pending:
            return {"status": "pending_approval", "executed": False, "action_id": "a1"}
        return {
            "status": "completed",
            "executed": True,
            "result": {"content": "Inspected"},
            "trace_id": "t1",
        }

    async def resume(self, action_id):
        assert action_id == "a1"
        return {"status": "completed", "executed": True, "result": {"outbox_id": "o1"}}


def test_cycle_preserves_exact_call_and_complete_tool_response():
    fixture = ProtocolFixture()
    assert asyncio.run(DirectAgent(fixture).run("read"))["text"] == "Summary"
    returned = fixture.calls[1]["messages"][-1]
    assert returned["tool_call_id"] == "exact-call-7"
    assert json.loads(returned["content"]) == {
        "status": "completed",
        "executed": True,
        "result": {"content": "Inspected"},
        "trace_id": "t1",
    }


def test_pending_stops_before_model_and_explicit_resume_uses_same_call_id():
    fixture = ProtocolFixture(pending=True)
    first = asyncio.run(DirectAgent(fixture).run("mail"))
    assert first["status"] == "pending_approval" and len(fixture.calls) == 1
    result = asyncio.run(DirectAgent(fixture).run("", state=first["state"]))
    assert result["status"] == "completed"
    assert fixture.calls[1]["messages"][-1]["tool_call_id"] == "exact-call-7"


def test_repeated_call_ids_stop_without_another_execution():
    fixture = ProtocolFixture(repeated=True)
    with pytest.raises(ClientFailure, match="repeated_call_id"):
        asyncio.run(DirectAgent(fixture).run("read"))
    assert len(fixture.calls) == 2


def test_direct_cli_removes_inherited_vendor_operator_and_proxy_credentials(monkeypatch):
    import os

    from agentgate.agents.direct import scrub_process_environment

    with monkeypatch.context() as context:
        for key in (
            "OPENAI_API_KEY",
            "AGENTGATE_OPERATOR_TOKEN",
            "HTTP_PROXY",
            "LITELLM_MASTER_KEY",
            "AWS_SECRET_ACCESS_KEY",
        ):
            context.setenv(key, "synthetic-only")
        previous = dict(os.environ)
        try:
            scrub_process_environment()
            assert not any(
                key in os.environ
                for key in (
                    "OPENAI_API_KEY",
                    "AGENTGATE_OPERATOR_TOKEN",
                    "HTTP_PROXY",
                    "LITELLM_MASTER_KEY",
                    "AWS_SECRET_ACCESS_KEY",
                )
            )
        finally:
            os.environ.clear()
            os.environ.update(previous)


@pytest.mark.parametrize("state", [{}, {"turns": -1}, {"turns": True}, {"turns": 1000}])
def test_malformed_resume_rejected_before_network(state):
    fixture = ProtocolFixture()
    with pytest.raises(ClientFailure, match="invalid_pending_state"):
        asyncio.run(DirectAgent(fixture).run("", state=state))
    assert fixture.calls == []
