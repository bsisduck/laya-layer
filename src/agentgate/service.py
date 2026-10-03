"""Document enforcement independent of HTTP, agent frameworks, and inference imports."""

import hashlib
import hmac
import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from agentgate.budgets import BudgetExceeded
from agentgate.contracts import (
    ActionRequest,
    ActionResponse,
    AuditEvent,
    DocumentArguments,
    Identity,
    Reason,
)
from agentgate.documents import DocumentExecutor, DocumentRegistry
from agentgate.policy import Policy
from agentgate.storage import CredentialInvalid, StorageUnavailable, Store, credential_digest

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}\b")
SYNTHETIC_SECRET = re.compile(r"AGENTGATE_SECRET\[")


@dataclass
class Context:
    action_id: str
    trace_id: str
    identity: Identity | None = None
    credential_digest: str | None = None
    payload_digest: str | None = None
    operation: Literal["documents.read"] | None = None
    executed: bool = False


class GateError(Exception):
    def __init__(self, status_code: int, reason: Reason) -> None:
        self.status_code = status_code
        self.reason = reason


class ActionService:
    def __init__(
        self,
        store: Store,
        policy: Policy,
        registry: DocumentRegistry,
        executor: DocumentExecutor,
        audit_key: bytes,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if len(audit_key) < 32:
            raise ValueError("Audit HMAC key requires at least 32 bytes")
        self.store = store
        self.policy = policy
        self.registry = registry
        self.executor = executor
        self.audit_key = audit_key
        self.clock = clock

    @staticmethod
    def new_context() -> Context:
        return Context(action_id=f"act-{uuid.uuid4().hex}", trace_id=f"trace-{uuid.uuid4().hex}")

    def authenticate(self, context: Context, token: str | None) -> None:
        if token is None:
            raise GateError(401, Reason.AUTHENTICATION_REQUIRED)
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            raise GateError(401, Reason.INVALID_CREDENTIAL)
        digest = credential_digest(token)
        try:
            context.identity = self.store.resolve(digest, self.clock())
            context.credential_digest = digest
        except CredentialInvalid as error:
            raise GateError(401, Reason.INVALID_CREDENTIAL) from error

    def digest_payload(self, context: Context, payload: bytes) -> None:
        context.payload_digest = hmac.new(
            self.audit_key, b"action-v1:" + payload, hashlib.sha256
        ).hexdigest()

    def event(
        self,
        context: Context,
        event_type: Literal[
            "action_denied",
            "dispatch_intent",
            "action_completed",
            "output_blocked",
            "execution_failed",
        ],
        reason: Reason,
        decision: Literal["allow", "redact", "deny"],
    ) -> AuditEvent:
        identity = context.identity
        return AuditEvent(
            event_id=f"evt-{uuid.uuid4().hex}",
            event_type=event_type,
            timestamp=self.clock(),
            action_id=context.action_id,
            trace_id=context.trace_id,
            principal_id=identity.principal_id if identity else None,
            tenant_id=identity.tenant_id if identity else None,
            root_run_id=identity.root_run_id if identity else None,
            operation=context.operation,
            decision=decision,
            reason_codes=(reason,),
            policy_version=self.policy.version,
            payload_digest=context.payload_digest,
            executed=context.executed,
            semantic_status=(
                "unavailable"
                if reason == Reason.REQUIRED_SEMANTIC_UNAVAILABLE
                else "not_run_hard_denial"
                if decision == "deny"
                else "not_configured"
            ),
        )

    def reject(self, context: Context, error: GateError) -> tuple[int, ActionResponse]:
        event_type: Literal["action_denied", "output_blocked", "execution_failed"] = "action_denied"
        if context.executed:
            event_type = (
                "execution_failed" if error.reason == Reason.EXECUTION_FAILED else "output_blocked"
            )
        try:
            self.store.append(self.event(context, event_type, error.reason, "deny"))
        except StorageUnavailable:
            error = GateError(503, Reason.AUDIT_UNAVAILABLE)
        return error.status_code, ActionResponse(
            status="error" if error.status_code >= 500 else "denied",
            action_id=context.action_id,
            trace_id=context.trace_id,
            decision="deny",
            reason_codes=(error.reason,),
            policy_version=self.policy.version,
            executed=context.executed,
        )

    def execute(self, context: Context, request: ActionRequest) -> ActionResponse:
        identity = context.identity
        digest = context.credential_digest
        if identity is None or digest is None:
            raise GateError(401, Reason.AUTHENTICATION_REQUIRED)
        if request.operation != "documents.read":
            raise GateError(403, Reason.UNKNOWN_OPERATION)
        context.operation = "documents.read"
        try:
            arguments = DocumentArguments.model_validate(request.arguments)
        except ValidationError as error:
            raise GateError(422, Reason.MALFORMED_REQUEST) from error
        metadata = self.registry.lookup(arguments.document_id)
        denial = self.policy.authorize(identity, metadata)
        if denial is not None:
            raise GateError(403, denial)
        if self.policy.semantic_required:
            raise GateError(503, Reason.REQUIRED_SEMANTIC_UNAVAILABLE)
        try:
            self.store.dispatch_intent(
                digest,
                identity,
                self.event(context, "dispatch_intent", Reason.ALLOWED, "allow"),
                self.clock,
                self.policy.tool_budgets,
            )
        except CredentialInvalid as error:
            raise GateError(401, Reason.INVALID_CREDENTIAL) from error
        except BudgetExceeded as error:
            raise GateError(429, Reason.BUDGET_EXCEEDED) from error

        context.executed = True
        try:
            content = self.executor.read(arguments.document_id, identity.tenant_id)
        except Exception as error:
            # Executor exception text may contain document contents or credentials.
            raise GateError(503, Reason.EXECUTION_FAILED) from error
        if not isinstance(content, str):
            raise GateError(503, Reason.OUTPUT_INVALID)
        try:
            size = len(content.encode("utf-8"))
        except UnicodeError as error:
            raise GateError(503, Reason.OUTPUT_INVALID) from error
        if size > self.policy.output.max_result_bytes:
            raise GateError(403, Reason.OUTPUT_TOO_LARGE)
        if SYNTHETIC_SECRET.search(content):
            raise GateError(403, Reason.SECRET_IN_OUTPUT)
        released = (
            EMAIL.sub("[REDACTED_EMAIL]", content) if self.policy.output.redact_emails else content
        )
        decision: Literal["allow", "redact"] = "redact" if released != content else "allow"
        reason = Reason.EMAIL_REDACTED if decision == "redact" else Reason.ALLOWED
        result = {"document_id": arguments.document_id, "content": released}
        if (
            len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            > self.policy.output.max_result_bytes
        ):
            raise GateError(403, Reason.OUTPUT_TOO_LARGE)
        self.store.append(self.event(context, "action_completed", reason, decision))
        return ActionResponse(
            status="completed",
            action_id=context.action_id,
            trace_id=context.trace_id,
            decision=decision,
            reason_codes=(reason,),
            policy_version=self.policy.version,
            executed=True,
            result=result,
        )
