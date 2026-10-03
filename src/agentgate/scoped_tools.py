"""Shared REST/MCP authority for scoped reads and exact local-outbox approvals.

The outbox IS the fixture effect, not a queue to a real SMTP provider. Its insert,
intent, outcome, budget settlement and approval consumption share one transaction.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, cast

from pydantic import JsonValue, ValidationError

from agentgate import budgets
from agentgate.contracts import ActionRequest, ActionResponse, Identity, Reason
from agentgate.policy import Policy
from agentgate.scoped_contracts import ALIASES, REGISTRY_DIGEST, MailArguments, MemoryArguments
from agentgate.storage import CredentialInvalid

if TYPE_CHECKING:
    from agentgate.service import ActionService, Context


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


ToolStage = Literal["tool_action", "tool_result"]


class LiveControlSnapshot(Protocol):
    @property
    def policy(self) -> Policy: ...

    @property
    def generation(self) -> int: ...

    def inspect(self, stage: ToolStage, text: str) -> None: ...

    def assert_current(self, connection: sqlite3.Connection) -> None: ...


@dataclass(frozen=True)
class ToolSnapshot:
    """Integration seam: callbacks must reject changed or blocked live controls."""

    policy: Policy
    binding: str
    inspect: Callable[[ToolStage, str], None]
    assert_current: Callable[[sqlite3.Connection], None]


class ScopedTools:
    def __init__(self, service: ActionService) -> None:
        self.service = service
        self.snapshot_provider: Callable[[], ToolSnapshot] | None = None

    def snapshot(self, context: Context | None = None) -> ToolSnapshot:
        from agentgate.service import GateError

        if self.snapshot_provider is not None:
            return self.snapshot_provider()
        # PR17 exposes these methods. Structural binding keeps that dependency
        # additive without copying its control-plane implementation into this PR.
        current = getattr(self.service, "current_controls", None)
        capture = getattr(self.service, "context_controls", None)
        live = getattr(self.service, "controls", None) is not None
        if callable(current) and callable(capture):
            snapshot = cast(LiveControlSnapshot, capture(context) if context else current())

            def inspect(stage: ToolStage, text: str) -> None:
                try:
                    snapshot.inspect(stage, text)
                except ValueError as error:
                    raise GateError(422, Reason.MALFORMED_REQUEST) from error
                except Exception as error:
                    raise GateError(403, Reason.THREAT_FEED_BLOCKED) from error

            def check(connection: sqlite3.Connection) -> None:
                try:
                    if live:
                        # ControlSnapshot.assert_current delegates to
                        # ControlPlane.assert_current(db, snapshot).
                        snapshot.assert_current(connection)
                    elif self.service.policy != snapshot.policy:
                        raise GateError(409, Reason.POLICY_CHANGED)
                except Exception as error:
                    raise GateError(409, Reason.POLICY_CHANGED) from error

            return ToolSnapshot(snapshot.policy, str(snapshot.generation), inspect, check)
        if live:
            raise GateError(503, Reason.POLICY_CHANGED)
        policy = self.service.policy

        def assert_current(connection: sqlite3.Connection) -> None:
            if self.service.policy != policy:
                raise GateError(409, Reason.POLICY_CHANGED)

        return ToolSnapshot(policy, "static", lambda stage, text: None, assert_current)

    @staticmethod
    def policy_digest(snapshot: ToolSnapshot) -> str:
        return hashlib.sha256(
            canonical(
                {
                    "policy": snapshot.policy.model_dump(mode="json"),
                    "controls": snapshot.binding,
                }
            ).encode()
        ).hexdigest()

    @staticmethod
    def allowed(identity: Identity, policy: Policy, operation: str) -> bool:
        roles = {
            "documents.read": policy.documents_read.roles,
            "memory.query": policy.scoped_tools.memory_roles,
            "mail.send": policy.scoped_tools.mail_roles,
        }.get(operation, ())
        return operation in identity.operations and bool(set(identity.roles).intersection(roles))

    def discover(self, context: Context) -> list[str]:
        from agentgate.service import GateError

        if context.identity is None:
            raise GateError(401, Reason.AUTHENTICATION_REQUIRED)
        policy = self.snapshot(context).policy
        return [
            op
            for op in ("documents.read", "memory.query", "mail.send")
            if self.allowed(context.identity, policy, op)
        ]

    def execute(self, context: Context, request: ActionRequest) -> ActionResponse:
        from agentgate.service import GateError

        snapshot = self.snapshot(context)
        context.policy = snapshot.policy
        identity = context.identity
        if identity is None or context.credential_digest is None:
            raise GateError(401, Reason.AUTHENTICATION_REQUIRED)
        operation = ALIASES.get(request.operation)
        if operation not in ("memory.query", "mail.send"):
            raise GateError(403, Reason.UNKNOWN_OPERATION)
        context.operation = "memory.query" if operation == "memory.query" else "mail.send"
        if not self.allowed(identity, snapshot.policy, operation):
            raise GateError(403, Reason.OPERATION_NOT_ALLOWED)
        try:
            if operation == "memory.query":
                return self.query(
                    context, MemoryArguments.model_validate(request.arguments), snapshot
                )
            arguments = MailArguments.model_validate(request.arguments)
        except ValidationError as error:
            raise GateError(422, Reason.MALFORMED_REQUEST) from error
        payload = canonical(arguments.model_dump(mode="json"))
        self.service.digest_payload(context, payload.encode())
        with self.service.store.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.revalidate(connection, context, snapshot)
            row = connection.execute(
                "SELECT * FROM tool_actions WHERE tenant_id=? AND principal_id=? "
                "AND root_run_id=? AND idempotency_key=?",
                (
                    identity.tenant_id,
                    identity.principal_id,
                    identity.root_run_id,
                    arguments.idempotency_key,
                ),
            ).fetchone()
            if row is not None:
                if row["payload"] != payload:
                    raise GateError(409, Reason.IDEMPOTENCY_CONFLICT)
                return self.resume_row(connection, context, row, snapshot)
            self.check_mail(context, arguments, snapshot)
            expires = self.service.clock() + snapshot.policy.scoped_tools.approval_ttl_seconds
            fingerprint = self.fingerprint(context, snapshot, expires)
            connection.execute(
                "INSERT INTO tool_actions (action_id,tenant_id,principal_id,root_run_id,"
                "idempotency_key,identity,credential_digest,payload,payload_digest,policy_digest,"
                "registry_digest,fingerprint,policy_version,expires_at,created_at,state,reason) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)",
                (
                    context.action_id,
                    identity.tenant_id,
                    identity.principal_id,
                    identity.root_run_id,
                    arguments.idempotency_key,
                    identity.model_dump_json(),
                    context.credential_digest,
                    payload,
                    context.payload_digest,
                    self.policy_digest(snapshot),
                    REGISTRY_DIGEST,
                    fingerprint,
                    snapshot.policy.version,
                    expires,
                    self.service.clock(),
                    Reason.REQUIRES_APPROVAL.value,
                ),
            )
            self.service.store._append(
                connection,
                self.service.event(
                    context, "action_pending", Reason.REQUIRES_APPROVAL, "require_approval"
                ),
            )
            row = connection.execute(
                "SELECT * FROM tool_actions WHERE action_id=?", (context.action_id,)
            ).fetchone()
            connection.execute("COMMIT")
            return self.response(context, row)

    def fingerprint(self, context: Context, snapshot: ToolSnapshot, expires: float) -> str:
        assert context.identity is not None
        return hmac.new(
            self.service.audit_key,
            canonical(
                {
                    "identity": context.identity.model_dump(mode="json"),
                    "credential": context.credential_digest,
                    "operation": "mail.send",
                    "payload": context.payload_digest,
                    "policy": self.policy_digest(snapshot),
                    "registry": REGISTRY_DIGEST,
                    "expires": expires,
                }
            ).encode(),
            hashlib.sha256,
        ).hexdigest()

    def revalidate(
        self, connection: sqlite3.Connection, context: Context, snapshot: ToolSnapshot
    ) -> None:
        from agentgate.service import GateError

        assert context.credential_digest is not None
        try:
            if (
                self.service.store._resolve(
                    connection, context.credential_digest, self.service.clock()
                )
                != context.identity
            ):
                raise CredentialInvalid
        except CredentialInvalid as error:
            raise GateError(401, Reason.INVALID_CREDENTIAL) from error
        snapshot.assert_current(connection)

    def check_mail(
        self, context: Context, arguments: MailArguments, snapshot: ToolSnapshot
    ) -> None:
        from agentgate.service import GateError

        assert context.identity is not None
        if not self.allowed(context.identity, snapshot.policy, "mail.send"):
            raise GateError(403, Reason.OPERATION_NOT_ALLOWED)
        if arguments.recipient.rsplit("@", 1)[1] not in snapshot.policy.scoped_tools.mail_domains:
            raise GateError(403, Reason.RECIPIENT_DOMAIN_NOT_ALLOWED)
        text = canonical(arguments.model_dump(mode="json"))
        snapshot.inspect("tool_action", text)
        self.service.inspect_text(context, text, input_text=True)

    def query(
        self, context: Context, arguments: MemoryArguments, snapshot: ToolSnapshot
    ) -> ActionResponse:
        from agentgate.service import GateError

        assert context.identity is not None
        self.service.digest_payload(context, canonical(arguments.model_dump(mode="json")).encode())
        snapshot.inspect("tool_action", arguments.query)
        self.service.inspect_text(context, arguments.query, input_text=True)
        with self.service.store.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.revalidate(connection, context, snapshot)
            self.reserve(connection, context, snapshot)
            connection.execute("COMMIT")
        context.executed = True
        classifications = snapshot.policy.scoped_tools.memory_classifications
        with self.service.store.connection() as connection:
            rows = connection.execute(
                "SELECT entry_id,content FROM memory_entries WHERE tenant_id=? "
                "AND classification IN (SELECT value FROM json_each(?)) "
                "AND instr(lower(content),lower(?))>0 ORDER BY entry_id LIMIT ?",
                (
                    context.identity.tenant_id,
                    json.dumps(classifications),
                    arguments.query,
                    arguments.limit,
                ),
            ).fetchall()
        records: list[JsonValue] = []
        redacted = False
        for row in rows:
            snapshot.inspect("tool_result", row["content"])
            content = self.service.inspect_text(context, row["content"])
            redacted |= content != row["content"]
            records.append({"entry_id": row["entry_id"], "content": content})
        result: dict[str, JsonValue] = {"entries": records}
        if len(canonical(result).encode()) > snapshot.policy.output.max_result_bytes:
            raise GateError(403, Reason.OUTPUT_TOO_LARGE)
        reason = Reason.EMAIL_REDACTED if redacted else Reason.ALLOWED
        self.service.store.append(
            self.service.event(
                context, "action_completed", reason, "redact" if redacted else "allow"
            )
        )
        return ActionResponse(
            status="completed",
            action_id=context.action_id,
            trace_id=context.trace_id,
            decision="redact" if redacted else "allow",
            reason_codes=(reason,),
            policy_version=snapshot.policy.version,
            executed=True,
            result=result,
        )

    def reserve(
        self, connection: sqlite3.Connection, context: Context, snapshot: ToolSnapshot
    ) -> None:
        from agentgate.service import GateError

        assert context.identity is not None
        try:
            if snapshot.policy.tool_budgets is not None:
                budgets.reserve(
                    connection,
                    context.action_id,
                    context.identity,
                    snapshot.policy.tool_budgets,
                    self.service.clock(),
                    snapshot.policy.version,
                )
        except budgets.BudgetExceeded as error:
            raise GateError(429, Reason.BUDGET_EXCEEDED) from error
        self.service.store._append(
            connection, self.service.event(context, "dispatch_intent", Reason.ALLOWED, "allow")
        )

    @staticmethod
    def owned(connection: sqlite3.Connection, context: Context, action_id: str) -> sqlite3.Row:
        from agentgate.service import GateError

        assert context.identity is not None
        identity = context.identity
        row = connection.execute(
            "SELECT * FROM tool_actions WHERE action_id=? AND tenant_id=? AND principal_id=? AND root_run_id=?",
            (action_id, identity.tenant_id, identity.principal_id, identity.root_run_id),
        ).fetchone()
        if row is None:
            raise GateError(404, Reason.ACTION_NOT_FOUND)
        if (
            row["identity"] != identity.model_dump_json()
            or row["credential_digest"] != context.credential_digest
        ):
            raise GateError(403, Reason.APPROVAL_MISMATCH)
        return cast(sqlite3.Row, row)

    def retrieve(self, context: Context, action_id: str, *, resume: bool = False) -> ActionResponse:
        snapshot = self.snapshot(context)
        context.policy = snapshot.policy
        with self.service.store.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.revalidate(connection, context, snapshot)
            row = self.owned(connection, context, action_id)
            if resume:
                return self.resume_row(connection, context, row, snapshot)
            row = self.refresh(connection, context, row, snapshot)
            connection.execute("COMMIT")
            return self.response(context, row)

    def refresh(
        self,
        connection: sqlite3.Connection,
        context: Context,
        row: sqlite3.Row,
        snapshot: ToolSnapshot,
    ) -> sqlite3.Row:
        """Terminal states never become executable again; expire/invalidate active ones."""
        context.action_id = row["action_id"]
        context.operation = "mail.send"
        self.service.digest_payload(context, row["payload"].encode())
        if row["state"] in ("pending", "approved"):
            reason = None
            state = "denied"
            if not hmac.compare_digest(context.payload_digest or "", row["payload_digest"]):
                reason = Reason.APPROVAL_MISMATCH
            elif self.service.clock() >= row["expires_at"]:
                reason, state = Reason.APPROVAL_EXPIRED, "expired"
            elif (
                row["policy_digest"] != self.policy_digest(snapshot)
                or row["registry_digest"] != REGISTRY_DIGEST
            ):
                reason = Reason.POLICY_CHANGED
            elif not hmac.compare_digest(
                row["fingerprint"], self.fingerprint(context, snapshot, row["expires_at"])
            ):
                reason = Reason.APPROVAL_MISMATCH
            if reason is not None:
                connection.execute(
                    "UPDATE tool_actions SET state=?,reason=? WHERE action_id=?",
                    (state, reason.value, row["action_id"]),
                )
                self.service.store._append(
                    connection, self.service.event(context, "action_denied", reason, "deny")
                )
        return cast(
            sqlite3.Row,
            connection.execute(
                "SELECT * FROM tool_actions WHERE action_id=?", (row["action_id"],)
            ).fetchone(),
        )

    def resume_row(
        self,
        connection: sqlite3.Connection,
        context: Context,
        row: sqlite3.Row,
        snapshot: ToolSnapshot,
    ) -> ActionResponse:
        # Repeated execute also passes this ownership check; another credential
        # cannot consume a remembered key, even with identical identity claims.
        self.owned(connection, context, row["action_id"])
        row = self.refresh(connection, context, row, snapshot)
        if row["state"] == "approved":
            arguments = MailArguments.model_validate_json(row["payload"])
            self.check_mail(context, arguments, snapshot)
            self.revalidate(connection, context, snapshot)
            row = self.refresh(connection, context, row, snapshot)
            if row["state"] != "approved":
                connection.execute("COMMIT")
                return self.response(context, row)
            self.reserve(connection, context, snapshot)
            connection.execute(
                "INSERT INTO tool_outbox(action_id,tenant_id,recipient,subject,body,created_at) VALUES(?,?,?,?,?,?)",
                (
                    row["action_id"],
                    row["tenant_id"],
                    arguments.recipient,
                    arguments.subject,
                    arguments.body,
                    self.service.clock(),
                ),
            )
            # The fixture acknowledgement contains no mail content to release.
            snapshot.inspect("tool_result", "Message saved to local test outbox")
            self.service.inspect_text(context, "Message saved to local test outbox")
            budgets.settle(connection, context.action_id, uncertain=False)
            connection.execute(
                "UPDATE tool_actions SET state='consumed',reason=? WHERE action_id=?",
                (Reason.ALLOWED.value, row["action_id"]),
            )
            event = self.service.event(context, "action_completed", Reason.ALLOWED, "allow")
            self.service.store._append(connection, event.model_copy(update={"executed": True}))
            row = connection.execute(
                "SELECT * FROM tool_actions WHERE action_id=?", (row["action_id"],)
            ).fetchone()
        connection.execute("COMMIT")
        context.executed = row["state"] == "consumed"
        return self.response(context, row)

    @staticmethod
    def response(context: Context, row: sqlite3.Row) -> ActionResponse:
        state = row["state"]
        return ActionResponse.model_validate(
            {
                "status": {
                    "pending": "pending_approval",
                    "approved": "approved",
                    "denied": "denied",
                    "expired": "expired",
                    "consumed": "completed",
                }[state],
                "action_id": row["action_id"],
                "trace_id": context.trace_id,
                "decision": "allow"
                if state == "consumed"
                else "require_approval"
                if state in ("pending", "approved")
                else "deny",
                "reason_codes": (Reason(row["reason"]),),
                "policy_version": row["policy_version"],
                "executed": state == "consumed",
                "approval_id": row["action_id"],
                "action_state": state,
                "expires_at": row["expires_at"],
                "result": {"outbox_id": row["action_id"], "delivery_state": "fixture"}
                if state == "consumed"
                else None,
            }
        )

    def list_approvals(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, JsonValue]]:
        """Trusted operator hook; caller must authorize this tenant and sensitive view."""
        self.check_limit(limit)
        with self.service.store.connection() as connection:
            rows = connection.execute(
                "SELECT action_id,principal_id,root_run_id,payload,fingerprint,policy_version,"
                "expires_at,state,reason,decided_by FROM tool_actions WHERE tenant_id=? ORDER BY created_at DESC,action_id LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        result = []
        for row in rows:
            entry = dict(row)
            entry["payload"] = json.loads(entry["payload"])
            if (
                entry["state"] in ("pending", "approved")
                and self.service.clock() >= entry["expires_at"]
            ):
                entry["state"] = "expired"
                entry["reason"] = Reason.APPROVAL_EXPIRED.value
            result.append(entry)
        return result

    def decide(
        self, *, tenant_id: str, action_id: str, fingerprint: str, approve: bool, actor: str
    ) -> ActionResponse:
        """Trusted operator hook, never registered as an agent operation or MCP tool."""
        from agentgate.service import GateError

        if not actor or len(actor) > 96 or not isinstance(approve, bool):
            raise ValueError("Invalid operator decision")
        context = self.service.new_context()
        snapshot = self.snapshot(context)
        context.policy = snapshot.policy
        with self.service.store.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM tool_actions WHERE action_id=? AND tenant_id=?",
                (action_id, tenant_id),
            ).fetchone()
            if row is None:
                raise GateError(404, Reason.ACTION_NOT_FOUND)
            if not hmac.compare_digest(fingerprint, row["fingerprint"]):
                raise GateError(409, Reason.APPROVAL_MISMATCH)
            context.identity = Identity.model_validate_json(row["identity"])
            context.credential_digest = row["credential_digest"]
            row = self.refresh(connection, context, row, snapshot)
            if row["state"] != "pending":
                connection.execute("COMMIT")
                return self.response(context, row)
            try:
                self.revalidate(connection, context, snapshot)
                self.check_mail(
                    context, MailArguments.model_validate_json(row["payload"]), snapshot
                )
            except GateError:
                approve = False
            state: Literal["approved", "denied"] = "approved" if approve else "denied"
            reason = Reason.APPROVAL_APPROVED if approve else Reason.APPROVAL_DENIED
            connection.execute(
                "UPDATE tool_actions SET state=?,reason=?,decided_by=? WHERE action_id=?",
                (state, reason.value, actor, action_id),
            )
            self.service.store._append(
                connection,
                self.service.event(
                    context, "approval_decided", reason, "require_approval" if approve else "deny"
                ),
            )
            row = connection.execute(
                "SELECT * FROM tool_actions WHERE action_id=?", (action_id,)
            ).fetchone()
            connection.execute("COMMIT")
            return self.response(context, row)

    def outbox(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, JsonValue]]:
        """Trusted operator hook: bounded metadata; mail content stays in private state."""
        self.check_limit(limit)
        with self.service.store.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT action_id,recipient,created_at,delivery_state FROM tool_outbox "
                    "WHERE tenant_id=? ORDER BY created_at DESC,action_id LIMIT ?",
                    (tenant_id, limit),
                )
            ]

    @staticmethod
    def check_limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
