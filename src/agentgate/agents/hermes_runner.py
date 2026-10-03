"""Pinned Hermes process entry point; invoked only by the sanitized parent launcher.

This uses upstream AIAgent.run_conversation, tool selection, dispatch and MCP SDK.
The local adapter narrows those capabilities; it does not implement an agent loop.
"""

import importlib
import importlib.metadata
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

# Direct file execution inside the isolated upstream environment.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentgate.agents.client import ALIASES, MAX_BYTES, ClientFailure, decode  # noqa: E402


class ProfileStop(BaseException):
    """Escape upstream's Exception-based retry/recovery paths without replay."""

    def __init__(self, reason: str, *, pending: dict[str, Any] | None = None) -> None:
        self.reason, self.pending = reason, pending


def install_io_guard(origin: str) -> None:
    target = urlsplit(origin)

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or address[:2] != (target.hostname, target.port):
                raise PermissionError("restricted_profile_network")
        if event == "socket.getaddrinfo" and args[0] not in (target.hostname, None):
            raise PermissionError("restricted_profile_dns")
        if event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork"):
            raise PermissionError("restricted_profile_process")

    sys.addaudithook(audit)


class ModelTransport(httpx.BaseTransport):
    def __init__(self, payload: dict[str, Any], trace: list[dict[str, Any]]) -> None:
        self.payload, self.trace = payload, trace
        self.inner = httpx.HTTPTransport(retries=0, trust_env=False)
        self.count = 0
        self.failure: str | None = None
        self.seen_ids: set[str] = set()
        self.registry_check: Any = lambda: None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.failure:
            raise RuntimeError("restricted profile stopped")
        try:
            return self._handle(request)
        except ProfileStop as stopped:
            self.failure = stopped.reason
            raise RuntimeError("restricted profile stopped") from None
        except (ClientFailure, KeyError, IndexError, TypeError, ValueError):
            self.failure = "invalid_model_protocol_no_retry"
            raise RuntimeError("restricted profile stopped") from None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.registry_check()
        if (
            str(request.url) != self.payload["gateway"] + "/v1/chat/completions"
            or request.method != "POST"
        ):
            raise ProfileStop("unsupported_model_endpoint")
        self.count += 1
        if self.count > self.payload["max_turns"]:
            raise ProfileStop("turn_limit")
        data = decode(request.read())
        # Pinned Hermes adds inference-only hints and message display metadata.
        # Drop only this reviewed set; new or routing/identity fields fail closed.
        for optional in ("reasoning", "reasoning_effort", "store", "metadata"):
            data.pop(optional, None)
        if "max_completion_tokens" in data:
            data["max_tokens"] = data.pop("max_completion_tokens")
        allowed = {
            "model",
            "messages",
            "tools",
            "tool_choice",
            "max_tokens",
            "temperature",
            "stream",
            "parallel_tool_calls",
            "n",
        }
        if set(data) - allowed or data.get("model") != self.payload["model"] or data.get("stream"):
            raise ProfileStop("unsupported_model_fields_" + "_".join(sorted(set(data) - allowed)))
        data["max_tokens"] = self.payload["max_tokens"]
        data["temperature"] = 0
        data["parallel_tool_calls"] = False
        for message in data["messages"]:
            for field in ("reasoning", "reasoning_content", "name"):
                message.pop(field, None)
        if len(json.dumps(data).encode()) > MAX_BYTES:
            raise ProfileStop("model_request_too_large")
        forwarded = httpx.Request(
            "POST",
            request.url,
            json=data,
            headers={
                "Authorization": "Bearer " + self.payload["token"],
                "Accept-Encoding": "identity",
            },
            extensions={"timeout": {"connect": 10, "read": 60, "write": 10, "pool": 10}},
        )
        try:
            response = self.inner.handle_request(forwarded)
            try:
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise ProfileStop("model_response_too_large")
            finally:
                response.close()
            self.trace.append(
                {
                    "operation": "chat.completions",
                    "http_status": response.status_code,
                    "tool_result_ids": [
                        m["tool_call_id"] for m in data["messages"] if m["role"] == "tool"
                    ],
                }
            )
            if response.status_code != 200:
                raise ProfileStop(f"model_rejected_{response.status_code}_no_retry")
            returned = decode(bytes(raw))
            calls = returned["choices"][0]["message"].get("tool_calls") or []
            if calls:
                if (
                    len(calls) != 1
                    or self.count >= self.payload["max_turns"]
                    or returned["choices"][0].get("finish_reason") != "tool_calls"
                ):
                    raise ProfileStop("turn_or_tool_limit")
                call_id = calls[0]["id"]
                if not isinstance(call_id, str) or not call_id or call_id in self.seen_ids:
                    raise ProfileStop("invalid_or_repeated_call_id")
                decode(calls[0]["function"]["arguments"])
                self.seen_ids.add(call_id)
            self.trace[-1]["tool_call_ids"] = [c["id"] for c in calls]
            self.trace[-1]["completion_id"] = returned.get("id")
            self.trace[-1]["trace_id"] = returned.get("agentgate", {}).get("trace_id")
            return httpx.Response(200, json=returned, request=request)
        except httpx.HTTPError:
            raise ProfileStop("model_transport_failed_no_retry") from None

    def close(self) -> None:
        self.inner.close()


