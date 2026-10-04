"""Additive authenticated discovery and immutable-action retrieval/resumption."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from agentgate.contracts import Reason
from agentgate.service import ActionService, GateError
from agentgate.storage import StorageUnavailable

IDENTITY_HEADERS = (
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


def bearer_token(request: Request) -> str | None:
    if len(request.headers.getlist("authorization")) > 1:
        raise GateError(401, Reason.INVALID_CREDENTIAL)
    parts = request.headers.get("authorization", "").split(" ")
    return parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else None


def reject_identity_overrides(request: Request) -> None:
    if request.query_params or any(name in request.headers for name in IDENTITY_HEADERS):
        raise GateError(422, Reason.IDENTITY_OVERRIDE)


def attach_tool_routes(app: FastAPI, service: ActionService) -> None:
    from agentgate.app import read_body, response_status

    @app.api_route("/v1/tools", methods=["GET"])
    @app.api_route("/v1/actions/{action_id}", methods=["GET"])
    @app.api_route("/v1/actions/{action_id}/resume", methods=["POST"])
    async def scoped_action(request: Request, action_id: str | None = None) -> JSONResponse:
        context = service.new_context()
        try:
            await run_in_threadpool(service.authenticate, context, bearer_token(request))
            reject_identity_overrides(request)
            if action_id is None:
                tools = await run_in_threadpool(service.tools.discover, context)
                return JSONResponse({"tools": tools}, headers={"Cache-Control": "no-store"})
            resume = request.method == "POST"
            if resume:
                limits = service.policy.ingress
                body = await read_body(request, limits.max_body_bytes, limits.body_timeout_seconds)
                # The only executable payload is the stored snapshot. Require an
                # empty object, not a mutable second set of action arguments.
                if body.strip() != b"{}":
                    raise GateError(422, Reason.MALFORMED_REQUEST)
            response = await run_in_threadpool(
                service.tools.retrieve, context, action_id, resume=resume
            )
            status = response_status(response)
        except (GateError, StorageUnavailable) as error:
            rejection = (
                error if isinstance(error, GateError) else GateError(503, Reason.AUDIT_UNAVAILABLE)
            )
            status, response = await run_in_threadpool(service.reject, context, rejection)
        headers = {"Cache-Control": "no-store", "X-Request-ID": context.trace_id}
        if status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            response.model_dump(mode="json", exclude_none=True), status_code=status, headers=headers
        )
