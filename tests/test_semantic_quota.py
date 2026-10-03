"""Admission tests use observable child processes, not Laya accuracy fixtures."""

import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from test_models import model as model
from test_semantics import result_data

from agentgate.semantic_quota import QuotaExhausted, QuotaUnavailable, SemanticQuota
from agentgate.semantic_worker import Supervisor, create_worker
from agentgate.semantics import (
    REVISIONS,
    Capabilities,
    SemanticBudgetExceeded,
    SemanticClient,
)


def worker(path, marker, *, backend="laya_standard", timeout=5, stall=False):
    result = result_data() | {"backend": backend, "checkpoint_revision": REVISIONS[backend]}
    caps = Capabilities(status="ready", backend=backend, checkpoint_revision=REVISIONS[backend])
    script = (
        "import json,sys,time\n"
        f"print({caps.model_dump_json()!r},flush=True)\n"
        "for line in sys.stdin:\n"
        " job=json.loads(line)\n"
        f" with open({str(marker)!r},'a') as observed: observed.write('dispatch\\n')\n"
        + (" time.sleep(60)\n" if stall else "")
        + f" result={result!r}\n result['request_id']=job['request_id']\n"
        " print(json.dumps(result),flush=True)\n"
    )
    return Supervisor(
        [sys.executable, "-u", "-c", script], backend, timeout=timeout, quota=SemanticQuota(path, 1)
    )


HEADERS = {"Authorization": "Bearer " + "w" * 43}
JOB = {"request_id": "req-1", "untrusted_content": "synthetic document"}
ENDPOINT = "/internal/v1/semantic/evaluate"


def test_worker_rejects_exhaustion_without_native_call_across_backend_restart(tmp_path):
    path, marker = tmp_path / "quota.db", tmp_path / "effects"
    for backend, expected in [("laya_standard", 200), ("laya_coreml", 429)]:
        with TestClient(create_worker(worker(path, marker, backend=backend), "w" * 43)) as client:
            assert client.post(ENDPOINT, headers=HEADERS, json=JOB).status_code == expected
            assert client.get("/internal/v1/semantic/budget").status_code == 401
            status = client.get("/internal/v1/semantic/budget", headers=HEADERS)
            assert status.json()["calls"] == 1
            assert status.json()["remaining"] == 0
            assert client.post(ENDPOINT, headers=HEADERS, json=JOB).status_code == 429
    assert marker.read_text().splitlines() == ["dispatch"]
    assert path.stat().st_mode & 0o777 == 0o600


def test_auth_and_malformed_requests_cannot_consume_quota(tmp_path):
    path, marker = tmp_path / "quota.db", tmp_path / "effects"
    with TestClient(create_worker(worker(path, marker), "w" * 43)) as client:
        assert client.post(ENDPOINT, json=JOB).status_code == 401
        assert client.post(ENDPOINT, headers=HEADERS, json=JOB | {"extra": True}).status_code == 422
        assert (
            client.post(
                ENDPOINT, headers=HEADERS, json=JOB | {"untrusted_content": "x" * 32769}
            ).status_code
            == 422
        )
        assert client.get("/internal/v1/semantic/budget", headers=HEADERS).json()["calls"] == 0
    assert not marker.exists()


def test_storage_failure_prevents_native_dispatch(tmp_path):
    path, marker = tmp_path / "quota.db", tmp_path / "effects"
    supervisor = worker(path, marker)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TRIGGER fail BEFORE INSERT ON semantic_days BEGIN SELECT RAISE(ABORT,'fixture'); END"
        )
    with TestClient(create_worker(supervisor, "w" * 43)) as client:
        result = client.post(ENDPOINT, headers=HEADERS, json=JOB)
        assert result.status_code == 503
        assert result.json()["status"] == "budget_unavailable"
    assert not marker.exists()


