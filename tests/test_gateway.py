import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentgate.app import create_app
from agentgate.cli import initialize_demo
from agentgate.contracts import Identity, Reason
from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
from agentgate.policy import Policy
from agentgate.service import ActionService
from agentgate.storage import StorageUnavailable, Store


class ObservedExecutor(FixtureExecutor):
    def __init__(self, store: Store):
        super().__init__(demo_documents())
        self.store = store
        self.calls: list[tuple[str, str]] = []

    def read(self, document_id: str, tenant_id: str) -> str:
        # The independently read database must already contain durable intent before invocation.
        assert any(
            event.event_type == "dispatch_intent" for event in Store(self.store.path).events()
        )
        self.calls.append((document_id, tenant_id))
        return super().read(document_id, tenant_id)


@dataclass
class Harness:
    store: Store
    executor: ObservedExecutor
    service: ActionService
    client: TestClient
    token: str
    identity: Identity
    now: list[float]

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def read(self, document_id="tenant-a-notes", **kwargs):
        return self.client.post(
            "/v1/actions/execute",
            headers=self.headers,
            json={"operation": "documents.read", "arguments": {"document_id": document_id}},
            **kwargs,
        )


@pytest.fixture
def harness(tmp_path: Path):
    store = Store(tmp_path / "audit.sqlite3")
    store.initialize()
    identity = Identity(
        principal_id="analyst",
        tenant_id="tenant-a",
        agent_id="reader",
        root_run_id="run-a",
        roles=("analyst",),
        operations=("documents.read",),
    )
    token = store.issue(identity, expires_at=2000.0)
    executor = ObservedExecutor(store)
    now = [1000.0]
    service = ActionService(
        store,
        Policy(policy_id="test", revision=1),
        DocumentRegistry(demo_documents()),
        executor,
        b"explicit-test-hmac-key-not-a-secret",
        clock=lambda: now[0],
    )
    with TestClient(create_app(service)) as client:
        yield Harness(store, executor, service, client, token, identity, now)


def test_T01_allowed_read_has_durable_intent_and_private_audit(harness: Harness):
    result = harness.read()
    assert result.status_code == 200
    body = result.json()
    assert body["executed"] is True
    assert body["decision"] == "allow"
    assert "quarterly notes" in body["result"]["content"]
    assert harness.executor.calls == [("tenant-a-notes", "tenant-a")]
    events = harness.store.events()
    assert [event.event_type for event in events] == ["dispatch_intent", "action_completed"]
    assert [event.executed for event in events] == [False, True]
    assert events[0].trace_id == events[1].trace_id == body["trace_id"]
    assert events[0].payload_digest == events[1].payload_digest
    assert len(events[0].payload_digest) == 64
    assert events[1].principal_id == "analyst"
    assert events[1].tenant_id == "tenant-a"
    assert events[1].root_run_id == "run-a"
    assert events[1].policy_version == "test:1"
    for file in harness.store.path.parent.glob("audit.sqlite3*"):
        data = file.read_bytes()
        assert harness.token.encode() not in data
        assert body["result"]["content"].encode() not in data
        assert b"tenant-a-notes" not in data
    assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic abc", "Bearer " + "x" * 43])
def test_T02_invalid_authentication_never_dispatches(harness: Harness, authorization):
    headers = {"Authorization": authorization} if authorization else {}
    result = harness.client.post("/v1/actions/execute", headers=headers, content=b"not even JSON")
    assert result.status_code == 401
    assert result.json()["executed"] is False
    assert result.headers["www-authenticate"] == "Bearer"
    assert harness.executor.calls == []
    assert harness.store.events()[-1].principal_id is None


def test_T03_credential_expires_at_boundary(harness: Harness):
    harness.now[0] = 2000.0
    assert harness.read().status_code == 401
    assert harness.executor.calls == []


def test_T04_revocation_between_admission_and_dispatch(harness: Harness, monkeypatch):
    original = harness.store.dispatch_intent

    def revoke_before_dispatch(*args):
        harness.store.revoke(harness.token)
        original(*args)

    monkeypatch.setattr(harness.store, "dispatch_intent", revoke_before_dispatch)
    result = harness.read()
    assert result.status_code == 401
    assert harness.executor.calls == []
    assert [event.event_type for event in harness.store.events()] == ["action_denied"]


@pytest.mark.parametrize("document_id", ["tenant-b-notes", "unknown", "tenant-a-secret"])
def test_T05_resource_authorization_happens_before_executor(harness: Harness, document_id):
    result = harness.read(document_id)
    assert result.status_code == 403
    assert result.json()["reason_codes"] == ["RESOURCE_NOT_ALLOWED"]
    assert result.json()["executed"] is False
    assert harness.executor.calls == []


