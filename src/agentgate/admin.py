"""Separate operator authority, bounded admin APIs, and private bootstrap.

Attach to an existing FastAPI app; no frontend, inference, or agent permission
is implemented here. The only playground authority is a server-owned demo run.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, RootModel
from starlette.concurrency import run_in_threadpool

from agentgate.app import read_body, reject_constant, response_status, unique_object
from agentgate.audit_export import MAX_SEQUENCE, export_page, format_event
from agentgate.contracts import (
    ActionRequest,
    ActionResponse,
    AuditEvent,
    Contract,
    Identifier,
    Identity,
    Reason,
)
from agentgate.control_plane import ControlConflict, ControlPlane, ThreatFeed
from agentgate.models import ChatRequest, ModelService
from agentgate.policy import Policy
from agentgate.semantics import SemanticClient
from agentgate.service import ActionService, GateError
from agentgate.storage import StorageUnavailable, Store, credential_digest

COOKIE = "agentgate_operator"
SESSION_SECONDS = 900
MAX_SESSIONS = 32
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


class AdminError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status, self.detail = status, detail


def error_response(error: Exception) -> JSONResponse:
    if isinstance(error, AdminError):
        status, detail = error.status, error.detail
    elif isinstance(error, ControlConflict):
        status, detail = 409, "Control version conflict"
    elif isinstance(error, GateError):
        status, detail = error.status_code, error.reason.value
    elif isinstance(error, StorageUnavailable):
        status, detail = 503, "Operator state unavailable"
    else:
        status, detail = 422, "Invalid request"
    return JSONResponse({"detail": detail}, status_code=status)


class AdminRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def bounded_errors(request: Request) -> Response:
            try:
                return await handler(request)
            except (
                AdminError,
                ControlConflict,
                GateError,
                StorageUnavailable,
                ValueError,
            ) as error:
                return error_response(error)

        return bounded_errors


async def body_model[T: BaseModel](request: Request, model: type[T], maximum: int = 131072) -> T:
    body = await read_body(request, maximum, 5.0)
    try:
        value = json.loads(body, object_pairs_hook=unique_object, parse_constant=reject_constant)
        pending: list[tuple[object, int]] = [(value, 1)]
        while pending:
            item, depth = pending.pop()
            if depth > 16:
                raise ValueError("JSON depth")
            if isinstance(item, dict):
                pending.extend((v, depth + 1) for v in item.values())
            elif isinstance(item, list):
                pending.extend((v, depth + 1) for v in item)
        return model.model_validate_json(json.dumps(value, allow_nan=False))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise AdminError(422, "Invalid request") from error


class Login(Contract):
    token: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]


class PolicyBody(Contract):
    policy: Policy


class ActivatePolicy(PolicyBody):
    expected_version: Annotated[str, Field(min_length=1, max_length=128)]


class ActivateFeed(Contract):
    feed: ThreatFeed
    expected_version: Annotated[str, Field(min_length=1, max_length=128)]


class DocumentPlayground(Contract):
    mode: Literal["document"]
    document_id: Identifier


class MemoryPlayground(Contract):
    mode: Literal["memory"]
    query: Annotated[str, Field(min_length=1, max_length=512)]
    limit: Annotated[int, Field(ge=1, le=10)] = 10


class MailPlayground(Contract):
    mode: Literal["mail"]
    recipient: Annotated[str, Field(min_length=1, max_length=254)]
    subject: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=8192)]
    idempotency_key: Identifier


class ModelPlayground(ChatRequest):
    mode: Literal["model"]
    stream: Literal[False] = False


class Playground(
    RootModel[
        Annotated[
            DocumentPlayground | MemoryPlayground | MailPlayground | ModelPlayground,
            Field(discriminator="mode"),
        ]
    ]
):
    pass


def playground_credential(service: ActionService, *, model: bool = False) -> str:
    # Domain-separated derivation keeps the token stable across process restarts
    # without storing or exposing plaintext. Expired/revoked rows are NOT renewed.
    token = (
        base64.urlsafe_b64encode(
            hmac.new(
                service.audit_key,
                b"operator-model-playground-credential-v1"
                if model
                else b"operator-playground-credential-v1",
                hashlib.sha256,
            ).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )
    identity = Identity(
        principal_id="operator-playground",
        tenant_id="tenant-a",
        agent_id="admin-demo",
        root_run_id="operator-playground",
        roles=("analyst",),
        operations=("chat.completions",)
        if model
        else ("documents.read", "memory.query", "mail.send"),
    )
    with service.store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT OR IGNORE INTO credentials(digest, identity, expires_at) VALUES (?, ?, ?)",
            (credential_digest(token), identity.model_dump_json(), service.clock() + 86400),
        )
        db.execute("COMMIT")
    return token


@dataclass(frozen=True)
class OperatorSession:
    digest: str
    expires_at: float
    csrf_token: str


class OperatorAuth:
    def __init__(self, service: ActionService) -> None:
        self.service = service

    def _csrf(self, token: str) -> str:
        return hmac.new(
            self.service.audit_key, b"operator-csrf-v1:" + token.encode(), hashlib.sha256
        ).hexdigest()

    def login(self, token: str, previous: str | None) -> tuple[str, OperatorSession]:
        if TOKEN_PATTERN.fullmatch(token) is None:
            raise AdminError(401, "Invalid operator credential")
        digest = credential_digest(token)
        with self.service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self.service.clock()
            row = db.execute("SELECT digest FROM operator_credentials WHERE id=1").fetchone()
            if row is None or not hmac.compare_digest(digest, row[0]):
                raise AdminError(401, "Invalid operator credential")
            # Operator credentials must never acquire agent authority, or vice versa.
            if db.execute("SELECT 1 FROM credentials WHERE digest=?", (digest,)).fetchone():
                raise AdminError(401, "Invalid operator credential")
            db.execute("DELETE FROM operator_sessions WHERE expires_at<=?", (now,))
            if previous is not None:
                db.execute(
                    "DELETE FROM operator_sessions WHERE digest=?", (credential_digest(previous),)
                )
            if db.execute("SELECT count(*) FROM operator_sessions").fetchone()[0] >= MAX_SESSIONS:
                raise AdminError(429, "Operator session capacity reached")
            session_token = secrets.token_urlsafe(32)
            session = OperatorSession(
                credential_digest(session_token), now + SESSION_SECONDS, self._csrf(session_token)
            )
            db.execute(
                "INSERT INTO operator_sessions VALUES (?, ?, ?)",
                (session.digest, digest, session.expires_at),
            )
            db.execute("COMMIT")
        return session_token, session

    def resolve(self, token: str | None) -> OperatorSession:
        if token is None or TOKEN_PATTERN.fullmatch(token) is None:
            raise AdminError(401, "Operator session required")
        digest = credential_digest(token)
        with self.service.store.connection() as db:
            row = db.execute(
                "SELECT s.expires_at FROM operator_sessions s JOIN operator_credentials c "
                "ON c.id=1 AND c.digest=s.operator_digest WHERE s.digest=? AND s.expires_at>?",
                (digest, self.service.clock()),
            ).fetchone()
            if row is None:
                raise AdminError(401, "Operator session required")
        return OperatorSession(digest, row[0], self._csrf(token))

    def logout(self, session: OperatorSession) -> None:
        with self.service.store.connection() as db:
            db.execute("DELETE FROM operator_sessions WHERE digest=?", (session.digest,))


def bootstrap_operator(directory: Path, policy: Policy) -> None:
    """Create once, never print or overwrite; do not register in agent credentials."""
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError("Operator state directory must be private")
    store = Store(directory / "agentgate.sqlite3")
    if not store.ready():
        raise StorageUnavailable
    ControlPlane(store).initialize(policy)
    path = directory / "operator.token"
    token = secrets.token_urlsafe(32)
    created = False
    try:
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM operator_credentials").fetchone():
                raise ValueError("Operator credential already exists")
            with open(path, "xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as file:
                created = True
                file.write(token.encode("ascii"))
                file.flush()
                os.fsync(file.fileno())
            db.execute(
                "INSERT INTO operator_credentials VALUES (1, ?)", (credential_digest(token),)
            )
            db.execute("COMMIT")
    except (OSError, ValueError, StorageUnavailable):
        if created:
            path.unlink()
        raise


def query(request: Request, allowed: set[str]) -> dict[str, str]:
    items = list(request.query_params.multi_items())
    if len(items) > len(allowed) or len({k for k, _ in items}) != len(items):
        raise ValueError("Duplicate query")
    if any(k not in allowed or len(v) > 128 for k, v in items):
        raise ValueError("Invalid query")
    return dict(items)


def number(value: str, minimum: int, maximum: int) -> int:
    if not value.isascii() or not value.isdigit() or not minimum <= int(value) <= maximum:
        raise ValueError("Invalid range")
    return int(value)


class OperatorTools(Protocol):
    def list_approvals(self, *, tenant_id: str, limit: int = 100) -> object: ...
    def decide(
        self, *, tenant_id: str, action_id: str, fingerprint: str, approve: bool, actor: str
    ) -> object: ...
    def outbox(self, *, tenant_id: str, limit: int = 100) -> object: ...


class ApprovalDecision(Contract):
    tenant_id: Identifier
    fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    approve: bool


def attach_admin_routes(
    app: FastAPI, service: ActionService, *, origin: str, tools: OperatorTools | None = None
) -> None:
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or (parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"))
    ):
        raise ValueError("Admin origin requires HTTPS or explicit loopback HTTP")
    secure = parsed.scheme == "https"
    if service.controls is None:
        controls = ControlPlane(service.store, service.clock)
        controls.initialize(service.policy)
        service.controls = controls
    else:
        controls = service.controls
    auth = OperatorAuth(service)
    router = APIRouter(prefix="/admin", route_class=AdminRoute)

    @app.middleware("http")
    async def operator_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not (request.url.path == "/admin" or request.url.path.startswith("/admin/")):
            return await call_next(request)
        try:
            for header in ("origin", "host", "x-csrf-token", "authorization"):
                if len(request.headers.getlist(header)) > 1:
                    raise AdminError(403, "Invalid operator request")
            if request.headers.get("host") != parsed.netloc:
                raise AdminError(403, "Invalid operator host")
            supplied_origin = request.headers.get("origin")
            if supplied_origin is not None and supplied_origin != origin:
                raise AdminError(403, "Same-origin request required")
            if request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
                raise AdminError(403, "Same-origin request required")
            if request.headers.get("authorization"):
                raise AdminError(401, "Use an operator session")
            cookies = ";".join(request.headers.getlist("cookie"))
            if sum(part.strip().startswith(COOKIE + "=") for part in cookies.split(";")) > 1:
                raise AdminError(401, "Invalid operator session")
            write = request.method not in ("GET", "HEAD", "OPTIONS")
            if write and supplied_origin != origin:
                raise AdminError(403, "Same-origin request required")
            if request.method == "POST" and request.url.path == "/admin/session":
                query(request, set())
            else:
                session = await run_in_threadpool(auth.resolve, request.cookies.get(COOKIE))
                request.state.operator_session = session
                csrf = request.headers.get("x-csrf-token", "")
                if write and (
                    re.fullmatch(r"[a-f0-9]{64}", csrf) is None
                    or not hmac.compare_digest(csrf, session.csrf_token)
                ):
                    raise AdminError(403, "Valid CSRF token required")
            response = await call_next(request)
        except (AdminError, StorageUnavailable, ValueError) as error:
            response = error_response(error)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def session_body(session: OperatorSession) -> dict[str, object]:
        return {
            "authenticated": True,
            "expires_at": session.expires_at,
            "csrf_token": session.csrf_token,
        }

    @router.post("/session")
    async def login(request: Request) -> Response:
        body = await body_model(request, Login, 1024)
        token, session = await run_in_threadpool(
            auth.login, body.token, request.cookies.get(COOKIE)
        )
        response = JSONResponse(session_body(session))
        response.set_cookie(
            COOKIE,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/admin",
        )
        return response

    @router.get("/session")
    def introspect(request: Request) -> dict[str, object]:
        query(request, set())
        return session_body(request.state.operator_session)

    @router.delete("/session")
    def logout(request: Request) -> Response:
        query(request, set())
        auth.logout(request.state.operator_session)
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(
            COOKIE, path="/admin", secure=secure, httponly=True, samesite="strict"
        )
        return response

    def policy_result(policy: Policy) -> dict[str, object]:
        return {"policy": policy.model_dump(mode="json"), "version": policy.version}

    def validate_policy(policy: Policy) -> Policy:
        policy = controls.validate_policy(policy)
        if not service.semantic_ready(policy):
            raise AdminError(422, "Required semantic worker unavailable")
        return policy

    @router.get("/policy")
    def policy(request: Request) -> dict[str, object]:
        query(request, set())
        return policy_result(controls.snapshot().policy)

    @router.post("/policy/validate")
    async def validate(request: Request) -> dict[str, object]:
        query(request, set())
        body = await body_model(request, PolicyBody)
        checked = await run_in_threadpool(validate_policy, body.policy)
        return {"valid": True, "version": checked.version}

    @router.post("/policy/activate")
    async def activate(request: Request) -> dict[str, object]:
        query(request, set())
        body = await body_model(request, ActivatePolicy)
        checked = await run_in_threadpool(validate_policy, body.policy)
        snapshot = await run_in_threadpool(controls.activate_policy, checked, body.expected_version)
        return policy_result(snapshot.policy)

    def feed_result() -> dict[str, object]:
        feed = controls.snapshot().feed
        return {
            "feed": feed.model_dump(mode="json"),
            "version": feed.version,
            "indicator_count": len(feed.indicators),
            "refresh": "operator-managed",
        }

    @router.get("/feed")
    def feed(request: Request) -> dict[str, object]:
        query(request, set())
        return feed_result()

    @router.post("/feed")
    async def import_feed(request: Request) -> dict[str, object]:
        query(request, set())
        body = await body_model(request, ActivateFeed)
        snapshot = await run_in_threadpool(controls.activate_feed, body.feed, body.expected_version)
        return {
            "feed": snapshot.feed.model_dump(mode="json"),
            "version": snapshot.feed.version,
            "indicator_count": len(snapshot.feed.indicators),
            "refresh": "operator-managed",
        }

    @router.get("/events")
    def events(request: Request) -> dict[str, object]:
        params = query(request, {"limit"})
        limit = number(params.get("limit", "100"), 1, 1000)
        # Reuse the export allowlist; never dump semantic raw scores or payload digests.
        with service.store.connection() as db:
            rows = db.execute(
                "SELECT sequence, event FROM audit_events ORDER BY sequence DESC LIMIT ?", (limit,)
            ).fetchall()
        records = []
        for row in rows:
            if row["event"] is None:
                raise StorageUnavailable
            event = AuditEvent.model_validate_json(row["event"])
            records.append(
                format_event(event, row["sequence"], "jsonl") | {"feed_version": event.feed_version}
            )
        return {"events": records, "control_events": controls.events(limit)}

    @router.get("/overview")
    def overview(request: Request) -> dict[str, object]:
        query(request, set())
        snapshot = controls.snapshot()
        events = service.store.events(1000)
        terminal = [event for event in events if event.event_type != "dispatch_intent"]
        models = getattr(app.state, "models", None)
        model_enabled = isinstance(models, ModelService) and snapshot.policy.models is not None
        return {
            "policy_version": snapshot.policy.version,
            "feed_version": snapshot.feed.version,
            "controls": {
                "authentication": True,
                "document_authorization": True,
                "redact_emails": snapshot.policy.output.redact_emails,
                "semantic_required": snapshot.policy.semantic_required,
                "semantic_mode": snapshot.policy.semantic_mode,
                "threat_feed_indicators": len(snapshot.feed.indicators),
            },
            "counts": {
                **{
                    decision: sum(e.decision == decision for e in terminal)
                    for decision in ("allow", "redact", "deny")
                },
                "pending": None,
            },
            "count_window": {
                "status": "measured",
                "audit_rows": len(events),
                "limit": 1000,
                "scope": "latest audit rows; terminal events only",
            },
            "budgets": {
                "status": "measured",
                "tool_counters": service.store.budget_counters(1000),
                "semantic": service.semantic.budget()
                if isinstance(service.semantic, SemanticClient)
                else {"status": "not_configured"},
                "limit": 1000,
                "model": models.ledger.counters()
                if model_enabled and isinstance(models, ModelService)
                else None,
            },
            "services": {
                "gateway": "ready" if service.store.ready() else "unavailable",
                "model": "configured" if model_enabled else "not_configured",
                "semantic": "not_configured"
                if service.semantic is None
                else "ready"
                if service.semantic.ready()
                else "unavailable",
            },
            "latency": {"status": "unknown", "reason": "Gateway latency is not recorded"},
            "coverage": {
                "enforced": ["documents.read"] + (["chat.completions"] if model_enabled else []),
                "not_implemented": ([] if model_enabled else ["models"])
                + ["memory", "mail", "approvals", "mcp"],
                "real_model_evaluation": "not_run",
                "pending_approvals": "unknown",
            },
        }

    @router.get("/audit/export")
    def export(request: Request) -> Response:
        params = query(
            request,
            {"tenant", "unattributed", "format", "after_sequence", "through_sequence", "limit"},
        )
        if ("tenant" in params) == ("unattributed" in params) or params.get(
            "unattributed", "true"
        ) != "true":
            raise ValueError("Select tenant or unattributed")
        format_value = params.get("format", "jsonl")
        if format_value not in ("jsonl", "ecs", "splunk-hec"):
            raise ValueError("Invalid format")
        # Narrowed literals preserve the existing export schema and selection semantics.
        export_format: Literal["jsonl", "ecs", "splunk-hec"] = (
            "ecs"
            if format_value == "ecs"
            else "splunk-hec"
            if format_value == "splunk-hec"
            else "jsonl"
        )
        page = export_page(
            service.store.path,
            tenant=params.get("tenant"),
            format=export_format,
            after_sequence=number(params.get("after_sequence", "0"), 0, MAX_SEQUENCE),
            through_sequence=number(params["through_sequence"], 0, MAX_SEQUENCE)
            if "through_sequence" in params
            else None,
            limit=number(params.get("limit", "100"), 1, 1000),
        )
        return Response(
            "\n".join(page.lines) + ("\n" if page.lines else ""),
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": 'attachment; filename="agentgate-audit.jsonl"',
                "X-AgentGate-Cursor": json.dumps(page.metadata(), separators=(",", ":")),
            },
        )

    def execute_playground(body: Playground) -> Response:
        selection = body.root
        if isinstance(selection, ModelPlayground):
            models = getattr(app.state, "models", None)
            if not isinstance(models, ModelService):
                raise AdminError(503, "Model provider unavailable")
            context = service.new_context()
            try:
                service.authenticate(context, playground_credential(service, model=True))
                chat = ChatRequest.model_validate_json(selection.model_dump_json(exclude={"mode"}))
                service.digest_payload(context, chat.model_dump_json().encode())
                return JSONResponse(models.complete(context, chat))
            except (GateError, StorageUnavailable) as error:
                code, denied = models.reject(context, error)
                return JSONResponse(denied.model_dump(mode="json", exclude_none=True), code)
        if selection.mode != "document":
            tool_service()  # Explicit unavailable until the real executor is attached.
        context = service.new_context()
        try:
            service.authenticate(context, playground_credential(service))
            action = ActionRequest(
                operation={
                    "document": "documents.read",
                    "memory": "memory.query",
                    "mail": "mail.send",
                }[selection.mode],
                arguments=selection.model_dump(mode="json", exclude={"mode"}),
            )
            service.digest_payload(context, action.model_dump_json().encode())
            result = service.execute(context, action)
            status = response_status(result)
        except (GateError, StorageUnavailable) as error:
            status, result = service.reject(
                context,
                error if isinstance(error, GateError) else GateError(503, Reason.AUDIT_UNAVAILABLE),
            )
        return JSONResponse(result.model_dump(mode="json", exclude_none=True), status_code=status)

    @router.post("/playground")
    async def playground(request: Request) -> Response:
        query(request, set())
        body = await body_model(request, Playground, 65536)
        return await run_in_threadpool(execute_playground, body)

    def tool_service() -> OperatorTools:
        current = tools if tools is not None else getattr(service, "tools", None)
        if current is None:
            raise AdminError(503, "Scoped tools and approvals unavailable")
        return cast(OperatorTools, current)

    def tenant_selection(request: Request) -> tuple[str, int]:
        params = query(request, {"tenant_id", "limit"})
        tenant_id = params.get("tenant_id", "")
        if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}", tenant_id) is None:
            raise ValueError("Tenant required")
        return tenant_id, number(params.get("limit", "100"), 1, 100)

    @router.get("/approvals")
    def approvals(request: Request) -> Response:
        tenant, limit = tenant_selection(request)
        result = tool_service().list_approvals(tenant_id=tenant, limit=limit)
        return JSONResponse({"approvals": jsonable_encoder(result)})

    @router.post("/approvals/{action_id}/decision")
    async def decide(action_id: str, request: Request) -> Response:
        query(request, set())
        if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}", action_id) is None:
            raise ValueError("Invalid action ID")
        body = await body_model(request, ApprovalDecision, 2048)
        result = await run_in_threadpool(
            tool_service().decide,
            tenant_id=body.tenant_id,
            action_id=action_id,
            fingerprint=body.fingerprint,
            approve=body.approve,
            actor="operator",
        )
        status = response_status(result) if isinstance(result, ActionResponse) else 200
        return JSONResponse(jsonable_encoder(result), status_code=status)

    @router.get("/outbox")
    def outbox(request: Request) -> Response:
        tenant, limit = tenant_selection(request)
        result = tool_service().outbox(tenant_id=tenant, limit=limit)
        return JSONResponse({"messages": jsonable_encoder(result)})

    app.include_router(router)
