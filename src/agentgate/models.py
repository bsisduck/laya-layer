"""Bounded Chat Completions over a private provider; nothing streams before inspection."""

import asyncio
import json
from functools import partial
from typing import Annotated, Literal, Protocol, Self, cast
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from agentgate.budgets import BudgetExceeded
from agentgate.contracts import ActionResponse, Contract, Identifier, Reason
from agentgate.control_plane import ControlsChanged, ThreatBlocked
from agentgate.model_budgets import ModelLedger
from agentgate.policy import Policy
from agentgate.semantics import SemanticBudgetExceeded, SemanticInvalid, SemanticUnavailable
from agentgate.service import EMAIL, SYNTHETIC_SECRET, ActionService, Context, GateError
from agentgate.storage import CredentialInvalid, StorageUnavailable

ToolName = Literal["documents_read", "memory_query", "mail_send"]


class FunctionCall(Contract):
    name: ToolName
    arguments: Annotated[str, Field(max_length=16384)]


class ToolCall(Contract):
    id: Annotated[str, Field(min_length=1, max_length=128)]
    type: Literal["function"] = "function"
    function: FunctionCall


class ChatMessage(Contract):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: Annotated[str, Field(max_length=65536)] | None = None
    tool_call_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    tool_calls: Annotated[list[ToolCall], Field(min_length=1, max_length=8)] | None = None

    @model_validator(mode="after")
    def valid_role(self) -> Self:
        if (self.role == "tool") != (self.tool_call_id is not None):
            raise ValueError("Tool messages require correlation")
        if self.tool_calls is not None and self.role != "assistant":
            raise ValueError("Only assistants propose tool calls")
        if self.content is None and not self.tool_calls:
            raise ValueError("Message has no content")
        return self


class FunctionDefinition(Contract):
    name: ToolName
    description: Annotated[str, Field(max_length=1024)] = ""
    parameters: dict[str, JsonValue]


class ToolDefinition(Contract):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class StreamOptions(Contract):
    include_usage: bool = True


class ChatRequest(Contract):
    model: Identifier
    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=64)]
    max_tokens: Annotated[int, Field(ge=1, le=4096)] = 256
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    stream: bool = False
    stream_options: StreamOptions | None = None
    tools: Annotated[list[ToolDefinition], Field(min_length=1, max_length=3)] | None = None
    tool_choice: Literal["auto", "none", "required"] = "auto"
    parallel_tool_calls: Literal[False] = False
    n: Literal[1] = 1


class Provider(Protocol):
    def complete(self, payload: dict[str, JsonValue]) -> bytes: ...


