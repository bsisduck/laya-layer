"""Strict boundary contracts shared by the HTTP adapter and enforcement core."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class Identity(Contract):
    principal_id: Identifier
    tenant_id: Identifier
    agent_id: Identifier
    root_run_id: Identifier
    roles: tuple[Identifier, ...]
    operations: tuple[Identifier, ...]


class ActionRequest(Contract):
    operation: Annotated[str, Field(min_length=1, max_length=96)]
    arguments: dict[str, JsonValue]


class DocumentArguments(Contract):
    document_id: Identifier


class DocumentMetadata(Contract):
    document_id: Identifier
    tenant_id: Identifier
    classification: Literal["public", "internal", "confidential", "secret"]


class Reason(StrEnum):
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INVALID_CREDENTIAL = "INVALID_CREDENTIAL"
    IDENTITY_OVERRIDE = "IDENTITY_OVERRIDE"
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    BODY_TOO_LARGE = "BODY_TOO_LARGE"
    UNSUPPORTED_CONTENT_TYPE = "UNSUPPORTED_CONTENT_TYPE"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    UNKNOWN_OPERATION = "UNKNOWN_OPERATION"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    RESOURCE_NOT_ALLOWED = "RESOURCE_NOT_ALLOWED"
    REQUIRED_SEMANTIC_UNAVAILABLE = "REQUIRED_SEMANTIC_UNAVAILABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    SEMANTIC_BLOCKED = "SEMANTIC_BLOCKED"
    SEMANTIC_ABSTAIN = "SEMANTIC_ABSTAIN"
    SEMANTIC_INCOMPLETE = "SEMANTIC_INCOMPLETE"
    SEMANTIC_INVALID = "SEMANTIC_INVALID"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    OUTPUT_INVALID = "OUTPUT_INVALID"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    SECRET_IN_OUTPUT = "SECRET_IN_OUTPUT"
    EMAIL_REDACTED = "EMAIL_REDACTED"
    ALLOWED = "ALLOWED"


class ActionResponse(Contract):
    status: Literal["completed", "denied", "error"]
    action_id: str
    trace_id: str
    decision: Literal["allow", "redact", "deny"]
    reason_codes: tuple[Reason, ...]
    policy_version: str
    executed: bool
    result: dict[str, str] | None = None


class AuditEvent(Contract):
    event_id: str
    event_type: Literal[
        "action_denied", "dispatch_intent", "action_completed", "output_blocked", "execution_failed"
    ]
    timestamp: float
    action_id: str
    trace_id: str
    principal_id: str | None
    tenant_id: str | None
    root_run_id: str | None
    operation: Literal["documents.read"] | None
    decision: Literal["allow", "redact", "deny"]
    reason_codes: tuple[Reason, ...]
    policy_version: str
    payload_digest: str | None
    executed: bool
    semantic_status: Literal[
        "not_configured",
        "not_run_hard_denial",
        "unavailable",
        "ok",
        "abstain",
        "incomplete",
        "invalid_output",
    ]
    semantic: SemanticResult | None = None


class SemanticCoverage(Contract):
    complete: bool
    windows_evaluated: Annotated[int, Field(ge=0)]
    input_truncated: bool
    options_collapsed: bool


class SemanticResult(Contract):
    request_id: str
    backend: Literal["laya_standard", "laya_coreml"]
    checkpoint_revision: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    question_set_id: str
    status: Literal["ok", "abstain", "incomplete", "unavailable", "invalid_output"]
    selected_labels: dict[str, str]
    raw_scores: dict[str, float]
    coverage: SemanticCoverage
    usage: SemanticUsage


class SemanticUsage(Contract):
    input_tokens: Annotated[int, Field(ge=0, le=1024)]
    output_tokens: Literal[0] = 0
    inference_wall_ms: Annotated[float, Field(ge=0, le=60000)]