@pytest.mark.parametrize(
    "override", ["tenant_id", "principal_id", "agent_id", "root_run_id", "roles"]
)
def test_T05_body_identity_cannot_override_credential(harness: Harness, override):
    result = harness.client.post(
        "/v1/actions/execute",
        headers=harness.headers,
        json={
            "operation": "documents.read",
            "arguments": {"document_id": "tenant-b-notes"},
            override: "tenant-b",
        },
    )
    assert result.status_code == 422
    assert harness.executor.calls == []


def test_T05_identity_headers_query_and_duplicate_credentials_are_rejected(harness: Harness):
    action = {"operation": "documents.read", "arguments": {"document_id": "tenant-a-notes"}}
    headers = harness.headers | {"X-Tenant-ID": "tenant-b"}
    assert (
        harness.client.post("/v1/actions/execute", headers=headers, json=action).status_code == 422
    )
    assert (
        harness.client.post(
            "/v1/actions/execute?tenant_id=tenant-b", headers=harness.headers, json=action
        ).status_code
        == 422
    )
    duplicate = [("Authorization", f"Bearer {harness.token}"), ("Authorization", "Bearer other")]
    assert (
        harness.client.post("/v1/actions/execute", headers=duplicate, json=action).status_code
        == 401
    )
    assert harness.executor.calls == []


@pytest.mark.parametrize("update", [{"roles": ("viewer",)}, {"operations": ()}])
def test_agent_scope_and_principal_roles_are_both_required(harness: Harness, update):
    harness.token = harness.store.issue(
        harness.identity.model_copy(update=update), expires_at=2000.0
    )
    assert harness.read().json()["reason_codes"] == ["OPERATION_NOT_ALLOWED"]
    assert harness.executor.calls == []


@pytest.mark.parametrize("operation", ["mail.send", "documents_read", "sk-client-secret-value"])
def test_T07_unknown_operations_are_not_executed_or_copied_to_audit(harness: Harness, operation):
    result = harness.client.post(
        "/v1/actions/execute",
        headers=harness.headers,
        json={"operation": operation, "arguments": {}},
    )
    assert result.status_code == 403
    assert result.json()["reason_codes"] == ["UNKNOWN_OPERATION"]
    assert harness.executor.calls == []
    assert harness.store.events()[-1].operation is None
    assert operation not in result.text
    assert operation not in harness.store.events()[-1].model_dump_json()


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        {},
        {"document_id": 12},
        {"document_id": "../../etc/passwd"},
        {"document_id": "tenant-a-notes", "tenant_id": "tenant-b"},
    ],
)
def test_T08_malformed_arguments_fail_without_input_echo(harness: Harness, arguments):
    result = harness.client.post(
        "/v1/actions/execute",
        headers=harness.headers,
        json={"operation": "documents.read", "arguments": arguments},
    )
    assert result.status_code == 422
    assert result.json()["reason_codes"] == ["MALFORMED_REQUEST"]
    assert harness.executor.calls == []


@pytest.mark.parametrize(
    "body",
    [
        b'{"operation":"documents.read","operation":"mail.send","arguments":{}}',
        b'{"operation":NaN}',
        b'{"arguments":"AGENTGATE_SECRET[never-echo]"}',
        b"\xff",
        b"[" * 100 + b"0" + b"]" * 100,
    ],
)
def test_parser_rejects_duplicates_nonfinite_deep_and_invalid_json(harness: Harness, body):
    result = harness.client.post(
        "/v1/actions/execute",
        headers=harness.headers | {"Content-Type": "application/json"},
        content=body,
    )
    assert result.status_code == 422
    assert "never-echo" not in result.text
    assert "never-echo" not in harness.store.events()[-1].model_dump_json()
    assert harness.executor.calls == []


def test_body_limit_applies_with_and_without_content_length(harness: Harness):
    headers = harness.headers | {"Content-Type": "application/json"}
    for payload in [b"x" * 16385, iter([b"x" * 9000, b"x" * 9000])]:
        result = harness.client.post("/v1/actions/execute", headers=headers, content=payload)
        assert result.status_code == 413
        assert result.json()["executed"] is False
    assert harness.executor.calls == []


def test_unsupported_content_encoding_and_type(harness: Harness):
    for headers in [
        {"Content-Type": "text/plain"},
        {"Content-Type": "application/json", "Content-Encoding": "gzip"},
    ]:
        result = harness.client.post(
            "/v1/actions/execute", headers=harness.headers | headers, content=b"{}"
        )
        assert result.status_code == 415
    assert harness.executor.calls == []


