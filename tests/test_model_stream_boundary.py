"""T45: real gateway/provider HTTP boundaries, synthetic output, no model inference."""

import asyncio
import json
import socket
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from threading import Event, Thread
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from test_models import model as model

from agentgate.app import create_app
from agentgate.contracts import Reason
from agentgate.models import PrivateProvider
from agentgate.storage import Store

WAIT_SECONDS = 5


@contextmanager
def live_http(app):
    """Use the existing HTTP tests' pre-bound socket and startup-event convention."""
    started = Event()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets)
            started.set()

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = Server(uvicorn.Config(app, log_level="critical", access_log=False))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            assert started.wait(WAIT_SECONDS), "HTTP fixture did not start"
            yield origin
        finally:
            server.should_exit = True
            thread.join(timeout=WAIT_SECONDS)
            assert not thread.is_alive(), "HTTP fixture did not stop"


@pytest.mark.parametrize("upstream_kind", ["loopback_http", "split_transport"])
def test_T45_fragmented_upstream_is_inspected_before_any_client_output(
    model, monkeypatch, upstream_kind
):
    content = "withheld-prefix AGENTGATE_SECRET[wire-fragment-fixture] withheld-suffix"
    marker = b"AGENTGATE_SECRET[wire-fragment-fixture]"
    usage = {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}
    raw = json.dumps(
        {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        },
        separators=(",", ":"),
    ).encode()
    start = raw.index(marker)
    boundaries = [
        start + 5,
        start + len(b"AGENTGATE_SECRET[wire-"),
        start + len(marker) - 1,
        len(raw),
    ]
    fragments = [
        raw[left:right] for left, right in zip([0, *boundaries[:-1]], boundaries, strict=True)
    ]
    assert b"".join(fragments) == raw
    assert marker in raw and all(b"AGENTGATE_SECRET[" not in part for part in fragments)
    consumed = [Event() for _ in fragments]
    release = [Event() for _ in fragments]
    emitted, observed, upstream_requests = [], [], []
    response_messages, release_audit, consumer_bytes = [], [], []
    consumer_started = Event()
    provider_token = uuid4().hex

    async def source():
        for index, part in enumerate(fragments):
            emitted.append(part)
            yield part
            # Do not let the next HTTP body fragment coalesce with this one.
            assert await asyncio.to_thread(release[index].wait, WAIT_SECONDS)

    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def complete(request: Request):
        upstream_requests.append(
            (request.url.path, request.headers["authorization"], await request.json())
        )
        return StreamingResponse(source(), media_type="application/json")

    class SplitStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            async for part in source():
                yield part

    def split_response(request):
        upstream_requests.append(
            (request.url.path, request.headers["authorization"], json.loads(request.content))
        )
        return httpx.Response(
            200, headers={"Content-Type": "application/json"}, stream=SplitStream()
        )

    class ObservedStream(httpx.AsyncByteStream):
        def __init__(self, inner):
            self.inner = inner

        async def __aiter__(self):
            size = 0
            index = 0
            async for part in self.inner:
                observed.append(part)
                yield part
                # Resumption means PrivateProvider consumed this raw fragment.
                size += len(part)
                assert size <= boundaries[index], "Upstream fragments unexpectedly coalesced"
                if size == boundaries[index]:
                    consumed[index].set()
                    assert await asyncio.to_thread(release[index].wait, WAIT_SECONDS)
                    index += 1
            assert size == len(raw) and index == len(fragments)

        async def aclose(self):
            await self.inner.aclose()

    with ExitStack() as stack:
        if upstream_kind == "loopback_http":
            upstream_origin = stack.enter_context(live_http(upstream))
            inner = httpx.AsyncHTTPTransport(retries=0)
        else:
            upstream_origin = "http://127.0.0.1"
            inner = httpx.MockTransport(split_response)

        class ObservedTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                response = await inner.handle_async_request(request)
                response.stream = ObservedStream(response.stream)
                return response

            async def aclose(self):
                await inner.aclose()

        real_client = httpx.AsyncClient

        def observed_client(*args, **kwargs):
            # Preserve PrivateProvider's deadlines/auth/options and real HTTP path.
            return real_client(*args, **kwargs, transport=ObservedTransport())

        monkeypatch.setattr("agentgate.models.httpx.AsyncClient", observed_client)
        model.models.provider = PrivateProvider(upstream_origin + "/v1", provider_token)
        app = create_app(model.actions, model.models)

        async def observed_app(scope, receive, send):
            async def observed_send(message):
                if message["type"].startswith("http.response."):
                    response_messages.append(message)
                    if message["type"] == "http.response.start":
                        release_audit.extend(Store(model.store.path).events())
                await send(message)

            await app(scope, receive, observed_send)

        gateway_origin = stack.enter_context(live_http(observed_app))

        def consume():
            with httpx.Client(trust_env=False) as client:
                with client.stream(
                    "POST",
                    gateway_origin + "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {model.token}"},
                    json={
                        "model": "local-demo",
                        "messages": [{"role": "user", "content": "Hello"}],
                        "stream": True,
                    },
                ) as response:
                    consumer_started.set()
                    for part in response.iter_raw():
                        consumer_bytes.append(part)
                    return response.status_code, response.headers, b"".join(consumer_bytes)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(consume)
            try:
                for index in range(len(fragments)):
                    assert consumed[index].wait(WAIT_SECONDS), (
                        f"Provider did not consume fragment {index}"
                    )
                    assert emitted == fragments[: index + 1]
                    assert b"".join(observed) == b"".join(fragments[: index + 1])
                    assert all(b"AGENTGATE_SECRET[" not in part for part in observed)
                    assert response_messages == []
                    assert not consumer_started.is_set() and consumer_bytes == []
                    assert not future.done()
                    assert [e.event_type for e in Store(model.store.path).events()] == [
                        "dispatch_intent"
                    ]
                    release[index].set()
            finally:
                for barrier in release:
                    barrier.set()
            code, headers, body = future.result(timeout=WAIT_SECONDS)

    assert len(upstream_requests) == 1
    path, authorization, payload = upstream_requests[0]
    assert path == "/v1/chat/completions"
    assert authorization == f"Bearer {provider_token}"
    assert payload["stream"] is False
    assert payload["messages"] == [{"role": "user", "content": "Hello"}]
    assert model.provider.calls == []  # The complete-output provider fixture was not used.
    assert emitted == fragments and b"".join(observed) == raw
    if upstream_kind == "split_transport":
        assert observed == fragments
    assert code == 403 and headers["content-type"].startswith("application/json")
    blocked = json.loads(body)
    assert blocked["status"] == "denied" and blocked["decision"] == "deny"
    assert blocked["executed"] is True
    assert blocked["reason_codes"] == ["SECRET_IN_OUTPUT"]
    for withheld in (
        marker,
        b"AGENTGATE",
        b"wire-fragment",
        b"withheld-prefix",
        b"withheld-suffix",
        b"data: ",
        b"[DONE]",
    ):
        assert withheld not in body
    events = Store(model.store.path).events()
    assert [e.event_type for e in events] == ["dispatch_intent", "output_blocked"]
    assert release_audit == events  # Durable terminal evidence preceded response headers.
    intent, terminal = events
    assert intent.executed is False and terminal.executed is True
    assert terminal.decision == "deny" and terminal.reason_codes == (Reason.SECRET_IN_OUTPUT,)
    assert {e.action_id for e in events} == {blocked["action_id"]}
    assert {e.trace_id for e in events} == {blocked["trace_id"], headers["x-request-id"]}
    assert all(
        e.operation == "chat.completions" and e.principal_id == model.identity.principal_id
        for e in events
    )
    counters = model.models.ledger.counters()
    assert {(r["scope"], r["resource"]) for r in counters} == {
        (scope, resource)
        for scope in ("tenant_day", "principal_day", "root_run")
        for resource in ("calls", "tokens", "micro_usd")
    }
    assert len(counters) == 9
    assert all(
        r["spent"] == {"calls": 1, "tokens": usage["total_tokens"], "micro_usd": 0}[r["resource"]]
        and r["reserved"] == 0
        and r["frozen"] == 0
        for r in counters
    )
    with model.store.connection() as db:
        attempts = db.execute("SELECT action_id, state FROM model_attempts").fetchall()
        assert [tuple(row) for row in attempts] == [(blocked["action_id"], "settled")]
    assert content not in json.dumps([e.model_dump(mode="json") for e in events])
    for path in model.store.path.parent.glob("db.sqlite3*"):
        assert marker not in path.read_bytes()
