import asyncio
import json
import sys
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_budgets import enable
from test_gateway import Harness
from test_gateway import harness as harness

from agentgate.contracts import SemanticResult
from agentgate.semantic_worker import Supervisor, create_worker
from agentgate.semantics import (
    REVISIONS,
    Capabilities,
    SemanticClient,
    SemanticInvalid,
    SemanticRequest,
    SemanticUnavailable,
    validate_result,
)


def result_data(label="task_data"):
    return {
        "request_id": "req-1",
        "backend": "laya_standard",
        "checkpoint_revision": REVISIONS["laya_standard"],
        "question_set_id": "content-role-v1",
        "status": "abstain" if label == "unclear" else "ok",
        "selected_labels": {"content_role": label},
        "raw_scores": {
            name: 0.8 if name == label else 0.1
            for name in ["task_data", "behavior_instruction", "unclear"]
        },
        "coverage": {
            "complete": True,
            "windows_evaluated": 1,
            "input_truncated": False,
            "options_collapsed": False,
        },
        "usage": {"input_tokens": 70, "output_tokens": 0, "inference_wall_ms": 12.5},
    }


@pytest.mark.parametrize("label", ["task_data", "behavior_instruction", "unclear"])
def test_known_labels_preserve_meaning(label):
    validate_result(SemanticResult.model_validate(result_data(label)), "req-1", "laya_standard")


@pytest.mark.parametrize(
    "patch",
    [
        {"request_id": "other"},
        {"backend": "laya_coreml"},
        {"checkpoint_revision": "a" * 40},
        {"question_set_id": "unknown"},
        {"selected_labels": {"content_role": "safe"}},
        {"selected_labels": {"content_role": "behavior_instruction"}},
        {"status": "abstain"},
        {"status": "incomplete"},
        {"raw_scores": {"task_data": 0.8, "behavior_instruction": 0.4, "unclear": -0.2}},
        {"raw_scores": {"task_data": 0.8}},
        {"raw_scores": {"task_data": float("nan")}},
    ],
)
def test_wrong_identity_labels_and_probabilities_are_rejected(patch):
    with pytest.raises((SemanticInvalid, ValidationError)):
        validate_result(
            SemanticResult.model_validate(result_data() | patch), "req-1", "laya_standard"
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"complete": False},
        {"windows_evaluated": 0},
        {"windows_evaluated": 2},
        {"input_truncated": True},
        {"options_collapsed": True},
    ],
)
def test_complete_claim_requires_full_single_window(patch):
    result = result_data()
    result["coverage"].update(patch)
    with pytest.raises(SemanticInvalid):
        validate_result(SemanticResult.model_validate(result), "req-1", "laya_standard")


@pytest.mark.parametrize(
    "patch",
    [
        {"input_tokens": 0},
        {"input_tokens": 1025},
        {"output_tokens": 1},
        {"inference_wall_ms": float("inf")},
        {"inference_wall_ms": -1},
    ],
)
def test_usage_requires_bounded_finite_evidence(patch):
    result = result_data()
    result["usage"].update(patch)
    with pytest.raises((SemanticInvalid, ValidationError)):
        validate_result(SemanticResult.model_validate(result), "req-1", "laya_standard")


class FixtureEvaluator:
    def __init__(self, label="task_data", error=None):
        self.label = label
        self.error = error
        self.calls = []

    def ready(self):
        return True

    def evaluate(self, request_id, content):
        self.calls.append(request_id)
        if self.error:
            raise self.error
        result = result_data(self.label)
        result["request_id"] = request_id
        return SemanticResult.model_validate(result)


@pytest.mark.parametrize(
    "label,expected,reason",
    [
        ("task_data", 200, "ALLOWED"),
        ("behavior_instruction", 403, "SEMANTIC_BLOCKED"),
        ("unclear", 403, "SEMANTIC_ABSTAIN"),
    ],
)
def test_gateway_semantic_release_and_minimized_audit(harness: Harness, label, expected, reason):
    harness.service.semantic = FixtureEvaluator(label)
    harness.service.policy = harness.service.policy.model_copy(update={"semantic_required": True})
    result = harness.read()
    assert result.status_code == expected
    assert result.json()["reason_codes"] == [reason]
    assert result.json()["executed"] is True
    assert ("result" in result.json()) == (expected == 200)
    event = harness.store.events()[-1]
    assert event.semantic.selected_labels["content_role"] == label
    assert event.semantic.request_id == result.json()["action_id"]
    assert "quarterly notes" not in event.model_dump_json()


