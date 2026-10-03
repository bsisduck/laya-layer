"""Document enforcement independent of HTTP, agent frameworks, and inference imports."""

import hashlib
import hmac
import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
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
    SemanticResult,
)
from agentgate.control_plane import (
    ControlPlane,
    ControlsChanged,
    ControlSnapshot,
    ThreatBlocked,
    ThreatFeed,
)
from agentgate.documents import DocumentExecutor, DocumentRegistry
from agentgate.policy import Policy
from agentgate.semantics import (
    SemanticBudgetExceeded,
    SemanticEvaluator,
    SemanticInvalid,
    SemanticUnavailable,
)
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
    operation: Literal["documents.read", "chat.completions"] | None = None
    executed: bool = False
    semantic: SemanticResult | None = None
    controls: ControlSnapshot | None = None
    semantic_failure: Literal["unavailable", "invalid_output"] | None = None


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
        semantic: SemanticEvaluator | None = None,
        controls: ControlPlane | None = None,
    ) -> None:
        if len(audit_key) < 32:
            raise ValueError("Audit HMAC key requires at least 32 bytes")
        self.store = store
        self._policy = policy
        self.controls = controls
        self.registry = registry
        self.executor = executor
        self.audit_key = audit_key
        self.clock = clock
        self.semantic = semantic

    @property
    def policy(self) -> Policy:
        return self.current_controls().policy

    @policy.setter
    def policy(self, policy: Policy) -> None:
        if self.controls is not None:
            raise ValueError("Use compare-and-swap activation for live controls")
        self._policy = policy

    def current_controls(self) -> ControlSnapshot:
        return (
            self.controls.snapshot()
            if self.controls is not None
            else ControlSnapshot(self._policy, ThreatFeed())
        )

    def context_controls(self, context: Context) -> ControlSnapshot:
        if context.controls is None:
            context.controls = self.current_controls()
        return context.controls

    def semantic_ready(self, policy: Policy | None = None) -> bool:
        policy = policy if policy is not None else self.policy
        return not policy.semantic_required or (self.semantic is not None and self.semantic.ready())

    @staticmethod
    def new_context() -> Context:
        return Context(action_id=f"act-{uuid.uuid4().hex}", trace_id=f"trace-{uuid.uuid4().hex}")

    def authenticate(self, context: Context, token: str | None) -> None:
        self.context_controls(context)
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
            policy_version=self.context_controls(context).policy.version,
            payload_digest=context.payload_digest,
            executed=context.executed,
            semantic_status=(
                context.semantic.status
                if context.semantic is not None
                else context.semantic_failure
                if context.semantic_failure is not None
                else "unavailable"
                if reason == Reason.REQUIRED_SEMANTIC_UNAVAILABLE
                else "not_run_hard_denial"
                if decision == "deny"
                else "not_configured"
            ),
            semantic=context.semantic,
            feed_version=self.context_controls(context).feed.version,
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
            policy_version=(context.controls.policy.version if context.controls else "unavailable"),
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
        # Re-evaluate if controls change before durable intent. The transaction
        # callback closes the cross-process check/dispatch race, not just a lock
        # on this Python service. Updates after intent apply to the next action.
        for attempt in range(3):
            snapshot = self.current_controls()
            context.controls = snapshot
            policy = snapshot.policy
            metadata = self.registry.lookup(arguments.document_id)
            denial = policy.authorize(identity, metadata)
            if denial is not None:
                raise GateError(403, denial)
            try:
                snapshot.inspect("tool_action", request.model_dump_json())
            except ThreatBlocked as error:
                raise GateError(403, Reason.THREAT_FEED_BLOCKED) from error
            except ValueError as error:
                raise GateError(422, Reason.MALFORMED_REQUEST) from error
            if not self.semantic_ready(policy):
                raise GateError(503, Reason.REQUIRED_SEMANTIC_UNAVAILABLE)
            try:
                before_dispatch = (
                    partial(ControlPlane.assert_current, snapshot=snapshot)
                    if self.controls is not None
                    else None
                )
                self.store.dispatch_intent(
                    digest,
                    identity,
                    self.event(context, "dispatch_intent", Reason.ALLOWED, "allow"),
                    self.clock,
                    policy.tool_budgets,
                    before_dispatch,
                )
                break
            except ControlsChanged as error:
                if attempt == 2:
                    raise GateError(409, Reason.CONTROLS_CHANGED) from error
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
        if size > policy.output.max_result_bytes:
            raise GateError(403, Reason.OUTPUT_TOO_LARGE)
        try:
            snapshot.inspect("tool_result", content)
        except ThreatBlocked as error:
            raise GateError(403, Reason.THREAT_FEED_BLOCKED) from error
        except ValueError as error:
            raise GateError(503, Reason.OUTPUT_INVALID) from error
        if SYNTHETIC_SECRET.search(content):
            raise GateError(403, Reason.SECRET_IN_OUTPUT)
        if policy.semantic_required:
            assert self.semantic is not None
            try:
                context.semantic = self.semantic.evaluate(context.action_id, content)
            except SemanticBudgetExceeded as error:
                context.semantic_failure = "unavailable"
                raise GateError(429, Reason.SEMANTIC_BUDGET_EXCEEDED) from error
            except SemanticUnavailable as error:
                context.semantic_failure = "unavailable"
                raise GateError(503, Reason.REQUIRED_SEMANTIC_UNAVAILABLE) from error
            except SemanticInvalid as error:
                context.semantic_failure = "invalid_output"
                raise GateError(503, Reason.SEMANTIC_INVALID) from error
            semantic = context.semantic
            if semantic.status in ("incomplete", "invalid_output", "unavailable"):
                reason = {
                    "incomplete": Reason.SEMANTIC_INCOMPLETE,
                    "invalid_output": Reason.SEMANTIC_INVALID,
                    "unavailable": Reason.REQUIRED_SEMANTIC_UNAVAILABLE,
                }[semantic.status]
                raise GateError(503, reason)
            if policy.semantic_mode == "enforce":
                if semantic.status == "abstain":
                    raise GateError(403, Reason.SEMANTIC_ABSTAIN)
                if semantic.selected_labels["content_role"] == "behavior_instruction":
                    raise GateError(403, Reason.SEMANTIC_BLOCKED)
        released = (
            EMAIL.sub("[REDACTED_EMAIL]", content) if policy.output.redact_emails else content
        )
        decision: Literal["allow", "redact"] = "redact" if released != content else "allow"
        reason = Reason.EMAIL_REDACTED if decision == "redact" else Reason.ALLOWED
        result = {"document_id": arguments.document_id, "content": released}
        if (
            len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            > policy.output.max_result_bytes
        ):
            raise GateError(403, Reason.OUTPUT_TOO_LARGE)
        self.store.append(self.event(context, "action_completed", reason, decision))
        return ActionResponse(
            status="completed",
            action_id=context.action_id,
            trace_id=context.trace_id,
            decision=decision,
            reason_codes=(reason,),
            policy_version=self.context_controls(context).policy.version,
            executed=True,
            result=result,
        )