def test_email_is_redacted_before_release(harness: Harness):
    result = harness.read("tenant-a-contact")
    assert result.status_code == 200
    assert result.json()["decision"] == "redact"
    assert "analyst@demo.internal" not in result.text
    assert "[REDACTED_EMAIL]" in result.json()["result"]["content"]
    assert harness.store.events()[-1].reason_codes == (Reason.EMAIL_REDACTED,)


def test_synthetic_secret_output_is_withheld_and_never_audited(harness: Harness):
    result = harness.read("tenant-a-leak")
    assert result.status_code == 403
    assert result.json()["executed"] is True
    assert "result" not in result.json()
    assert "never-release-this" not in result.text
    assert "never-release-this" not in json.dumps(
        [event.model_dump(mode="json") for event in harness.store.events()]
    )
    assert harness.store.events()[-1].event_type == "output_blocked"


@pytest.mark.parametrize("content", ["ą" * 20000, b"not text", "\ud800"])
def test_oversized_or_invalid_executor_output_is_withheld(harness: Harness, monkeypatch, content):
    monkeypatch.setattr(harness.executor, "read", lambda *_: content)
    result = harness.read()
    assert result.status_code in (403, 503)
    assert result.json()["executed"] is True
    assert "result" not in result.json()


def test_redaction_expansion_is_bounded(harness: Harness, monkeypatch):
    harness.service.policy = Policy(
        policy_id="small",
        revision=1,
        output=harness.service.policy.output.model_copy(update={"max_result_bytes": 64}),
    )
    monkeypatch.setattr(harness.executor, "read", lambda *_: "a@b.co a@b.co")
    assert harness.read().json()["reason_codes"] == ["OUTPUT_TOO_LARGE"]


def test_executor_exception_does_not_leak_its_message(harness: Harness, monkeypatch):
    def fail(*args):
        raise RuntimeError("upstream secret never-echo")

    monkeypatch.setattr(harness.executor, "read", fail)
    result = harness.read()
    assert result.status_code == 503
    assert result.json()["executed"] is True
    assert "never-echo" not in result.text
    assert "never-echo" not in harness.store.events()[-1].model_dump_json()


def test_required_semantics_fail_closed_without_worker(harness: Harness):
    harness.service.policy = harness.service.policy.model_copy(update={"semantic_required": True})
    assert harness.client.get("/health/ready").status_code == 503
    result = harness.read()
    assert result.status_code == 503
    assert result.json()["reason_codes"] == ["REQUIRED_SEMANTIC_UNAVAILABLE"]
    assert harness.executor.calls == []


def test_T47_failed_dispatch_audit_blocks_executor(harness: Harness, monkeypatch):
    def fail(*args):
        raise StorageUnavailable

    monkeypatch.setattr(harness.store, "dispatch_intent", fail)
    result = harness.read()
    assert result.status_code == 503
    assert result.json()["executed"] is False
    assert harness.executor.calls == []


def test_T47_failed_outcome_audit_withholds_already_executed_result(harness: Harness, monkeypatch):
    def fail(*args):
        raise StorageUnavailable

    monkeypatch.setattr(harness.store, "append", fail)
    result = harness.read()
    assert result.status_code == 503
    assert result.json()["executed"] is True
    assert result.json()["reason_codes"] == ["AUDIT_UNAVAILABLE"]
    assert "result" not in result.json()
    assert [event.event_type for event in harness.store.events()] == ["dispatch_intent"]


def test_health_has_no_identity_policy_or_credentials(harness: Harness, monkeypatch):
    assert harness.client.get("/health/live").json() == {"status": "live"}
    assert harness.client.get("/health/ready").json() == {"status": "ready"}
    monkeypatch.setattr(harness.store, "ready", lambda: False)
    assert harness.client.get("/health/ready").status_code == 503
    for path in ["/admin/events", "/v1/chat/completions", "/mcp", "/openapi.json"]:
        assert harness.client.get(path).status_code == 404


def test_concurrent_requests_keep_distinct_correlated_audit_pairs(harness: Harness):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: harness.read(), range(12)))
    assert all(result.status_code == 200 for result in results)
    assert len(harness.executor.calls) == 12
    events = harness.store.events()
    assert len(events) == 24
    for result in results:
        pair = [event for event in events if event.action_id == result.json()["action_id"]]
        assert [event.event_type for event in pair] == ["dispatch_intent", "action_completed"]


def test_demo_initialization_protects_credentials_and_refuses_overwrite(tmp_path: Path):
    directory = tmp_path / "state"
    initialize_demo(directory)
    token = (directory / "client.token").read_text()
    assert len(token) == 43
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "client.token").stat().st_mode & 0o777 == 0o600
    assert (directory / "audit.key").stat().st_mode & 0o777 == 0o600
    assert (directory / "agentgate.sqlite3").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        initialize_demo(directory)
    assert (directory / "client.token").read_text() == token