def test_semantics_never_overrides_authorization_or_budget(harness: Harness):
    worker = FixtureEvaluator()
    harness.service.semantic = worker
    harness.service.policy = harness.service.policy.model_copy(update={"semantic_required": True})
    assert harness.read("tenant-b-notes").status_code == 403
    enable(harness, root_run=0)
    assert harness.read().status_code == 429
    assert worker.calls == []
    assert harness.executor.calls == []


@pytest.mark.parametrize(
    "error,reason",
    [
        (SemanticUnavailable(), "REQUIRED_SEMANTIC_UNAVAILABLE"),
        (SemanticInvalid(), "SEMANTIC_INVALID"),
    ],
)
def test_worker_errors_withhold_output_even_in_observe(harness: Harness, error, reason):
    harness.service.semantic = FixtureEvaluator(error=error)
    harness.service.policy = harness.service.policy.model_copy(
        update={"semantic_required": True, "semantic_mode": "observe"}
    )
    result = harness.read()
    assert result.status_code == 503
    assert result.json()["reason_codes"] == [reason]
    assert "result" not in result.json()


def test_observe_records_labels_while_deterministic_dlp_still_blocks(harness: Harness):
    worker = FixtureEvaluator("behavior_instruction")
    harness.service.semantic = worker
    harness.service.policy = harness.service.policy.model_copy(
        update={"semantic_required": True, "semantic_mode": "observe"}
    )
    assert harness.read().status_code == 200
    assert harness.read("tenant-a-leak").status_code == 403
    assert len(worker.calls) == 1


class FixtureSupervisor:
    def __init__(self):
        self.ready = False
        self.capabilities = Capabilities(
            status="ready", backend="laya_standard", checkpoint_revision=REVISIONS["laya_standard"]
        )
        self.calls = []

    async def start(self):
        self.ready = True

    async def close(self):
        self.ready = False

    async def evaluate(self, request):
        self.calls.append(request)
        return SemanticResult.model_validate(result_data() | {"request_id": request.request_id})


def test_worker_authenticates_before_parsing_and_does_not_echo_secrets():
    supervisor = FixtureSupervisor()
    with TestClient(create_worker(supervisor, "w" * 43)) as client:
        endpoint = "/internal/v1/semantic/evaluate"
        assert client.post(endpoint, content="not JSON").status_code == 401
        assert client.get("/internal/v1/semantic/ready").status_code == 401
        headers = {"Authorization": "Bearer " + "w" * 43}
        assert client.get("/internal/v1/semantic/ready", headers=headers).status_code == 200
        invalid = {
            "request_id": "req-1",
            "untrusted_content": "private-content",
            "checkpoint": "untrusted-url",
        }
        result = client.post(endpoint, headers=headers, json=invalid)
        assert result.status_code == 422
        assert "private-content" not in result.text
        assert supervisor.calls == []
        result = client.post(
            endpoint, headers=headers, json={"request_id": "req-1", "untrusted_content": "data"}
        )
        assert result.status_code == 200
        assert len(supervisor.calls) == 1
        duplicate = [
            ("Authorization", headers["Authorization"]),
            ("Authorization", headers["Authorization"]),
        ]
        assert client.post(endpoint, headers=duplicate, json={}).status_code == 401


@pytest.mark.parametrize(
    "body,status",
    [
        (b"x" * 65537, 413),
        (b'{"request_id":"req-1","request_id":"req-2","untrusted_content":"data"}', 422),
        (b'{"request_id":"req-1","untrusted_content":NaN}', 422),
        (json.dumps({"request_id": "req-1", "untrusted_content": "x" * 32769}).encode(), 422),
    ],
)
def test_worker_bounds_and_validates_body(body, status):
    supervisor = FixtureSupervisor()
    with TestClient(create_worker(supervisor, "w" * 43)) as client:
        response = client.post(
            "/internal/v1/semantic/evaluate",
            headers={"Authorization": "Bearer " + "w" * 43, "Content-Type": "application/json"},
            content=body,
        )
        assert response.status_code == status
        assert supervisor.calls == []


def child_script(body):
    capabilities = Capabilities(
        status="ready", backend="laya_standard", checkpoint_revision=REVISIONS["laya_standard"]
    ).model_dump_json()
    return "import json,sys,time\nprint(" + repr(capabilities) + ",flush=True)\n" + body


