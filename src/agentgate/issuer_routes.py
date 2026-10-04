"""Bounded non-browser exchange ingress; never echo assertion or crypto errors."""

from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from agentgate.app import parse_json, read_body
from agentgate.contracts import Contract, Reason
from agentgate.control_plane import ControlsChanged
from agentgate.issuer_exchange import ExchangeLimit, exchange
from agentgate.issuer_trust import MAX_TOKEN_BYTES
from agentgate.service import ActionService, GateError
from agentgate.storage import CredentialInvalid, StorageUnavailable


class ExchangeRequest(Contract):
    access_token: Annotated[str, Field(min_length=1, max_length=MAX_TOKEN_BYTES)]


def attach_exchange(app: FastAPI, service: ActionService) -> None:
    bearer = HTTPBearer(auto_error=False)

    @app.post("/v1/authority/exchange")
    async def person_exchange(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> JSONResponse:
        context = service.new_context()
        status = 401
        result: dict[str, object] = {"reason": "EXCHANGE_DENIED"}
        try:
            if len(request.headers.getlist("authorization")) != 1:
                raise CredentialInvalid
            await run_in_threadpool(
                service.authenticate, context, credentials.credentials if credentials else None
            )
            if request.query_params or any(
                name.lower().startswith("x-")
                and name.lower()
                in {
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
                }
                for name in request.headers
            ):
                raise GateError(422, Reason.IDENTITY_OVERRIDE)
            body = await read_body(request, MAX_TOKEN_BYTES + 1024, 5.0)
            payload = ExchangeRequest.model_validate(parse_json(body, 4))
            child, expires = await run_in_threadpool(
                exchange, service, context, payload.access_token
            )
            status, result = 200, {"token": child, "expires_at": expires, "token_type": "Bearer"}
        except (CredentialInvalid, ValidationError):
            pass
        except ExchangeLimit:
            status, result = 429, {"reason": "EXCHANGE_LIMIT"}
        except (StorageUnavailable, ControlsChanged):
            status, result = 503, {"reason": "EXCHANGE_UNAVAILABLE"}
        except GateError as error:
            status = error.status_code
        return JSONResponse(
            result, status_code=status, headers={"Cache-Control": "no-store", "Pragma": "no-cache"}
        )
