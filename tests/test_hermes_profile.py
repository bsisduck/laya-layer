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
    tools, provider, _, origin = live_agent_gateway
    result = run_hermes(
        Path(os.environ["AGENTGATE_HERMES_SOURCE"]), origin, tools.token, "Read the notes"
    )
    assert result["status"] == "completed"
    assert result["active_tools"] == ["documents_read", "mail_send", "memory_query"]
    assert len(provider.calls) == 2 and len(tools.executor.calls) == 1
    assert provider.calls[-1]["messages"][-1]["tool_call_id"] == "provider-call-7"


@pytest.mark.skipif(
    not os.environ.get("AGENTGATE_HERMES_SOURCE"),
    reason="Actual upstream Hermes runtime not configured; not an integration pass",
)
@pytest.mark.parametrize(
    "scenario",
    [
        "invalid_operation",
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