def test_deadline_kills_and_reaps_a_real_child_process():
    async def run():
        supervisor = Supervisor(
            [sys.executable, "-u", "-c", child_script("sys.stdin.readline()\ntime.sleep(60)")],
            "laya_standard",
            timeout=0.05,
        )
        await supervisor.start()
        process = supervisor.process
        with pytest.raises(SemanticUnavailable):
            await supervisor.evaluate(SemanticRequest(request_id="req-1", untrusted_content="data"))
        assert not supervisor.ready
        assert process.returncode is not None and process.returncode != 0
        await supervisor.close()

    asyncio.run(run())


def test_busy_worker_has_no_unbounded_queue():
    async def run():
        body = (
            "job=json.loads(sys.stdin.readline())\ntime.sleep(0.1)\nresult="
            + repr(result_data())
            + '\nresult["request_id"]=job["request_id"]\nprint(json.dumps(result),flush=True)\ntime.sleep(60)'
        )
        supervisor = Supervisor([sys.executable, "-u", "-c", child_script(body)], "laya_standard")
        await supervisor.start()
        try:
            first = asyncio.create_task(
                supervisor.evaluate(SemanticRequest(request_id="req-1", untrusted_content="data"))
            )
            while not supervisor.lock.locked():
                await asyncio.sleep(0)
            with pytest.raises(SemanticUnavailable):
                await supervisor.evaluate(
                    SemanticRequest(request_id="req-2", untrusted_content="data")
                )
            assert (await first).request_id == "req-1"
        finally:
            await supervisor.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "response", ["not-json", "x" * 17000, json.dumps(result_data() | {"request_id": "wrong"})]
)
def test_invalid_child_response_marks_worker_unhealthy_and_terminates(response):
    async def run():
        body = "sys.stdin.readline()\nprint(" + repr(response) + ",flush=True)\ntime.sleep(60)"
        supervisor = Supervisor([sys.executable, "-u", "-c", child_script(body)], "laya_standard")
        await supervisor.start()
        with pytest.raises(SemanticUnavailable):
            await supervisor.evaluate(SemanticRequest(request_id="req-1", untrusted_content="data"))
        assert not supervisor.ready
        assert supervisor.process.returncode is not None

    asyncio.run(run())


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost:8091",
        "http://127.0.0.1/other",
        "http://user:pass@127.0.0.1:8091",
    ],
)
def test_worker_destination_is_operator_configured_loopback_only(url):
    with pytest.raises(ValueError):
        SemanticClient(url, "w" * 43, "laya_standard")


def test_gateway_client_revalidates_identity_and_readiness(monkeypatch):
    client = SemanticClient("http://127.0.0.1:8091", "w" * 43, "laya_standard")
    data = deepcopy(result_data())
    monkeypatch.setattr(client, "_request", lambda *args: json.dumps(data).encode())
    assert client.evaluate("req-1", "data").coverage.complete
    data["request_id"] = "wrong"
    with pytest.raises(SemanticInvalid):
        client.evaluate("req-1", "data")
    assert client.ready() is False


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("valid", None),
        ("oversized", SemanticInvalid),
        ("encoded", SemanticInvalid),
        ("redirect", SemanticUnavailable),
    ],
)
def test_http_client_authenticates_and_bounds_untrusted_response(monkeypatch, mode, expected):
    observed = []

    class Frame(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 16385 if mode == "oversized" else json.dumps(result_data()).encode()

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            observed.append(request)
            headers = {"Content-Encoding": "gzip"} if mode == "encoded" else {}
            return httpx.Response(
                302 if mode == "redirect" else 200, headers=headers, stream=Frame()
            )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=Transport())
    )
    client = SemanticClient("http://127.0.0.1:8091", "w" * 43, "laya_standard")
    if expected is None:
        assert client.evaluate("req-1", "data").status == "ok"
    else:
        with pytest.raises(expected):
            client.evaluate("req-1", "data")
    assert len(observed) == 1
    assert observed[0].headers["Authorization"] == "Bearer " + "w" * 43


def test_supervisor_owns_scratch_cleanup_when_killing_native_work():
    async def run():
        supervisor = Supervisor(
            [sys.executable, "-u", "-c", child_script("time.sleep(60)")], "laya_standard"
        )
        await supervisor.start()
        from pathlib import Path

        scratch = Path(supervisor.scratch.name)
        (scratch / "derived-asset").write_text("fixture")
        await supervisor.close()
        assert not scratch.exists()

    asyncio.run(run())
