"""Pinned semantic service contract and bounded gateway client."""

import asyncio
import math
from typing import Annotated, Literal, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import Field

from agentgate.contracts import Contract, Identifier, SemanticResult

Backend = Literal["laya_standard", "laya_coreml"]
QUESTION_SET: Literal["content-role-v1"] = "content-role-v1"
REVISIONS: dict[Backend, str] = {
    "laya_standard": "e4e9ddf21a7b1903b7acffd8814ad4307bf63a67",
    "laya_coreml": "8139e9089273319512c730218903784074133187",
}
LABELS = {"task_data", "behavior_instruction", "unclear"}


class SemanticRequest(Contract):
    request_id: Identifier
    question_set_id: Literal["content-role-v1"] = QUESTION_SET
    operation: Literal["documents.read"] = "documents.read"
    untrusted_content: Annotated[str, Field(max_length=32768)]


class Capabilities(Contract):
    status: Literal["ready"]
    backend: Backend
    checkpoint_revision: str
    question_set_id: Literal["content-role-v1"] = QUESTION_SET
    token_capacity: Literal[1024] = 1024
    max_concurrency: Literal[1] = 1


class SemanticUnavailable(Exception):
    pass


class SemanticBudgetExceeded(SemanticUnavailable):
    pass


class SemanticBudgetStatus(Contract):
    scope: Literal["installation_utc_day"]
    day: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    calls: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=1_000_000)]
    remaining: Annotated[int, Field(ge=0)]


class SemanticInvalid(Exception):
    pass


def validate_result(result: SemanticResult, request_id: str, backend: Backend) -> None:
    if (
        result.request_id != request_id
        or result.backend != backend
        or result.checkpoint_revision != REVISIONS[backend]
        or result.question_set_id != QUESTION_SET
    ):
        raise SemanticInvalid
    coverage = result.coverage
    if coverage.windows_evaluated not in (0, 1):
        raise SemanticInvalid
    if result.status in ("ok", "abstain"):
        if (
            not coverage.complete
            or coverage.windows_evaluated != 1
            or coverage.input_truncated
            or coverage.options_collapsed
            or result.usage.input_tokens == 0
            or set(result.selected_labels) != {"content_role"}
            or result.selected_labels["content_role"] not in LABELS
            or set(result.raw_scores) != LABELS
            or any(not 0 <= score <= 1 for score in result.raw_scores.values())
            or not math.isclose(sum(result.raw_scores.values()), 1.0, abs_tol=0.001)
        ):
            raise SemanticInvalid
        label = result.selected_labels["content_role"]
        if (label == "unclear") != (result.status == "abstain"):
            raise SemanticInvalid
        if result.raw_scores[label] < max(result.raw_scores.values()):
            raise SemanticInvalid
    elif coverage.complete or result.selected_labels or result.raw_scores:
        raise SemanticInvalid


class SemanticEvaluator(Protocol):
    def ready(self) -> bool: ...

    def evaluate(self, request_id: str, content: str) -> SemanticResult: ...


class SemanticClient:
    def __init__(self, base_url: str, token: str, backend: Backend) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or len(token) != 43
        ):
            raise ValueError("Semantic service requires an authenticated loopback URL")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.backend = backend

    def _request(self, method: str, path: str, body: bytes | None = None) -> bytes:
        return asyncio.run(self._request_async(method, path, body))

    async def _request_async(self, method: str, path: str, body: bytes | None) -> bytes:
        try:
            async with (
                asyncio.timeout(7),
                httpx.AsyncClient(timeout=7, trust_env=False, follow_redirects=False) as client,
            ):
                async with client.stream(
                    method,
                    self.base_url + path,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    content=body,
                ) as response:
                    if response.status_code == 429:
                        raise SemanticBudgetExceeded
                    if response.status_code != 200:
                        raise SemanticUnavailable
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise SemanticInvalid
                    chunks = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(chunks) + len(chunk) > 16384:
                            raise SemanticInvalid
                        chunks.extend(chunk)
                    return bytes(chunks)
        except (httpx.HTTPError, TimeoutError) as error:
            raise SemanticUnavailable from error

    def ready(self) -> bool:
        try:
            result = Capabilities.model_validate_json(
                self._request("GET", "/internal/v1/semantic/ready")
            )
            return (
                result.backend == self.backend
                and result.checkpoint_revision == REVISIONS[self.backend]
            )
        except (ValueError, SemanticUnavailable, SemanticInvalid):
            return False

    def evaluate(self, request_id: str, content: str) -> SemanticResult:
        request = SemanticRequest(request_id=request_id, untrusted_content=content)
        data = self._request(
            "POST", "/internal/v1/semantic/evaluate", request.model_dump_json().encode()
        )
        try:
            result = SemanticResult.model_validate_json(data)
            validate_result(result, request_id, self.backend)
            return result
        except ValueError as error:
            raise SemanticInvalid from error

    def budget(self) -> dict[str, str | int]:
        try:
            budget = SemanticBudgetStatus.model_validate_json(
                self._request("GET", "/internal/v1/semantic/budget")
            )
            if budget.remaining != max(0, budget.limit - budget.calls):
                raise ValueError("Inconsistent semantic quota")
            return budget.model_dump() | {"status": "measured"}
        except (ValueError, SemanticUnavailable, SemanticInvalid):
            return {"status": "unavailable"}
