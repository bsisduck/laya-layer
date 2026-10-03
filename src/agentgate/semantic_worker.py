"""Authenticated loopback service supervising a single native inference process."""

import asyncio
import hmac
import json
import os
import tempfile
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agentgate.app import read_body, reject_constant, unique_object
from agentgate.contracts import SemanticResult
from agentgate.semantic_quota import QuotaExhausted, QuotaUnavailable, SemanticQuota
from agentgate.semantics import (
    REVISIONS,
    Backend,
    Capabilities,
    SemanticInvalid,
    SemanticRequest,
    SemanticUnavailable,
    validate_result,
)
from agentgate.service import GateError


class Supervisor:
    def __init__(
        self,
        command: Sequence[str],
        backend: Backend,
        *,
        timeout: float = 5.0,
        quota: SemanticQuota | None = None,
    ) -> None:
        if not 0 < timeout <= 5:
            raise ValueError("Job deadline must be within five seconds")
        self.command = command
        self.backend = backend
        self.timeout = timeout
        self.quota = quota
        self.process: asyncio.subprocess.Process | None = None
        self.capabilities: Capabilities | None = None
        self.lock = asyncio.Lock()
        self.scratch: tempfile.TemporaryDirectory[str] | None = None

    @property
    def ready(self) -> bool:
        return (
            self.capabilities is not None
            and self.process is not None
            and self.process.returncode is None
        )

    async def start(self) -> None:
        try:
            async with asyncio.timeout(45):
                self.scratch = tempfile.TemporaryDirectory(prefix="agentgate-inference-")
                self.process = await asyncio.create_subprocess_exec(
                    *self.command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=16384,
                    env=os.environ | {"AGENTGATE_ENGINE_SCRATCH": self.scratch.name},
                )
                assert self.process.stdout is not None
                capabilities = Capabilities.model_validate_json(
                    await self.process.stdout.readline()
                )
                if (
                    capabilities.backend != self.backend
                    or capabilities.checkpoint_revision != REVISIONS[self.backend]
                ):
                    raise SemanticInvalid
                self.capabilities = capabilities
        except (TimeoutError, OSError, ValueError, SemanticInvalid) as error:
            await self.close()
            raise SemanticUnavailable from error

    async def close(self) -> None:
        self.capabilities = None
        if self.process is not None and self.process.returncode is None:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass
            try:
                async with asyncio.timeout(1):
                    await self.process.wait()
            except TimeoutError:
                # Keep readiness false and retain assets if the OS has not reaped the child.
                return
        if self.scratch is not None:
            self.scratch.cleanup()
            self.scratch = None

    async def evaluate(self, request: SemanticRequest) -> SemanticResult:
        if not self.ready or self.lock.locked():
            raise SemanticUnavailable
        async with self.lock:
            assert self.process is not None
            assert self.process.stdin is not None and self.process.stdout is not None
            if self.quota is not None:
                await asyncio.to_thread(self.quota.admit)
            try:
                async with asyncio.timeout(self.timeout):
                    self.process.stdin.write(request.model_dump_json().encode() + b"\n")
                    await self.process.stdin.drain()
                    result = SemanticResult.model_validate_json(
                        await self.process.stdout.readline()
                    )
                    validate_result(result, request.request_id, self.backend)
                    return result
            except asyncio.CancelledError:
                await self.close()
                raise
            except (TimeoutError, OSError, ValueError, SemanticInvalid) as error:
                # Killing/reaping, not abandoning a thread, bounds ongoing native work.
                await self.close()
                raise SemanticUnavailable from error


def create_worker(supervisor: Supervisor, token: str) -> FastAPI:
    if len(token) != 43 or not token.isascii():
        raise ValueError("Worker requires a dedicated 256-bit service token")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await supervisor.start()
        try:
            yield
        finally:
            await supervisor.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def authenticated(request: Request) -> bool:
        values = request.headers.getlist("authorization")
        return len(values) == 1 and hmac.compare_digest(
            values[0].encode(), f"Bearer {token}".encode()
        )

    @app.get("/internal/v1/semantic/ready")
    @app.get("/internal/v1/semantic/capabilities")
    async def ready(request: Request) -> JSONResponse:
        if not authenticated(request):
            return JSONResponse({"status": "unauthorized"}, status_code=401)
        if not supervisor.ready or supervisor.capabilities is None:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse(supervisor.capabilities.model_dump())

    @app.post("/internal/v1/semantic/evaluate")
    async def evaluate(request: Request) -> JSONResponse:
        if not authenticated(request):
            return JSONResponse({"status": "unauthorized"}, status_code=401)
        try:
            if request.query_params:
                raise ValueError("Query parameters unsupported")
            body = await read_body(request, 65536, 2.0)
            data = json.loads(body, object_pairs_hook=unique_object, parse_constant=reject_constant)
            job = SemanticRequest.model_validate(data)
            if len(job.untrusted_content.encode()) > 32768:
                raise ValueError("Content exceeds byte limit")
            result = await supervisor.evaluate(job)
            return JSONResponse(
                result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
            )
        except GateError as error:
            return JSONResponse({"status": "invalid_request"}, status_code=error.status_code)
        except (ValueError, UnicodeError, RecursionError):
            return JSONResponse({"status": "invalid_request"}, status_code=422)
        except SemanticUnavailable:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        except QuotaExhausted:
            return JSONResponse({"status": "budget_exhausted"}, status_code=429)
        except QuotaUnavailable:
            return JSONResponse({"status": "budget_unavailable"}, status_code=503)

    @app.get("/internal/v1/semantic/budget")
    async def budget(request: Request) -> JSONResponse:
        if not authenticated(request):
            return JSONResponse({"status": "unauthorized"}, status_code=401)
        if supervisor.quota is None:
            return JSONResponse({"status": "not_configured"}, status_code=503)
        try:
            data = await asyncio.to_thread(supervisor.quota.status)
            return JSONResponse(data, headers={"Cache-Control": "no-store"})
        except QuotaUnavailable:
            return JSONResponse({"status": "unavailable"}, status_code=503)

    return app