def test_timeout_consumes_quota_before_native_work_and_is_not_refunded(tmp_path):
    path, marker = tmp_path / "quota.db", tmp_path / "effects"
    supervisor = worker(path, marker, timeout=0.08, stall=True)
    with TestClient(create_worker(supervisor, "w" * 43)) as client:
        assert client.post(ENDPOINT, headers=HEADERS, json=JOB).status_code == 503
        assert not supervisor.ready
    assert marker.read_text().splitlines() == ["dispatch"]
    with pytest.raises(QuotaExhausted):
        SemanticQuota(path, 1).admit()


def test_last_capacity_is_atomic_across_independent_processes(tmp_path):
    path = tmp_path / "quota.db"
    SemanticQuota(path, 1)
    script = (
        "import sys\nfrom pathlib import Path\n"
        "from agentgate.semantic_quota import SemanticQuota,QuotaExhausted\n"
        "try: SemanticQuota(Path(sys.argv[1]),1).admit()\n"
        "except QuotaExhausted: sys.exit(2)\n"
    )

    def call(_):
        return subprocess.run(
            [sys.executable, "-c", script, str(path)], capture_output=True, timeout=10
        ).returncode

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(call, range(4)))
    assert sorted(outcomes) == [0, 2, 2, 2]
    assert SemanticQuota(path, 1000).status()["calls"] == 1
    with pytest.raises(QuotaExhausted):
        SemanticQuota(path, 1000).admit()  # A new backend cannot increase today's ceiling.


def test_lower_limit_applies_today_and_higher_limit_only_next_day(tmp_path):
    now = [1000.0]
    path = tmp_path / "quota.db"
    first = SemanticQuota(path, 3, clock=lambda: now[0])
    first.admit()
    with pytest.raises(QuotaExhausted):
        SemanticQuota(path, 1, clock=lambda: now[0]).admit()
    with pytest.raises(QuotaExhausted):
        first.admit()
    now[0] += 86400
    first.admit()
    assert first.status()["remaining"] == 2
    now[0] -= 86400  # Returning to a used day cannot reset its old spend.
    with pytest.raises(QuotaExhausted):
        first.admit()


@pytest.mark.parametrize("limit", [0, -1, True, 1_000_001])
def test_invalid_limits_and_symlink_do_not_create_or_overwrite_state(tmp_path, limit):
    with pytest.raises(ValueError):
        SemanticQuota(tmp_path / "quota.db", limit)
    target = tmp_path / "untouched"
    target.write_text("keep")
    link = tmp_path / "quota.db"
    link.symlink_to(target)
    with pytest.raises(QuotaUnavailable):
        SemanticQuota(link)
    assert target.read_text() == "keep"


def test_gateway_returns_budget_denial_with_zero_generation_dispatch(model):
    class Exhausted:
        def ready(self):
            return True

        def evaluate(self, *args):
            raise SemanticBudgetExceeded

    model.actions.semantic = Exhausted()
    model.actions.policy = model.actions.policy.model_copy(update={"semantic_required": True})
    denied = model.call()
    assert denied.status_code == 429
    assert denied.json()["reason_codes"] == ["SEMANTIC_BUDGET_EXCEEDED"]
    assert model.provider.calls == []
    assert model.models.ledger.counters() == []


def test_client_maps_worker_exhaustion_and_validates_status(monkeypatch):
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        return original(transport=httpx.MockTransport(lambda req: httpx.Response(429)))

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    client = SemanticClient("http://127.0.0.1:8091", "w" * 43, "laya_standard")
    with pytest.raises(SemanticBudgetExceeded):
        client.evaluate("req-1", "text")
    assert client.budget() == {"status": "unavailable"}
    monkeypatch.setattr(
        client,
        "_request",
        lambda *args: json.dumps(
            {
                "scope": "installation_utc_day",
                "day": "2026-10-03",
                "calls": 1,
                "limit": 2,
                "remaining": 1,
            }
        ).encode(),
    )
    assert client.budget()["status"] == "measured"
