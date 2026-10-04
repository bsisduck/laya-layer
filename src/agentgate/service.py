"""Document enforcement independent of HTTP, agent frameworks, and inference imports."""

import hashlib
import hmac
import json
import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Literal

from pydantic import JsonValue, ValidationError

from agentgate.authority import EffectiveAuthority
from agentgate.authority import resolve as resolve_authority
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
from agentgate.tool_catalog import disposition

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}\b")
SYNTHETIC_SECRET = re.compile(r"AGENTGATE_SECRET\[")


@dataclass
class Context:
    action_id: str
    trace_id: str
    identity: Identity | None = None
    credential_digest: str | None = None
    payload_digest: str | None = None
    operation: Literal["documents.read", "memory.query", "mail.send", "chat.completions"] | None = (
        None
    )
    policy: Policy | None = None
    executed: bool = False
    semantic: SemanticResult | None = None
    controls: ControlSnapshot | None = None
    authority_resource: str = ""
    authority: EffectiveAuthority | None = None
    approval_actor: dict[str, JsonValue] | None = None
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
        from agentgate.scoped_tools import ScopedTools

        self.tools = ScopedTools(self)

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
            with self.store.connection() as db:
                context.authority = resolve_authority(
                    db,
                    digest,
                    context.identity,
                    self.context_controls(context).policy,
                    self.clock(),
                )
        except CredentialInvalid as error:
            raise GateError(401, Reason.INVALID_CREDENTIAL) from error

    def resolve_authority(
        self, context: Context, policy: Policy, db: sqlite3.Connection | None = None
    ) -> EffectiveAuthority:
        assert context.identity is not None and context.credential_digest is not None
        try:
            if db is None:
                with self.store.connection() as connection:
                    authority = resolve_authority(
                        connection,
                        context.credential_digest,
                        context.identity,
                        policy,
                        self.clock(),
                    )
            else:
                authority = resolve_authority(
                    db, context.credential_digest, context.identity, policy, self.clock()
                )
        except CredentialInvalid as error:
            raise GateError(401, Reason.INVALID_CREDENTIAL) from error
        context.authority = authority
        return authority

    def authorize_authority(
        self,
        context: Context,
        policy: Policy,
        operation: str,
        resource: str | None = None,
        classification: str | None = None,
        *,
        db: sqlite3.Connection | None = None,
    ) -> None:
        authority = self.resolve_authority(context, policy, db)
        if not authority.allows(operation, resource, classification):
            raise GateError(
                403,
                Reason.RESOURCE_NOT_ALLOWED
                if operation in ("documents.read", "memory.query")
                else Reason.MODEL_NOT_ALLOWED
                if operation == "chat.completions"
                else Reason.OPERATION_NOT_ALLOWED,
            )

    def check_dispatch_authority(
        self,
        db: sqlite3.Connection,
        *,
        context: Context,
        snapshot: ControlSnapshot,
        operation: str,
        resource: str | None = None,
        classification: str | None = None,
    ) -> None:
        if self.controls is not None:
            snapshot.assert_current(db)
        elif self.policy != snapshot.policy:
            raise ControlsChanged
        if operation == "documents.read" and disposition(operation) != "automatic_read":
            raise GateError(403, Reason.OPERATION_NOT_ALLOWED)
        self.authorize_authority(
            context, snapshot.policy, operation, resource, classification, db=db
        )

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
            "action_pending",
            "approval_decided",
        ],
        reason: Reason,
        decision: Literal["allow", "redact", "deny", "require_approval"],
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
                context.semantic_failure
                if context.semantic_failure is not None
                else context.semantic.status
                if context.semantic is not None
                else "unavailable"
                if reason == Reason.REQUIRED_SEMANTIC_UNAVAILABLE
                else "not_run_hard_denial"
                if decision == "deny"
                else "not_configured"
            ),
            # A successful input result is retained on dispatch_intent; it must
            # not masquerade as a result for a failed output classification.
            semantic=context.semantic if context.semantic_failure is None else None,
            feed_version=self.context_controls(context).feed.version,
            authority=context.authority.attribution.model_dump(mode="json")
            if context.authority and context.authority.attribution
            else None,
            approval_actor=context.approval_actor,
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
        from agentgate.scoped_contracts import ALIASES

        operation = ALIASES.get(request.operation)
        if operation in ("memory.query", "mail.send"):
            return self.tools.execute(context, request.model_copy(update={"operation": operation}))
        if operation != "documents.read":
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
            if disposition(operation) != "automatic_read":
                raise GateError(403, Reason.OPERATION_NOT_ALLOWED)
            self.authorize_authority(
                context,
                policy,
                "documents.read",
                arguments.document_id,
                metadata.classification if metadata else None,
            )
            try:
                snapshot.inspect("tool_action", request.model_dump_json())
            except ThreatBlocked as error:
                raise GateError(403, Reason.THREAT_FEED_BLOCKED) from error
            except ValueError as error:
                raise GateError(422, Reason.MALFORMED_REQUEST) from error
            if not self.semantic_ready(policy):
                raise GateError(503, Reason.REQUIRED_SEMANTIC_UNAVAILABLE)
            try:
                before_dispatch = partial(
                    self.check_dispatch_authority,
                    context=context,
                    snapshot=snapshot,
                    operation="documents.read",
                    resource=arguments.document_id,
                    classification=metadata.classification if metadata else None,
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
        released = self.inspect_text(context, content)
        decision: Literal["allow", "redact"] = "redact" if released != content else "allow"
        reason = Reason.EMAIL_REDACTED if decision == "redact" else Reason.ALLOWED
        result: dict[str, JsonValue] = {"document_id": arguments.document_id, "content": released}
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

    def inspect_text(self, context: Context, content: object, *, input_text: bool = False) -> str:
        snapshot = self.context_controls(context)
        policy = snapshot.policy
        if not isinstance(content, str):
            raise GateError(503, Reason.OUTPUT_INVALID)
        try:
            size = len(content.encode("utf-8"))
        except UnicodeError as error:
            raise GateError(503, Reason.OUTPUT_INVALID) from error
        if size > policy.output.max_result_bytes:
            raise GateError(403, Reason.OUTPUT_TOO_LARGE)
        try:
            snapshot.inspect("tool_action" if input_text else "tool_result", content)
        except ThreatBlocked as error:
            raise GateError(403, Reason.THREAT_FEED_BLOCKED) from error
        except ValueError as error:
            raise GateError(503, Reason.OUTPUT_INVALID) from error
        if SYNTHETIC_SECRET.search(content):
            raise GateError(403, Reason.SECRET_IN_INPUT if input_text else Reason.SECRET_IN_OUTPUT)
        if policy.semantic_required:
            if self.semantic is None or not self.semantic.ready():
                raise GateError(503, Reason.REQUIRED_SEMANTIC_UNAVAILABLE)
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
        return (
            EMAIL.sub("[REDACTED_EMAIL]", content)
            if policy.output.redact_emails and not input_text
            else content
        )