class PrivateProvider:
    """Fixed loopback origin, no redirects, proxy environment, retries or fallback."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 45.0) -> None:
        url = urlsplit(base_url)
        if (
            url.scheme != "http"
            or url.hostname not in ("127.0.0.1", "::1")
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/", "/v1", "/v1/")
            or not token
            or not 0 < timeout <= 120
        ):
            raise ValueError("Provider must be an authenticated fixed loopback endpoint")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.token = token
        self.timeout = timeout

    def complete(self, payload: dict[str, JsonValue]) -> bytes:
        return asyncio.run(self._complete(payload))

    async def _complete(self, payload: dict[str, JsonValue]) -> bytes:
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(
                    timeout=self.timeout, trust_env=False, follow_redirects=False
                ) as client:
                    async with client.stream(
                        "POST",
                        self.url,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Accept-Encoding": "identity",
                        },
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        if response.headers.get("content-encoding", "identity") != "identity":
                            raise ValueError("Compressed upstream responses are unsupported")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > 262144:
                                raise ValueError("Provider response too large")
                            raw.extend(chunk)
                        return bytes(raw)
        except TimeoutError as error:
            raise httpx.ReadTimeout("Private provider total deadline exceeded") from error


class Usage(Contract):
    prompt_tokens: Annotated[int, Field(ge=0, le=10_000_000)]
    completion_tokens: Annotated[int, Field(ge=0, le=10_000_000)]
    total_tokens: Annotated[int, Field(ge=0, le=20_000_000)]
    # Provider-specific usage breakdowns are ignored, never forwarded.
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)

    @model_validator(mode="after")
    def sum_matches(self) -> Self:
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("Inconsistent usage")
        return self


class ProviderMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    role: Literal["assistant"]
    content: str | None = None
    tool_calls: Annotated[list[ToolCall], Field(max_length=8)] | None = None


class Choice(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    index: Literal[0]
    message: ProviderMessage
    finish_reason: Literal["stop", "length", "tool_calls"]


class Completion(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    choices: Annotated[list[Choice], Field(min_length=1, max_length=1)]
    usage: Usage


def unpack_calls(value: JsonValue, depth: int = 0) -> JsonValue:
    """Decode the protocol's JSON-in-a-string boundary before inspecting contents."""
    from agentgate.app import reject_constant, unique_object

    if depth > 24:
        raise ValueError("Tool argument depth exceeded")
    if isinstance(value, list):
        return [unpack_calls(item, depth + 1) for item in value]
    if not isinstance(value, dict):
        return value
    result = dict(value)
    function = result.get("function")
    if "id" in result and result.get("type") == "function" and isinstance(function, dict):
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            decoded = json.loads(
                arguments, object_pairs_hook=unique_object, parse_constant=reject_constant
            )
            if not isinstance(decoded, dict):
                raise ValueError("Tool arguments must be a JSON object")
            result["function"] = dict(function, arguments=decoded)
    return {key: unpack_calls(item, depth + 1) for key, item in result.items()}