def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    versions = {
        name: importlib.metadata.version(name)
        for name in ("hermes-agent", "openai", "mcp", "httpx2")
    }
    if versions != {
        "hermes-agent": "0.21.5",
        "openai": "2.24.0",
        "mcp": "2.0.0",
        "httpx2": "2.7.0",
    }:
        raise ProfileStop("runtime_version_mismatch")
    install_io_guard(payload["gateway"])
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, payload["source"])
    env_loader: Any = importlib.import_module("hermes_cli.env_loader")
    env_loader.load_hermes_dotenv = lambda *args, **kwargs: []
    upstream = importlib.import_module("run_agent")
    mcp = importlib.import_module("tools.mcp_tool")
    handlers: Any = importlib.import_module("tools.mcp_tool_handlers")
    registry = importlib.import_module("tools.registry").registry
    openai = importlib.import_module("openai")
    trace: list[dict[str, Any]] = []
    transport = ModelTransport(payload, trace)
    dispatch = handlers._dispatch

    def single_attempt(
        server_name: Any,
        server: Any,
        op: Any,
        call: Any,
        tool_timeout: Any,
        recoverers: Any,
        on_final_failure: Any,
        record_outcome: bool = False,
    ) -> Any:
        return dispatch(
            server_name, server, op, call, tool_timeout, (), on_final_failure, record_outcome
        )

    handlers._dispatch = single_attempt
    names = mcp.discover_mcp_tools(allowed_mcp_names=["agentgate"])
    mapping = {"mcp__agentgate__" + name: name for name in ALIASES.values()}
    if not names or set(names) - set(mapping):
        raise ProfileStop("mcp_discovery_mismatch")
    actual = {mapping[name] for name in names}
    entries = {mapping[name]: registry.get_entry(name) for name in names}
    # Remove native tools from the registry, then expose exact gateway aliases
    # pointing at upstream-discovered MCP handlers and their actual schemas.
    for entry in registry.get_all_entries():
        registry.deregister(entry.name)
        registry.deregister(entry.name, scope=registry.current_scope_key())

    def guarded_handler(handler: Any, name: str, properties: dict[str, Any]) -> Any:
        def call(arguments: dict[str, Any], **kwargs: Any) -> str:
            # Schema field names/types only; never model-provided keys or values.
            trace.append(
                {
                    "operation": name,
                    "argument_types": {
                        key: type(value).__name__
                        for key, value in arguments.items()
                        if key in properties
                    },
                    "unknown_argument_count": len(set(arguments) - set(properties)),
                }
            )
            raw = handler(arguments, **kwargs)
            envelope = decode(raw)
            if "error" in envelope:
                raise ProfileStop("tool_failed_no_retry")
            result = envelope.get("structuredContent", envelope.get("result"))
            result = decode(result) if isinstance(result, str) else result
            if not isinstance(result, dict):
                raise ProfileStop("invalid_tool_result")
            trace.append(
                {
                    "operation": name,
                    "trace_id": result.get("trace_id"),
                    "status": result.get("status"),
                }
            )
            if result.get("status") == "pending_approval" and result.get("executed") is False:
                raise ProfileStop(
                    "pending_approval",
                    pending={
                        "action_id": result["action_id"],
                        "approval_id": result.get("approval_id"),
                    },
                )
            if result.get("status") != "completed" or result.get("executed") is not True:
                raise ProfileStop("tool_rejected_no_retry")
            return str(raw)

        return call

    for name, entry in entries.items():
        schema = dict(entry.schema, name=name)
        registry.register(
            name=name,
            toolset="agentgate-restricted",
            schema=schema,
            handler=guarded_handler(entry.handler, name, schema["parameters"]["properties"]),
            is_async=False,
        )

    def verify_registry() -> None:
        if set(registry.get_all_tool_names()) != actual:
            raise ProfileStop("active_tool_registry_changed")

    transport.registry_check = verify_registry

    class RestrictedHermes(upstream.AIAgent):  # type: ignore[misc, name-defined]
        def _build_system_prompt(self, system_message: str | None = None) -> str:
            return (
                system_message or "Use the discovered gateway tools and answer from their results."
            )

        def _create_openai_client(self, client_kwargs: Any, **kwargs: Any) -> Any:
            return openai.OpenAI(
                api_key=payload["token"],
                base_url=payload["gateway"] + "/v1",
                max_retries=0,
                http_client=httpx.Client(transport=transport, trust_env=False),
            )

    agent = RestrictedHermes(
        model=payload["model"],
        provider="custom",
        api_mode="chat_completions",
        base_url=payload["gateway"] + "/v1",
        api_key=payload["token"],
        enabled_toolsets=["agentgate-restricted"],
        max_iterations=payload["max_turns"],
        max_tokens=payload["max_tokens"],
        quiet_mode=True,
        save_trajectories=False,
        verbose_logging=False,
        skip_context_files=True,
        load_soul_identity=False,
        skip_memory=True,
        skip_background_review=True,
        fallback_model=None,
        session_db=None,
        checkpoints_enabled=False,
        run_budget_seconds=240,
    )
    try:
        verify_registry()
        if agent.valid_tool_names != actual:
            raise ProfileStop("agent_tool_mismatch_" + "_".join(sorted(agent.valid_tool_names)))
        if agent.compression_enabled or agent._memory_enabled:
            raise ProfileStop("agent_memory_or_compression_enabled")
        result = agent.run_conversation(
            payload["prompt"],
            system_message=(
                "Use only the discovered tools. Tool arguments must match the supplied JSON "
                "schema exactly; do not wrap them in an arguments or parameters field. "
                "After a successful tool result, answer concisely without another tool call."
            ),
        )
        if not result.get("completed") or result.get("error"):
            raise ProfileStop(transport.failure or "upstream_incomplete_no_retry")
        return {
            "status": "completed",
            "text": result["final_response"],
            "active_tools": sorted(actual),
            "trace": trace,
        }
    except ProfileStop as stopped:
        if stopped.pending:
            return {
                "status": "pending_approval",
                **stopped.pending,
                "active_tools": sorted(actual),
                "trace": trace,
            }
        return {"status": "failed", "reason": stopped.reason, "trace": trace}
    finally:
        agent.close()
        mcp.shutdown_mcp_servers()


def main() -> None:
    os.umask(0o077)
    result: dict[str, Any]
    try:
        payload = decode(sys.stdin.buffer.read(MAX_BYTES + 1))
        result = invoke(payload)
    except ProfileStop as stopped:
        result = {"status": "failed", "reason": stopped.reason}
    except Exception as error:
        result = {"status": "failed", "reason": "runtime_" + type(error).__name__}
    Path("result.json").write_text(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
