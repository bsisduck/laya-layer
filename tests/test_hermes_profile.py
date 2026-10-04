"""Profile unit tests; optional upstream tests use actual pinned Hermes, fixture generation."""

import os
from pathlib import Path

import pytest
from test_agents_http import live_agent_gateway as live_agent_gateway
from test_gateway import harness as harness
from test_scoped_tools import tools as tools

from agentgate.agents.client import ClientFailure
from agentgate.agents.hermes import restricted_config, run_hermes, verify_source


def test_profile_disables_builtin_memory_compression_and_sampling():
    config = restricted_config("http://127.0.0.1:8080", "synthetic", "local-demo")
    assert config["agent"] == {"api_max_retries": 1, "auto_recovery_cycles": 0}
    assert config["model"]["streaming"] is False
    assert config["compression"]["enabled"] is False
    assert config["memory"]["memory_enabled"] is False
    assert list(config["mcp_servers"]) == ["agentgate"]
    assert config["mcp_servers"]["agentgate"]["sampling"]["enabled"] is False
    assert config["mcp_servers"]["agentgate"]["tools"]["resources"] is False


def test_missing_upstream_is_unavailable_not_success(tmp_path):
    with pytest.raises(ClientFailure, match="source_unavailable"):
        verify_source(tmp_path)


@pytest.mark.skipif(
    not os.environ.get("AGENTGATE_HERMES_SOURCE"),
    reason="Actual upstream Hermes runtime not configured; not an integration pass",
)
def test_actual_pinned_hermes_cycle_with_fixture_provider(live_agent_gateway):
    import json

    from agentgate.contracts import ActionResponse
    from agentgate.documents import demo_documents

    tools, provider, _, origin = live_agent_gateway
    result = run_hermes(
        Path(os.environ["AGENTGATE_HERMES_SOURCE"]), origin, tools.token, "Read the notes"
    )
    assert result["status"] == "completed"
    assert result["active_tools"] == ["documents_read", "mail_send", "memory_query"]
    assert len(provider.calls) == 2 and len(tools.executor.calls) == 1
    assert provider.calls[-1]["messages"][-1]["tool_call_id"] == "provider-call-7"
    envelope = json.loads(provider.calls[-1]["messages"][-1]["content"])
    response = ActionResponse.model_validate_json(envelope["result"])
    assert response.status == "completed" and response.executed
    assert response.result == {
        "document_id": "tenant-a-notes",
        "content": demo_documents()[0].content,
    }
    event = next(
        e
        for e in tools.store.events()
        if e.event_type == "action_completed" and e.operation == "documents.read"
    )
    assert response.action_id == event.action_id and response.trace_id == event.trace_id


@pytest.mark.skipif(
    not os.environ.get("AGENTGATE_HERMES_SOURCE"),
    reason="Actual upstream Hermes runtime not configured; not an integration pass",
)
@pytest.mark.parametrize(
    "scenario",
    [
        "invalid_operation",
        "malformed_arguments",
        "cross_tenant",
        "budget",
        "secret",
        "output_blocked",
        "pending",
        "forbidden_destination",
    ],
)
def test_actual_hermes_failures_stop_without_bypass_or_retry(live_agent_gateway, scenario):
    from test_scoped_tools import rows

    from agentgate.model_config import ModelPolicy, ResourceLimits

    tools, provider, _, origin = live_agent_gateway
    prompt = "Read notes"
    expected_dispatches = 1
    if scenario == "invalid_operation":
        provider.operation = "terminal"
    elif scenario == "malformed_arguments":
        provider.arguments = {"type": "object", "properties": {}, "required": ["document_id"]}
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
        tools.service.policy = tools.service.policy.model_copy(
            update={
                "output": tools.service.policy.output.model_copy(update={"redact_emails": False})
            }
        )
        provider.operation = "mail_send"
        provider.arguments = {
            "recipient": "a@demo.internal" if scenario == "pending" else "a@evil.example",
            "subject": "Review",
            "body": "Exact",
            "idempotency_key": "hermes-mail",
        }
    source = Path(os.environ["AGENTGATE_HERMES_SOURCE"])
    if scenario == "pending":
        result = run_hermes(source, origin, tools.token, prompt)
        assert result["status"] == "pending_approval" and result["action_id"]
    else:
        with pytest.raises(ClientFailure):
            run_hermes(source, origin, tools.token, prompt)
    assert len(provider.calls) == expected_dispatches
    assert rows(tools, "tool_outbox") == []
    assert len(tools.executor.calls) == (1 if scenario == "budget" else 0)
    expected_reason = {
        "invalid_operation": "EXECUTION_FAILED",
        "malformed_arguments": "MALFORMED_REQUEST",
        "cross_tenant": "RESOURCE_NOT_ALLOWED",
        "budget": "BUDGET_EXCEEDED",
        "secret": "SECRET_IN_INPUT",
        "output_blocked": "SECRET_IN_OUTPUT",
        "forbidden_destination": "RECIPIENT_DOMAIN_NOT_ALLOWED",
        "pending": "REQUIRES_APPROVAL",
    }[scenario]
    assert any(expected_reason in e.reason_codes for e in tools.store.events())


