"""Official MCP SDK tools-only HTTP adapter; no remote proxies or approval method."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mcp import types
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send

from agentgate.app import parse_json, read_body
from agentgate.contracts import ActionRequest, Reason
from agentgate.scoped_contracts import INPUTS
from agentgate.service import ActionService, Context, GateError
from agentgate.storage import StorageUnavailable
from agentgate.tool_catalog import CATALOG, mcp_annotations
from agentgate.tool_routes import bearer_token, reject_identity_overrides


class MCPAdapter:
    def __init__(self, service: ActionService) -> None:
        self.service = service
        server: Server[Any] = Server(
            "AgentGate",
            version="0.1.0",
            on_list_tools=self.list_tools,
            on_call_tool=self.call_tool,
        )
        self.manager = StreamableHTTPSessionManager(
            server,
            json_response=True,
            max_sessions=128,
            session_idle_timeout=300,
            max_request_body_size=service.policy.ingress.max_body_bytes,
            security_settings=TransportSecuritySettings(
                allowed_hosts=[
                    "127.0.0.1",
                    "127.0.0.1:*",
                    "localhost",
                    "localhost:*",
                    "[::1]",
                    "[::1]:*",
                ],
                allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
            ),
        )

    async def authenticate(self, request: Request) -> Context:
        context = self.service.new_context()
        await run_in_threadpool(self.service.authenticate, context, bearer_token(request))
        reject_identity_overrides(request)
        return context

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        context = self.service.new_context()
        try:
            request = Request(scope, receive)
            context = await self.authenticate(request)
            version = request.headers.get("mcp-protocol-version")
            if version is not None and version not in HANDSHAKE_PROTOCOL_VERSIONS:
                # This adapter supports session-based initialization. Do not let
                # a per-request envelope bypass the SDK's session-owner check.
                raise GateError(400, Reason.MALFORMED_REQUEST)
            if any(
                len(request.headers.getlist(name)) > 1
                for name in ("mcp-session-id", "mcp-protocol-version", "host", "origin")
            ):
                raise GateError(400, Reason.MALFORMED_REQUEST)
            assert context.credential_digest is not None
            assert context.identity is not None
            # The SDK compares authorization_context for every request carrying
            # a session ID. Bind more tightly than principal alone: to this exact
            # server-issued run credential. Never treat a session ID as a token.
            scope["user"] = AuthenticatedUser(
                AccessToken(
                    token=context.credential_digest,
                    client_id=context.credential_digest,
                    subject=context.identity.principal_id,
                    scopes=list(context.identity.operations),
                )
            )
            if request.method == "POST":
                limits = self.service.policy.ingress
                body = await read_body(request, limits.max_body_bytes, limits.body_timeout_seconds)
                parse_json(body, limits.max_json_depth)
                delivered = False

                async def replay() -> Message:
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()

                await self.manager.handle_request(scope, replay, send)
            else:
                await self.manager.handle_request(scope, receive, send)
        except (GateError, StorageUnavailable) as error:
            rejection = (
                error if isinstance(error, GateError) else GateError(503, Reason.AUDIT_UNAVAILABLE)
            )
            status, result = await run_in_threadpool(self.service.reject, context, rejection)
            await JSONResponse(
                result.model_dump(mode="json", exclude_none=True),
                status_code=status,
                headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"},
            )(scope, receive, send)

    async def list_tools(
        self, ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        if not isinstance(ctx.request, Request):
            return types.ListToolsResult(tools=[])
        context = await self.authenticate(ctx.request)
        operations = await run_in_threadpool(self.service.tools.discover, context)
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=operation,
                    description=CATALOG[operation].description,
                    input_schema=INPUTS[operation].model_json_schema(),
                    annotations=types.ToolAnnotations.model_validate(mcp_annotations(operation)),
                )
                for operation in operations
            ]
        )

    async def call_tool(
        self, ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        context = self.service.new_context()
        try:
            if not isinstance(ctx.request, Request):
                raise GateError(401, Reason.AUTHENTICATION_REQUIRED)
            context = await self.authenticate(ctx.request)
            try:
                action = ActionRequest.model_validate(
                    {"operation": params.name, "arguments": params.arguments or {}}
                )
            except ValidationError as error:
                raise GateError(422, Reason.MALFORMED_REQUEST) from error
            self.service.digest_payload(context, action.model_dump_json().encode())
            response = await run_in_threadpool(self.service.execute, context, action)
        except (GateError, StorageUnavailable) as error:
            rejection = (
                error if isinstance(error, GateError) else GateError(503, Reason.AUDIT_UNAVAILABLE)
            )
            _, response = await run_in_threadpool(self.service.reject, context, rejection)
        data = response.model_dump(mode="json", exclude_none=True)
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text=response.model_dump_json(exclude_none=True))
            ],
            structured_content=data,
            is_error=response.status in ("denied", "error", "expired"),
        )


def attach_mcp(app: FastAPI, service: ActionService) -> None:
    adapter = MCPAdapter(service)
    app.state.mcp_enabled = True
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with previous(app), adapter.manager.run():
            yield

    app.router.lifespan_context = lifespan
    app.router.routes.append(Route("/mcp", endpoint=adapter, methods=["POST", "GET", "DELETE"]))
