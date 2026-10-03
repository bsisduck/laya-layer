"""Authenticated, bounded model facade and deliberately buffered SSE encoding."""

import json
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from agentgate.contracts import ActionResponse, Reason
from agentgate.models import ChatRequest, ModelService
from agentgate.service import Context, GateError
from agentgate.storage import StorageUnavailable

if TYPE_CHECKING:
    pass


def parse_chat(raw: bytes, max_depth: int) -> ChatRequest:
    from agentgate.app import reject_constant, unique_object

    try:
        data = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
        pending: list[tuple[object, int]] = [(data, 1)]
        while pending:
            value, depth = pending.pop()
            if depth > max_depth:
                raise ValueError("JSON nesting too deep")
            if isinstance(value, dict):
                pending.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                pending.extend((item, depth + 1) for item in value)
        return ChatRequest.model_validate(data)
    except (ValueError, UnicodeError, RecursionError, ValidationError) as error:
        raise GateError(422, Reason.MALFORMED_REQUEST) from error


def attach_model_routes(app: FastAPI, models: ModelService) -> None:
    from agentgate.app import read_body

    actions = models.actions
    bearer = HTTPBearer(auto_error=False)
    app.state.models = models

    async def authenticate(
        request: Request, credentials: HTTPAuthorizationCredentials | None, context: Context
    ) -> None:
        if len(request.headers.getlist("authorization")) > 1:
            raise GateError(401, Reason.INVALID_CREDENTIAL)
        await run_in_threadpool(
            actions.authenticate, context, credentials.credentials if credentials else None
        )
        if request.query_params or any(
            key in request.headers
            for key in (
                "x-tenant-id",
                "x-principal-id",
                "x-agent-id",
                "x-run-id",
                "x-root-run-id",
                "x-role",
            )
        ):
            raise GateError(422, Reason.IDENTITY_OVERRIDE)

    async def rejection(context: Context, error: GateError | StorageUnavailable) -> JSONResponse:
        denied = error if isinstance(error, GateError) else GateError(503, Reason.AUDIT_UNAVAILABLE)
        if not context.executed:
            code, body = await run_in_threadpool(actions.reject, context, denied)
        else:
            # ModelService atomically records the terminal event with settlement.
            code = denied.status_code
            body = ActionResponse(
                status="error" if code >= 500 else "denied",
                action_id=context.action_id,
                trace_id=context.trace_id,
                decision="deny",
                reason_codes=(denied.reason,),
                policy_version=actions.policy.version,
                executed=True,
            )
        headers = {"Cache-Control": "no-store", "X-Request-ID": context.trace_id}
        if code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(body.model_dump(mode="json", exclude_none=True), code, headers=headers)

    @app.get("/v1/models")
    async def available_models(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> JSONResponse:
        context = actions.new_context()
        try:
            await authenticate(request, credentials, context)
            assert context.identity is not None
            policy = actions.policy.models
            aliases = (
                policy.aliases
                if policy is not None and "chat.completions" in context.identity.operations
                else ()
            )
            return JSONResponse(
                {"object": "list", "data": [{"id": alias, "object": "model"} for alias in aliases]},
                headers={"Cache-Control": "no-store"},
            )
        except (GateError, StorageUnavailable) as error:
            return await rejection(context, error)

    @app.post("/v1/chat/completions")
    async def complete(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> Response:
        context = actions.new_context()
        try:
            await authenticate(request, credentials, context)
            ingress = actions.policy.ingress
            raw = await read_body(request, ingress.max_body_bytes, ingress.body_timeout_seconds)
            actions.digest_payload(context, raw)
            chat = parse_chat(raw, ingress.max_json_depth)
            result = await run_in_threadpool(models.complete, context, chat)
            headers = {"Cache-Control": "no-store", "X-Request-ID": context.trace_id}
            if not chat.stream:
                return JSONResponse(result, headers=headers)
            # No incremental upstream bytes reach this adapter. The entire message,
            # including tool arguments, passed inspection and durable settlement.
            chunk = dict(result)
            chunk["object"] = "chat.completion.chunk"
            choices = result["choices"]
            assert isinstance(choices, list) and isinstance(choices[0], dict)
            message = choices[0]["message"]
            assert isinstance(message, dict)
            calls = message.get("tool_calls")
            if isinstance(calls, list):
                for index, call in enumerate(calls):
                    assert isinstance(call, dict)
                    call["index"] = index
            chunk["choices"] = [{"index": 0, "delta": message, "finish_reason": None}]
            end = dict(chunk)
            end["choices"] = [
                {"index": 0, "delta": {}, "finish_reason": choices[0]["finish_reason"]}
            ]
            if chat.stream_options is not None and not chat.stream_options.include_usage:
                chunk.pop("usage", None)
                end.pop("usage", None)
            encoded = (
                "".join(
                    "data: " + json.dumps(part, separators=(",", ":")) + "\n\n"
                    for part in (chunk, end)
                )
                + "data: [DONE]\n\n"
            )
            return Response(encoded, media_type="text/event-stream", headers=headers)
        except (GateError, StorageUnavailable) as error:
            return await rejection(context, error)
