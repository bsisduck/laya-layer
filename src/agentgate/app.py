"""Bounded HTTP ingress for the document-only enforcement slice."""

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from agentgate.contracts import ActionRequest, ActionResponse, Reason
from agentgate.metrics import LatencyWindow, ResponseTimings
from agentgate.service import ActionService, GateError
from agentgate.storage import StorageUnavailable
from agentgate.web_routes import attach_web_routes

if TYPE_CHECKING:
    from agentgate.models import ModelService
    from agentgate.telemetry_contract import TelemetryConfig


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str) -> NoReturn:
    raise ValueError("Nonfinite JSON number")


def parse_json(body: bytes, max_depth: int) -> object:
    try:
        data = json.loads(body, object_pairs_hook=unique_object, parse_constant=reject_constant)
        pending: list[tuple[object, int]] = [(data, 1)]
        while pending:
            item, depth = pending.pop()
            if depth > max_depth:
                raise ValueError("JSON depth exceeded")
            if isinstance(item, dict):
                pending.extend((value, depth + 1) for value in item.values())
            elif isinstance(item, list):
                pending.extend((value, depth + 1) for value in item)
        return data
    except (ValueError, UnicodeError, RecursionError, ValidationError) as error:
        raise GateError(422, Reason.MALFORMED_REQUEST) from error


def parse_action(body: bytes, max_depth: int) -> ActionRequest:
    try:
        return ActionRequest.model_validate(parse_json(body, max_depth))
    except ValidationError as error:
        raise GateError(422, Reason.MALFORMED_REQUEST) from error


async def read_body(request: Request, maximum: int, timeout: float) -> bytes:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise GateError(415, Reason.UNSUPPORTED_CONTENT_TYPE)
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise GateError(415, Reason.UNSUPPORTED_CONTENT_TYPE)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            length = int(content_length)
            if length < 0:
                raise ValueError
        except ValueError as error:
            raise GateError(422, Reason.MALFORMED_REQUEST) from error
        if length > maximum:
            raise GateError(413, Reason.BODY_TOO_LARGE)
    body = bytearray()
    try:
        async with asyncio.timeout(timeout):
            async for chunk in request.stream():
                if len(body) + len(chunk) > maximum:
                    raise GateError(413, Reason.BODY_TOO_LARGE)
                body.extend(chunk)
    except (TimeoutError, ClientDisconnect) as error:
        raise GateError(408, Reason.REQUEST_TIMEOUT) from error
    return bytes(body)


def create_app(
    service: ActionService,
    models: "ModelService | None" = None,
    *,
    admin_origin: str | None = None,
    local_console: bool = False,
    serving_address: tuple[str, int] | None = None,
    enable_mcp: bool = False,
    telemetry_config: "TelemetryConfig | None" = None,
    telemetry_token_file: Path | None = None,
) -> FastAPI:
    if local_console and admin_origin is None:
        raise ValueError("Local console requires an admin origin")
    if (telemetry_config is None) != (telemetry_token_file is None):
        raise ValueError("Telemetry configuration and credential file must be supplied together")
    app = FastAPI(
        title="AgentGate", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    attach_web_routes(app)
    app.state.latency = LatencyWindow()
    app.state.telemetry_config = telemetry_config
    bearer = HTTPBearer(auto_error=False)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        try:
            healthy = service.store.ready() and service.semantic_ready()
        except StorageUnavailable:
            healthy = False
        return JSONResponse(
            {"status": "ready" if healthy else "not_ready"}, status_code=200 if healthy else 503
        )

    @app.post("/v1/actions/execute", response_model=ActionResponse)
    async def execute(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> JSONResponse:
        context = service.new_context()
        try:
            if len(request.headers.getlist("authorization")) > 1:
                raise GateError(401, Reason.INVALID_CREDENTIAL)
            await run_in_threadpool(
                service.authenticate, context, credentials.credentials if credentials else None
            )
            if request.query_params or any(
                name in request.headers
                for name in (
                    "x-tenant-id",
                    "x-principal-id",
                    "x-agent-id",
                    "x-run-id",
                    "x-root-run-id",
                    "x-role",
                    "x-human-id",
                    "x-subject-id",
                    "x-delegation-id",
                    "x-on-behalf-of",
                    "x-department",
                )
            ):
                raise GateError(422, Reason.IDENTITY_OVERRIDE)
            limits = service.context_controls(context).policy.ingress
            body = await read_body(request, limits.max_body_bytes, limits.body_timeout_seconds)
            service.digest_payload(context, body)
            action = parse_action(body, limits.max_json_depth)
            response = await run_in_threadpool(service.execute, context, action)
            status_code = response_status(response)
        except (GateError, StorageUnavailable) as error:
            rejection = (
                error if isinstance(error, GateError) else GateError(503, Reason.AUDIT_UNAVAILABLE)
            )
            status_code, response = await run_in_threadpool(service.reject, context, rejection)
        headers = {"Cache-Control": "no-store", "X-Request-ID": context.trace_id}
        if status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            response.model_dump(mode="json", exclude_none=True),
            status_code=status_code,
            headers=headers,
        )

    from agentgate.tool_routes import attach_tool_routes

    attach_tool_routes(app, service)
    if enable_mcp:
        from agentgate.mcp_adapter import attach_mcp

        attach_mcp(app, service)
    if models is not None:
        from agentgate.model_http import attach_model_routes

        attach_model_routes(app, models)
    if admin_origin is not None:
        from agentgate.admin import attach_admin_routes

        attach_admin_routes(
            app,
            service,
            origin=admin_origin,
            local_console=local_console,
            serving_address=serving_address,
        )
    if telemetry_config is not None and telemetry_token_file is not None:
        from agentgate.telemetry_runtime import attach_sender

        attach_sender(app, service.store.path, telemetry_config, telemetry_token_file)
    app.add_middleware(ResponseTimings, window=app.state.latency)
    return app


def response_status(response: ActionResponse) -> int:
    if response.action_state in ("pending", "approved"):
        return 202
    if response.action_state == "expired":
        return 410
    if response.action_state == "denied":
        return 403
    return 200