def pack_calls(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [pack_calls(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: pack_calls(item) for key, item in value.items()}
    function = result.get("function")
    if "id" in result and result.get("type") == "function" and isinstance(function, dict):
        arguments = function.get("arguments")
        if isinstance(arguments, dict):
            result["function"] = dict(
                function, arguments=json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
            )
    return result


def text_leaves(value: JsonValue) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in text_leaves(item)]
    if isinstance(value, dict):
        return [text for key, item in value.items() for text in [key, *text_leaves(item)]]
    return []


def redact_content(value: JsonValue, field: str = "") -> JsonValue:
    if isinstance(value, str):
        redacted = EMAIL.sub("[REDACTED_EMAIL]", value)
        if redacted != value and field not in {
            "content",
            "body",
            "subject",
            "query",
            "description",
        }:
            raise ValueError("Cannot redact routing, identity or schema fields")
        return redacted
    if isinstance(value, list):
        return [redact_content(item, field) for item in value]
    if isinstance(value, dict):
        if any(EMAIL.search(key) for key in value):
            raise ValueError("Cannot redact schema or argument names")
        return {key: redact_content(item, key) for key, item in value.items()}
    return value


class ModelService:
    def __init__(self, actions: ActionService, provider: Provider) -> None:
        self.actions = actions
        self.provider = provider
        self.ledger = ModelLedger(actions.store)

    def reject(
        self, context: Context, error: GateError | StorageUnavailable
    ) -> tuple[int, ActionResponse]:
        denied = error if isinstance(error, GateError) else GateError(503, Reason.AUDIT_UNAVAILABLE)
        if not context.executed:
            return self.actions.reject(context, denied)
        # The terminal model event and usage have already been written together.
        # On audit failure, unresolved reservation remains and output stays withheld.
        return denied.status_code, ActionResponse(
            status="error" if denied.status_code >= 500 else "denied",
            action_id=context.action_id,
            trace_id=context.trace_id,
            decision="deny",
            reason_codes=(denied.reason,),
            policy_version=context.controls.policy.version if context.controls else "unavailable",
            executed=True,
        )

    @staticmethod
    def inspect(service: ActionService, context: Context, content: str, *, incoming: bool) -> str:
        snapshot = service.context_controls(context)
        policy = snapshot.policy
        invalid = Reason.MALFORMED_REQUEST if incoming else Reason.OUTPUT_INVALID
        try:
            normalized = unpack_calls(cast(JsonValue, json.loads(content)))
            strings = text_leaves(normalized)
            inspected_text = "\n".join(strings)
            snapshot.inspect("model_input" if incoming else "model_output", inspected_text)
        except ThreatBlocked as error:
            raise GateError(403, Reason.THREAT_FEED_BLOCKED) from error
        except (ValueError, UnicodeError, RecursionError) as error:
            raise GateError(422 if incoming else 503, invalid) from error
        if any(SYNTHETIC_SECRET.search(value) for value in strings):
            raise GateError(403, Reason.SECRET_IN_INPUT if incoming else Reason.SECRET_IN_OUTPUT)
        if policy.semantic_required:
            if not service.semantic_ready(policy) or service.semantic is None:
                raise GateError(503, Reason.REQUIRED_SEMANTIC_UNAVAILABLE)
            try:
                result = service.semantic.evaluate(context.action_id, inspected_text)
                context.semantic = result
            except SemanticBudgetExceeded as error:
                context.semantic_failure = "unavailable"
                raise GateError(429, Reason.SEMANTIC_BUDGET_EXCEEDED) from error
            except SemanticUnavailable as error:
                context.semantic_failure = "unavailable"
                raise GateError(503, Reason.REQUIRED_SEMANTIC_UNAVAILABLE) from error
            except SemanticInvalid as error:
                context.semantic_failure = "invalid_output"
                raise GateError(503, Reason.SEMANTIC_INVALID) from error
            if result.status not in ("ok", "abstain"):
                raise GateError(503, Reason.SEMANTIC_INCOMPLETE)
            if policy.semantic_mode == "enforce":
                if result.status == "abstain":
                    raise GateError(403, Reason.SEMANTIC_ABSTAIN)
                if result.selected_labels["content_role"] == "behavior_instruction":
                    raise GateError(403, Reason.SEMANTIC_BLOCKED)
        try:
            if policy.output.redact_emails:
                normalized = redact_content(normalized)
            released = json.dumps(pack_calls(normalized), ensure_ascii=False, separators=(",", ":"))
            maximum = (
                policy.models.max_input_bytes
                if incoming and policy.models
                else policy.output.max_result_bytes
            )
            if len(released.encode()) > maximum:
                raise GateError(
                    413 if incoming else 403,
                    Reason.BODY_TOO_LARGE if incoming else Reason.OUTPUT_TOO_LARGE,
                )
            return released
        except (ValueError, UnicodeError, RecursionError) as error:
            raise GateError(403, invalid) from error

    def complete(self, context: Context, request: ChatRequest) -> dict[str, JsonValue]:
        # Keep one immutable policy snapshot through reservation/inspection/evidence.
        service = self.actions
        context.operation = "chat.completions"
        identity, digest = context.identity, context.credential_digest
        if identity is None or digest is None:
            raise GateError(401, Reason.AUTHENTICATION_REQUIRED)
        if "chat.completions" not in identity.operations:
            raise GateError(403, Reason.OPERATION_NOT_ALLOWED)
        for attempt in range(3):
            snapshot = service.current_controls()
            context.controls = snapshot
            policy: Policy = snapshot.policy
            limits = policy.models
            if limits is None or request.model not in limits.aliases:
                raise GateError(403, Reason.MODEL_NOT_ALLOWED)
            service.authorize_authority(context, policy, "chat.completions", request.model)
            if request.max_tokens > limits.max_output_tokens:
                raise GateError(422, Reason.MALFORMED_REQUEST)
            payload = request.model_dump(mode="json", exclude_none=True)
            payload["stream"] = False
            payload.pop("stream_options", None)
            # Ollama does not accept parallel_tool_calls; enforce the single-call
            # contract on the returned message instead of silently dropping controls.
            payload.pop("parallel_tool_calls", None)
            if request.tools is None:
                payload.pop("tool_choice", None)
                payload.pop("parallel_tool_calls", None)
            serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            try:
                size = len(serialized.encode())
            except UnicodeError as error:
                raise GateError(422, Reason.MALFORMED_REQUEST) from error
            if size > limits.max_input_bytes:
                raise GateError(413, Reason.BODY_TOO_LARGE)
            inspected = self.inspect(service, context, serialized, incoming=True)
            payload = json.loads(inspected)
            redacted = (
                EMAIL.search(
                    "\n".join(text_leaves(unpack_calls(cast(JsonValue, json.loads(serialized)))))
                )
                is not None
                and policy.output.redact_emails
            )
            input_bound = len(inspected.encode()) + limits.template_token_allowance
            try:
                self.ledger.reserve(
                    digest,
                    identity,
                    service.event(context, "dispatch_intent", Reason.ALLOWED, "allow"),
                    limits,
                    input_bound,
                    request.max_tokens,
                    service.clock,
                    partial(
                        service.check_dispatch_authority,
                        context=context,
                        snapshot=snapshot,
                        operation="chat.completions",
                        resource=request.model,
                    ),
                )
            except ControlsChanged as error:
                if attempt == 2:
                    raise GateError(409, Reason.CONTROLS_CHANGED) from error
                continue
            except CredentialInvalid as error:
                raise GateError(401, Reason.INVALID_CREDENTIAL) from error
            except BudgetExceeded as error:
                raise GateError(429, Reason.BUDGET_EXCEEDED) from error
            break
        context.executed = True
        usage: tuple[int, int] | None = None
        try:
            raw = self.provider.complete(payload)
            if len(raw) > 262144:
                raise GateError(503, Reason.OUTPUT_TOO_LARGE)
            response = Completion.model_validate_json(raw)
            usage = (response.usage.prompt_tokens, response.usage.completion_tokens)
            if usage[0] > input_bound or usage[1] > request.max_tokens:
                raise GateError(503, Reason.USAGE_INVALID)
            message = response.choices[0].message
            names = {tool.function.name for tool in request.tools or []}
            if message.tool_calls and (
                request.tool_choice == "none"
                or len(message.tool_calls) > 1
                or any(call.function.name not in names for call in message.tool_calls)
                or len({call.id for call in message.tool_calls}) != len(message.tool_calls)
            ):
                raise GateError(503, Reason.OUTPUT_INVALID)
            if message.content is None and not message.tool_calls:
                raise GateError(503, Reason.OUTPUT_INVALID)
            for call in message.tool_calls or []:
                from agentgate.app import reject_constant, unique_object

                arguments = json.loads(
                    call.function.arguments,
                    object_pairs_hook=unique_object,
                    parse_constant=reject_constant,
                )
                if not isinstance(arguments, dict):
                    raise GateError(503, Reason.OUTPUT_INVALID)
            output = message.model_dump_json(exclude_none=True)
            if len(output.encode()) > policy.output.max_result_bytes:
                raise GateError(403, Reason.OUTPUT_TOO_LARGE)
            released = self.inspect(service, context, output, incoming=False)
            redacted = redacted or (
                EMAIL.search(
                    "\n".join(text_leaves(unpack_calls(cast(JsonValue, json.loads(output)))))
                )
                is not None
                and policy.output.redact_emails
            )
            decision: Literal["redact", "allow"] = "redact" if redacted else "allow"
            reason = Reason.EMAIL_REDACTED if redacted else Reason.ALLOWED
            event = service.event(context, "action_completed", reason, decision)
        except (GateError, httpx.HTTPError, ValueError, UnicodeError) as error:
            failure = (
                error if isinstance(error, GateError) else GateError(503, Reason.EXECUTION_FAILED)
            )
            event = service.event(
                context,
                "output_blocked" if usage is not None else "execution_failed",
                failure.reason,
                "deny",
            )
            self.ledger.finish(event, usage)
            raise failure from error
        self.ledger.finish(event, usage)
        return {
            "id": context.action_id,
            "object": "chat.completion",
            "created": int(service.clock()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": json.loads(released),
                    "finish_reason": response.choices[0].finish_reason,
                }
            ],
            "usage": response.usage.model_dump(mode="json"),
            "agentgate": {
                "trace_id": context.trace_id,
                "policy_version": policy.version,
                "decision": decision,
                "executed": True,
                "buffered": request.stream,
            },
        }
