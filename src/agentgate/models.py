"""Bounded Chat Completions over a private provider; nothing streams before inspection."""

import copy
import json
from typing import Annotated, Literal, Protocol, Self
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from agentgate.budgets import BudgetExceeded
from agentgate.contracts import Contract, Identifier, Reason
from agentgate.model_budgets import ModelLedger
from agentgate.policy import Policy
from agentgate.semantics import SemanticInvalid, SemanticUnavailable
from agentgate.service import EMAIL, SYNTHETIC_SECRET, ActionService, Context, GateError
from agentgate.storage import CredentialInvalid

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
        with httpx.Client(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
            with client.stream(
                "POST", self.url, headers={"Authorization": f"Bearer {self.token}"}, json=payload
            ) as response:
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise ValueError("Compressed upstream responses are unsupported")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    if len(raw) + len(chunk) > 262144:
                        raise ValueError("Provider response too large")
                    raw.extend(chunk)
                return bytes(raw)


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


class ModelService:
    def __init__(self, actions: ActionService, provider: Provider) -> None:
        self.actions = actions
        self.provider = provider
        self.ledger = ModelLedger(actions.store)

    @staticmethod
    def inspect(service: ActionService, context: Context, content: str, *, incoming: bool) -> str:
        policy = service.policy
        if SYNTHETIC_SECRET.search(content):
            raise GateError(403, Reason.SECRET_IN_INPUT if incoming else Reason.SECRET_IN_OUTPUT)
        if policy.semantic_required:
            if not service.semantic_ready() or service.semantic is None:
                raise GateError(503, Reason.REQUIRED_SEMANTIC_UNAVAILABLE)
            try:
                result = service.semantic.evaluate(context.action_id, content)
                context.semantic = result
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
        return EMAIL.sub("[REDACTED_EMAIL]", content) if policy.output.redact_emails else content

    def complete(self, context: Context, request: ChatRequest) -> dict[str, JsonValue]:
        # Keep one immutable policy snapshot through reservation/inspection/evidence.
        service = copy.copy(self.actions)
        policy: Policy = service.policy
        limits = policy.models
        context.operation = "chat.completions"
        identity, digest = context.identity, context.credential_digest
        if identity is None or digest is None:
            raise GateError(401, Reason.AUTHENTICATION_REQUIRED)
        if "chat.completions" not in identity.operations:
            raise GateError(403, Reason.OPERATION_NOT_ALLOWED)
        if limits is None or request.model not in limits.aliases:
            raise GateError(403, Reason.MODEL_NOT_ALLOWED)
        if request.max_tokens > limits.max_output_tokens:
            raise GateError(422, Reason.MALFORMED_REQUEST)
        payload = request.model_dump(mode="json", exclude_none=True)
        payload["stream"] = False
        payload.pop("stream_options", None)
        if request.tools is None:
            payload.pop("tool_choice", None)
            payload.pop("parallel_tool_calls", None)
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode()) > limits.max_input_bytes:
            raise GateError(413, Reason.BODY_TOO_LARGE)
        inspected = self.inspect(service, context, serialized, incoming=True)
        payload = json.loads(inspected)
        redacted = serialized != inspected
        input_bound = len(inspected.encode()) + limits.template_token_allowance
        if self.actions.policy.version != policy.version:
            raise GateError(409, Reason.RESOURCE_NOT_ALLOWED)
        try:
            self.ledger.reserve(
                digest,
                identity,
                service.event(context, "dispatch_intent", Reason.ALLOWED, "allow"),
                limits,
                input_bound,
                request.max_tokens,
                service.clock,
            )
        except CredentialInvalid as error:
            raise GateError(401, Reason.INVALID_CREDENTIAL) from error
        except BudgetExceeded as error:
            raise GateError(429, Reason.BUDGET_EXCEEDED) from error
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
                or any(call.function.name not in names for call in message.tool_calls)
                or len({call.id for call in message.tool_calls}) != len(message.tool_calls)
            ):
                raise GateError(503, Reason.OUTPUT_INVALID)
            if message.content is None and not message.tool_calls:
                raise GateError(503, Reason.OUTPUT_INVALID)
            output = message.model_dump_json(exclude_none=True)
            if len(output.encode()) > policy.output.max_result_bytes:
                raise GateError(403, Reason.OUTPUT_TOO_LARGE)
            released = self.inspect(service, context, output, incoming=False)
            redacted = redacted or output != released
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