def test_profile_rejects_host_process_and_non_gateway_network(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import socket, subprocess
from agentgate.agents.hermes_runner import install_io_guard
install_io_guard("http://127.0.0.1:12345")
checks = 0
for call in (lambda: socket.create_connection(("127.0.0.1", 11434)), lambda: socket.getaddrinfo("example.com", 80), lambda: subprocess.run(["echo", "bypass"])):
    try: call()
    except PermissionError: checks += 1
assert checks == 3
""",
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("failure", ["duplicate_id", "invalid_json", "redirect"])
def test_model_protocol_failure_latches_without_replay(failure):
    import json

    import httpx

    from agentgate.agents.hermes_runner import ModelTransport

    sent = []

    def provider(request):
        body = json.loads(request.content)
        assert body["temperature"] == 0 and body["max_tokens"] == 128
        sent.append(body)
        if failure == "redirect":
            return httpx.Response(307, headers={"Location": "http://127.0.0.1:11434"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "same-id",
                                    "function": {
                                        "name": "documents_read",
                                        "arguments": "not json"
                                        if failure == "invalid_json"
                                        else '{"document_id":"notes"}',
                                    },
                                }
                            ]
                        },
                    }
                ]
            },
        )

    transport = ModelTransport(
        {
            "gateway": "http://127.0.0.1:8080",
            "token": "scoped-only",
            "model": "local-demo",
            "max_turns": 6,
            "max_tokens": 128,
        },
        [],
    )
    transport.inner.close()
    transport.inner = httpx.MockTransport(provider)
    request = httpx.Request(
        "POST",
        "http://127.0.0.1:8080/v1/chat/completions",
        json={"model": "local-demo", "messages": [], "temperature": 1, "max_tokens": 999},
    )
    if failure == "duplicate_id":
        assert transport.handle_request(request).status_code == 200
    with pytest.raises(RuntimeError, match="restricted profile stopped"):
        transport.handle_request(request)
    assert transport.failure
    with pytest.raises(RuntimeError, match="restricted profile stopped"):
        transport.handle_request(request)
    assert len(sent) == (2 if failure == "duplicate_id" else 1)
    transport.close()


@pytest.mark.skipif(
    not os.environ.get("AGENTGATE_HERMES_SOURCE"),
    reason="Actual upstream Hermes runtime not configured; not an integration pass",
)
def test_actual_hermes_explicit_approved_reinvocation_is_one_effect(live_agent_gateway):
    from test_scoped_tools import decide, rows

    tools, provider, model, origin = live_agent_gateway
    tools.service.policy = tools.service.policy.model_copy(
        update={"output": tools.service.policy.output.model_copy(update={"redact_emails": False})}
    )
    provider.operation = "mail_send"
    provider.arguments = {
        "recipient": "a@demo.internal",
        "subject": "Review",
        "body": "Exact approved",
        "idempotency_key": "hermes-approved",
    }
    source = Path(os.environ["AGENTGATE_HERMES_SOURCE"])
    first = run_hermes(source, origin, tools.token, "Send this exact mail")
    assert first["status"] == "pending_approval"
    assert rows(tools, "tool_outbox") == []
    decide(tools)
    second = run_hermes(source, origin, tools.token, "Send this exact mail")
    assert second["status"] == "completed"
    assert len(rows(tools, "tool_outbox")) == 1
    assert len(provider.calls) == 3
    assert all(e.root_run_id == tools.identity.root_run_id for e in tools.store.events())
    assert any(
        c["scope"] == "root_run" and c["resource"] == "calls" and c["spent"] == 3
        for c in model.ledger.counters()
    )


def test_installed_runner_bootstrap_does_not_shadow_upstream_dependencies(tmp_path):
    import importlib.metadata
    import shutil
    import subprocess
    import sys

    import agentgate

    site = tmp_path / "gateway-site-packages"
    package = site / "agentgate"
    shutil.copytree(
        Path(agentgate.__file__).parent, package, ignore=shutil.ignore_patterns("__pycache__")
    )
    fake = site / "mcp-99.99.dist-info"
    fake.mkdir()
    (fake / "METADATA").write_text("Metadata-Version: 2.1\nName: mcp\nVersion: 99.99\n")
    runner = package / "agents/hermes_runner.py"
    # Import the shipped runner without invoking upstream or any gateway request.
    code = "import importlib.metadata,runpy,sys; runpy.run_path(sys.argv[1],run_name='bootstrap_test'); print(importlib.metadata.version('mcp'))"
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code, str(runner)], capture_output=True, check=True, text=True
    )
    assert completed.stdout.strip() == importlib.metadata.version("mcp")
    assert completed.stdout.strip() != "99.99"


def test_runner_import_preserves_loaded_adapter_package():
    import importlib

    import agentgate
    import agentgate.tool_catalog

    package = agentgate
    catalog = agentgate.tool_catalog
    importlib.import_module("agentgate.agents.hermes_runner")
    assert importlib.import_module("agentgate") is package
    assert package.tool_catalog is catalog


@pytest.mark.skipif(
    not os.environ.get("AGENTGATE_HERMES_SOURCE"),
    reason="Prepared pinned Hermes environment not supplied",
)
def test_installed_runner_exposes_only_adapter_to_pinned_hermes_environment(tmp_path):
    import json
    import shutil
    import subprocess

    import agentgate

    source = Path(os.environ["AGENTGATE_HERMES_SOURCE"])
    verify_source(source)
    site = tmp_path / "installed-gateway-site-packages"
    package = site / "agentgate"
    shutil.copytree(
        Path(agentgate.__file__).parent, package, ignore=shutil.ignore_patterns("__pycache__")
    )
    for name in ("mcp", "openai", "httpx2", "hermes_agent"):
        metadata = site / (name + "-99.99.dist-info")
        metadata.mkdir()
        (metadata / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name.replace('_', '-')}\nVersion: 99.99\n"
        )
    runner = package / "agents/hermes_runner.py"
    code = (
        "import importlib.metadata,json,runpy,sys; "
        "runpy.run_path(sys.argv[1],run_name='bootstrap_test'); import agentgate; "
        "print(json.dumps({'versions':{p:importlib.metadata.version(p) for p in "
        "('hermes-agent','openai','mcp','httpx2')}, 'package':list(agentgate.__path__), 'sys_path':sys.path}))"
    )
    completed = subprocess.run(
        [str(source / ".venv/bin/python"), "-I", "-c", code, str(runner)],
        capture_output=True,
        check=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["versions"] == {
        "hermes-agent": "0.21.5",
        "openai": "2.24.0",
        "mcp": "2.0.0",
        "httpx2": "2.7.0",
    }
    assert result["package"] == [str(package)]
    assert str(site) not in result["sys_path"]
