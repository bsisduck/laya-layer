import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agentgate.app import create_app
from agentgate.contracts import Identity
from agentgate.control_plane import ControlPlane, Indicator, ThreatFeed
from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
from agentgate.model_config import ModelPolicy, ResourceLimits
from agentgate.models import ModelService, PrivateProvider
from agentgate.policy import Policy
from agentgate.service import ActionService
from agentgate.storage import Store, credential_digest


class ObservedProvider:
    def __init__(self, store):
        self.calls = []
        self.store = store
        self.content = "Local response"
        self.usage = {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}
        self.tool_calls = None
        self.failure = None
        self.raw = None

    def complete(self, payload):
        assert any(
            event.event_type == "dispatch_intent" and event.operation == "chat.completions"
            for event in Store(self.store.path).events()
        )
        self.calls.append(payload)
        if self.failure:
            raise self.failure
        if self.raw is not None:
            return self.raw
        message = {"role": "assistant", "content": self.content}
        if self.tool_calls is not None:
            message["tool_calls"] = self.tool_calls
        return json.dumps(
            {
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                "usage": self.usage,
            }
        ).encode()


@dataclass
class ModelHarness:
    store: Store
    actions: ActionService
    models: ModelService
    provider: ObservedProvider
    client: TestClient
    token: str
    identity: Identity

    def call(self, text="Hello", *, token=None, **changes):
        payload = {"model": "local-demo", "messages": [{"role": "user", "content": text}]}
        payload.update(changes)
        return self.client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {token or self.token}"},
            json=payload,
        )

    def limits(self, **changes):
        self.actions.policy = self.actions.policy.model_copy(
            update={"models": ModelPolicy(**changes)}
        )


@pytest.fixture
def model(tmp_path: Path):
    store = Store(tmp_path / "db.sqlite3")
    store.initialize()
    identity = Identity(
        principal_id="tester",
        tenant_id="tenant-a",
        agent_id="agent",
        root_run_id="root",
        roles=("analyst",),
        operations=("documents.read", "chat.completions"),
    )
    token = store.issue(identity, 2000.0)
    actions = ActionService(
        store,
        Policy(policy_id="model-test", revision=1, models=ModelPolicy()),
        DocumentRegistry(demo_documents()),
        FixtureExecutor(demo_documents()),
        b"a" * 32,
        clock=lambda: 1000.0,
    )
    provider = ObservedProvider(store)
    models = ModelService(actions, provider)
    with TestClient(create_app(actions, models)) as client:
        yield ModelHarness(store, actions, models, provider, client, token, identity)


def test_model_intent_settlement_and_minimized_audit(model):
    response = model.call("unique-private-prompt")
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Local response"
    assert len(model.provider.calls) == 1
    events = model.store.events()
    assert [e.event_type for e in events] == ["dispatch_intent", "action_completed"]
    assert events[0].trace_id == events[1].trace_id
    assert all(e.operation == "chat.completions" for e in events)
    for counter in model.models.ledger.counters():
        assert counter["reserved"] == 0
        assert counter["spent"] == {"calls": 1, "tokens": 23, "micro_usd": 0}[counter["resource"]]
    for path in model.store.path.parent.glob("db.sqlite3*"):
        assert b"unique-private-prompt" not in path.read_bytes()
        assert b"Local response" not in path.read_bytes()
        assert model.token.encode() not in path.read_bytes()


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "unapproved"},
        {"api_base": "https://other.invalid"},
        {"api_key": "private"},
        {"metadata": {"tenant_id": "other"}},
        {"max_tokens": 500},
        {"n": 2},
        {"parallel_tool_calls": True},
        {"tools": [{"type": "function", "function": {"name": "shell", "parameters": {}}}]},
    ],
)
def test_T09_T10_forbidden_routing_has_no_upstream_attempt(model, changes):
    assert model.call(**changes).status_code in (403, 422)
    assert model.provider.calls == []
    assert model.models.ledger.counters() == []


def test_T11_input_secret_is_not_dispatched(model):
    assert model.call("AGENTGATE_SECRET[example]").status_code == 403
    assert model.provider.calls == []


def test_T12_input_and_output_emails_are_redacted(model):
    model.provider.content = "Reply to output@example.org"
    response = model.call("Contact input@example.org")
    assert response.status_code == 200
    assert "input@example.org" not in json.dumps(model.provider.calls)
    assert "output@example.org" not in response.text
    assert response.json()["agentgate"]["decision"] == "redact"
    assert "[REDACTED_EMAIL]" in json.dumps(model.provider.calls)


@pytest.mark.parametrize("stream", [False, True])
def test_T27_T45_secret_output_is_never_released_but_usage_is_settled(model, stream):
    model.provider.content = "AGENTGATE_SECRET[split-in-provider-stream]"
    response = model.call(stream=stream)
    assert response.status_code == 403
    assert response.json()["executed"] is True
    assert "AGENTGATE_SECRET" not in response.text
    assert model.store.events()[-1].event_type == "output_blocked"
    assert all(row["reserved"] == 0 for row in model.models.ledger.counters())


def test_buffered_sse_retains_tool_call_correlation(model):
    model.provider.content = None
    model.provider.tool_calls = [
        {
            "id": "call-a",
            "type": "function",
            "function": {"name": "documents_read", "arguments": '{"document_id":"tenant-a-notes"}'},
        }
    ]
    response = model.call(
        stream=True,
        tools=[
            {
                "type": "function",
                "function": {"name": "documents_read", "parameters": {"type": "object"}},
            }
        ],
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    chunks = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data:") and "[DONE]" not in line
    ]
    assert chunks[0]["choices"][0]["delta"]["tool_calls"][0]["id"] == "call-a"
    assert chunks[0]["choices"][0]["delta"]["tool_calls"][0]["index"] == 0
    assert chunks[0]["agentgate"]["buffered"] is True
    assert model.provider.calls[0]["stream"] is False


def test_model_auth_is_separate_from_ability_to_use_tools(model):
    document_token = model.store.issue(
        model.identity.model_copy(update={"operations": ("documents.read",)}), 2000.0
    )
    assert model.call(token=document_token).status_code == 403
    assert (
        model.client.get(
            "/v1/models", headers={"Authorization": f"Bearer {document_token}"}
        ).json()["data"]
        == []
    )
    assert model.client.get("/v1/models").status_code == 401
    assert model.client.post("/v1/chat/completions", json={}).status_code == 401
    model.store.revoke(model.token)
    assert model.call().status_code == 401
    assert model.provider.calls == []


def test_duplicate_keys_depth_and_identity_overrides_rejected(model):
    headers = {"Authorization": f"Bearer {model.token}", "Content-Type": "application/json"}
    response = model.client.post(
        "/v1/chat/completions",
        headers=headers,
        content='{"model":"local-demo","model":"local-demo","messages":[]}',
    )
    assert response.status_code == 422
    response = model.client.post(
        "/v1/chat/completions", headers={**headers, "X-Tenant-Id": "other"}, content="{}"
    )
    assert response.status_code == 422
    assert model.provider.calls == []


def test_T23_atomic_final_call_capacity(model):
    model.limits(root_run=ResourceLimits(calls=1), max_concurrent=8)
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: model.call().status_code, range(8)))
    assert sorted(codes) == [200] + [429] * 7
    assert len(model.provider.calls) == 1
    assert all(row["reserved"] == 0 for row in model.models.ledger.counters())


def test_T30_delegated_principal_cannot_reset_root_budget(model):
    model.limits(root_run=ResourceLimits(calls=1))
    assert model.call().status_code == 200
    child = model.identity.model_copy(update={"principal_id": "child", "agent_id": "child-agent"})
    child_token = model.store.issue(child, 2000.0)
    assert model.call(token=child_token).status_code == 429
    assert len(model.provider.calls) == 1


def test_T26_timeout_retains_reservation_and_admission_slot_after_restart(model):
    model.provider.failure = httpx.ReadTimeout("sensitive provider diagnostic")
    response = model.call()
    assert response.status_code == 503
    assert "sensitive" not in response.text
    assert all(row["spent"] == 0 for row in model.models.ledger.counters())
    assert any(row["reserved"] > 0 for row in model.models.ledger.counters())
    restarted = ModelService(model.actions, model.provider)
    with TestClient(create_app(model.actions, restarted)) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {model.token}"},
            json={"model": "local-demo", "messages": [{"role": "user", "content": "hello"}]},
        )
    assert response.status_code == 429
    assert len(model.provider.calls) == 1


def test_usage_above_bound_is_recorded_and_freezes_accounts(model):
    model.provider.usage = {"prompt_tokens": 100000, "completion_tokens": 3, "total_tokens": 100003}
    assert model.call().status_code == 503
    assert all(row["frozen"] == 1 for row in model.models.ledger.counters())
    assert model.call().status_code == 429
    assert len(model.provider.calls) == 1
    assert any(row["spent"] == 100003 for row in model.models.ledger.counters())


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0},
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 5},
    ],
)
def test_invalid_usage_withholds_output_and_retains_full_reservation(model, usage):
    model.provider.usage = usage
    response = model.call()
    assert response.status_code == 503
    assert "Local response" not in response.text
    assert any(row["reserved"] > 0 for row in model.models.ledger.counters())


def test_simulated_money_limit_rejects_before_provider(model):
    limits = ResourceLimits(calls=10, tokens=100000, micro_usd=1)
    model.limits(
        input_micro_usd=1,
        output_micro_usd=2,
        tenant_day=limits,
        principal_day=limits,
        root_run=limits,
        tariff_revision="simulated-test-v1",
    )
    assert model.call().status_code == 429
    assert model.provider.calls == []
    assert model.models.ledger.counters() == []


def test_simulated_tariff_settles_integer_micro_units(model):
    limits = ResourceLimits(micro_usd=1000000)
    model.limits(
        input_micro_usd=1,
        output_micro_usd=2,
        tenant_day=limits,
        principal_day=limits,
        root_run=limits,
        tariff_revision="simulated-test-v1",
    )
    assert model.call().status_code == 200
    assert all(
        row["spent"] == 26
        for row in model.models.ledger.counters()
        if row["resource"] == "micro_usd"
    )


def test_T47_audit_failure_prevents_upstream(model):
    with model.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(FAIL, 'no'); END"
        )
    assert model.call().status_code == 503
    assert model.provider.calls == []
    assert model.models.ledger.counters() == []


def test_T47_audit_failure_after_dispatch_withholds_result(model):
    with model.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_outcome BEFORE INSERT ON audit_events WHEN json_extract(NEW.event, '$.event_type')='action_completed' BEGIN SELECT RAISE(FAIL, 'no'); END"
        )
    assert model.call().status_code == 503
    assert len(model.provider.calls) == 1
    assert any(row["reserved"] > 0 for row in model.models.ledger.counters())


@pytest.mark.parametrize(
    "url",
    [
        "https://other.test/v1",
        "http://localhost:4000/v1",
        "http://user:pass@127.0.0.1:4000/v1",
        "http://127.0.0.1:4000/v1?key=x",
        "http://127.0.0.1:4000/other",
    ],
)
def test_private_upstream_is_fixed_and_never_client_selected(url):
    with pytest.raises(ValueError):
        PrivateProvider(url, "test-key")


def test_invalid_unicode_is_audited_without_dispatch(model):
    response = model.client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {model.token}", "Content-Type": "application/json"},
        content=b'{"model":"local-demo","messages":[{"role":"user","content":"\\ud800"}]}',
    )
    assert response.status_code == 422
    assert model.provider.calls == []
    assert model.store.events()[-1].reason_codes == ("MALFORMED_REQUEST",)


@pytest.mark.parametrize("arguments", ["[]", "not json", '{"x":1,"x":2}', '{"x":NaN}'])
def test_invalid_tool_argument_json_is_not_released(model, arguments):
    model.provider.content = None
    model.provider.tool_calls = [
        {
            "id": "call-a",
            "type": "function",
            "function": {
                "name": "documents_read",
                "arguments": arguments,
            },
        }
    ]
    response = model.call(
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "documents_read",
                    "parameters": {"type": "object"},
                },
            }
        ]
    )
    assert response.status_code == 503
    assert all(row["reserved"] == 0 for row in model.models.ledger.counters())


def test_parallel_calls_are_rejected_even_if_provider_ignores_control(model):
    model.provider.tool_calls = [
        {
            "id": f"call-{index}",
            "type": "function",
            "function": {
                "name": "documents_read",
                "arguments": "{}",
            },
        }
        for index in range(2)
    ]
    response = model.call(
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "documents_read",
                    "parameters": {"type": "object"},
                },
            }
        ]
    )
    assert response.status_code == 503
    assert "parallel_tool_calls" not in model.provider.calls[0]


def test_policy_cannot_approve_an_unregistered_model_alias():
    with pytest.raises(ValueError):
        ModelPolicy(aliases=("unregistered",))


def live_controls(model):
    controls = ControlPlane(model.store, model.actions.clock)
    controls.initialize(model.actions.policy)
    model.actions.controls = controls
    return controls


def test_T32_model_rechecks_policy_inside_reservation_transaction(model, monkeypatch):
    controls = live_controls(model)
    reserve = model.models.ledger.reserve
    calls = []

    def changed(*args, **kwargs):
        if not calls:
            calls.append(True)
            current = controls.snapshot().policy
            controls.activate_policy(
                current.model_copy(update={"revision": 2, "models": None}), current.version
            )
        return reserve(*args, **kwargs)

    monkeypatch.setattr(model.models.ledger, "reserve", changed)
    response = model.call()
    assert response.status_code == 403
    assert response.json()["policy_version"] == "model-test:2"
    assert model.provider.calls == []
    assert model.models.ledger.counters() == []


def test_T33_model_rechecks_feed_when_policy_version_is_unchanged(model, monkeypatch):
    controls = live_controls(model)
    reserve = model.models.ledger.reserve

    def changed(*args, **kwargs):
        controls.activate_feed(
            ThreatFeed(
                revision=2,
                indicators=(
                    Indicator(
                        id="deny-hello", kind="literal_text", value="Hello", stages=("model_input",)
                    ),
                ),
            ),
            "local:1",
        )
        return reserve(*args, **kwargs)

    monkeypatch.setattr(model.models.ledger, "reserve", changed)
    response = model.call()
    assert response.status_code == 403
    assert response.json()["reason_codes"] == ["THREAT_FEED_BLOCKED"]
    assert model.provider.calls == []
    assert model.store.events()[-1].feed_version == "local:2"
    assert model.models.ledger.counters() == []


def test_inflight_model_uses_dispatch_snapshot_after_policy_activation(model, monkeypatch):
    controls = live_controls(model)
    complete = model.provider.complete
    model.provider.content = "Contact someone@example.org"

    def changed(payload):
        old = controls.snapshot().policy
        controls.activate_policy(
            old.model_copy(
                update={
                    "revision": 2,
                    "output": old.output.model_copy(update={"redact_emails": False}),
                }
            ),
            old.version,
        )
        return complete(payload)

    monkeypatch.setattr(model.provider, "complete", changed)
    response = model.call()
    assert response.status_code == 200
    assert "someone@example.org" not in response.text
    assert response.json()["agentgate"]["policy_version"] == "model-test:1"
    assert model.store.events()[-1].policy_version == "model-test:1"
    assert controls.snapshot().policy.version == "model-test:2"


def test_model_output_feed_blocks_after_spend(model):
    controls = live_controls(model)
    controls.activate_feed(
        ThreatFeed(
            revision=2,
            indicators=(
                Indicator(
                    id="output",
                    kind="literal_text",
                    value="Local response",
                    stages=("model_output",),
                ),
            ),
        ),
        "local:1",
    )
    response = model.call(stream=True)
    assert response.status_code == 403
    assert "Local response" not in response.text
    assert len(model.provider.calls) == 1
    assert all(row["reserved"] == 0 for row in model.models.ledger.counters())


def test_admin_model_playground_uses_real_authority_feed_and_ledger(model):
    origin = "http://127.0.0.1:8769"
    live_controls(model)
    operator = "o" * 43
    with model.store.connection() as db:
        db.execute("INSERT INTO operator_credentials VALUES(1,?)", (credential_digest(operator),))
    with TestClient(
        create_app(model.actions, model.models, admin_origin=origin), base_url=origin
    ) as client:
        assert client.post("/admin/playground", json={"mode": "model"}).status_code in (401, 403)
        assert (
            client.post(
                "/admin/session", headers={"Origin": origin}, json={"token": model.token}
            ).status_code
            == 401
        )
        login = client.post("/admin/session", headers={"Origin": origin}, json={"token": operator})
        assert login.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}
        body = {
            "mode": "model",
            "model": "local-demo",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 64,
        }
        response = client.post("/admin/playground", headers=headers, json=body)
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "Local response"
        event = model.store.events()[-1]
        assert event.principal_id == "operator-playground"
        assert event.root_run_id == "operator-playground"
        for override in ("tenant_id", "principal_id", "root_run_id", "api_base"):
            assert (
                client.post(
                    "/admin/playground", headers=headers, json=body | {override: "other"}
                ).status_code
                == 422
            )
        feed = {
            "feed": {
                "feed_id": "local",
                "revision": 2,
                "indicators": [
                    {
                        "id": "deny-hello",
                        "kind": "literal_text",
                        "value": "Hello",
                        "stages": ["model_input"],
                    }
                ],
            },
            "expected_version": "local:1",
        }
        assert client.post("/admin/feed", headers=headers, json=feed).status_code == 200
        assert client.post("/admin/playground", headers=headers, json=body).status_code == 403
        assert len(model.provider.calls) == 1
        overview = client.get("/admin/overview").json()
        assert overview["budgets"]["model"]
        assert "chat.completions" in overview["coverage"]["enforced"]
        assert overview["services"]["model"] == "configured"


def proposal(arguments):
    return {
        "id": "call-mail",
        "type": "function",
        "function": {"name": "mail_send", "arguments": arguments},
    }


MAIL_TOOLS = [
    {"type": "function", "function": {"name": "mail_send", "parameters": {"type": "object"}}}
]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "arguments",
    ['{"body":"AGENTGATE_SECRET[fixture]"}', r'{"body":"AGENTGATE_\u0053ECRET[fixture]"}'],
)
def test_decoded_output_argument_secret_is_withheld_and_spent(model, stream, arguments):
    model.provider.content = None
    model.provider.tool_calls = [proposal(arguments)]
    response = model.call(stream=stream, tools=MAIL_TOOLS)
    assert response.status_code == 403
    assert response.json()["reason_codes"] == ["SECRET_IN_OUTPUT"]
    assert "tool_calls" not in response.text
    assert len(model.provider.calls) == 1
    assert model.store.events()[-1].event_type == "output_blocked"
    assert all(row["reserved"] == 0 for row in model.models.ledger.counters())


def test_decoded_input_argument_secret_never_reaches_provider(model):
    messages = [
        {
            "role": "assistant",
            "tool_calls": [proposal(r'{"body":"AGENTGATE_\u0053ECRET[fixture]"}')],
        },
        {"role": "tool", "tool_call_id": "call-mail", "content": "pending"},
    ]
    response = model.call(messages=messages)
    assert response.status_code == 403
    assert response.json()["reason_codes"] == ["SECRET_IN_INPUT"]
    assert model.provider.calls == []
    assert model.models.ledger.counters() == []


@pytest.mark.parametrize("incoming", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_decoded_argument_feed_indicator_cannot_be_escaped(model, incoming, stream):
    controls = live_controls(model)
    controls.activate_feed(
        ThreatFeed(
            revision=2,
            indicators=(Indicator(id="literal", kind="literal_text", value="badneedle"),),
        ),
        "local:1",
    )
    call = proposal(r'{"body":"b\u0061dneedle"}')
    options = {"stream": stream, "tools": MAIL_TOOLS}
    if incoming:
        options["messages"] = [{"role": "assistant", "tool_calls": [call]}]
    else:
        model.provider.content = None
        model.provider.tool_calls = [call]
    response = model.call(**options)
    assert response.status_code == 403
    assert response.json()["reason_codes"] == ["THREAT_FEED_BLOCKED"]
    assert len(model.provider.calls) == (0 if incoming else 1)
    assert "tool_calls" not in response.text


def test_argument_content_redaction_preserves_call_and_routing_fields(model):
    model.provider.content = None
    model.provider.tool_calls = [
        proposal(r'{"body":"Contact person\u0040example.org","subject":"Hi"}')
    ]
    response = model.call(tools=MAIL_TOOLS)
    assert response.status_code == 200
    call = response.json()["choices"][0]["message"]["tool_calls"][0]
    assert call["id"] == "call-mail" and call["function"]["name"] == "mail_send"
    assert json.loads(call["function"]["arguments"]) == {
        "body": "Contact [REDACTED_EMAIL]",
        "subject": "Hi",
    }
    assert response.json()["agentgate"]["decision"] == "redact"


def test_routing_fields_are_denied_instead_of_silently_redacted(model):
    model.provider.tool_calls = [proposal('{"recipient":"person@example.org","body":"test"}')]
    response = model.call(tools=MAIL_TOOLS)
    assert response.status_code == 403
    assert "tool_calls" not in response.text
    assert all(row["reserved"] == 0 for row in model.models.ledger.counters())


def test_private_provider_total_deadline_stops_a_trickling_response():
    class Trickle(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            try:
                for _ in range(10):
                    time.sleep(0.08)
                    self.wfile.write(b"x")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        provider = PrivateProvider(
            f"http://127.0.0.1:{server.server_port}/v1", "test-only", timeout=0.12
        )
        start = time.monotonic()
        with pytest.raises(httpx.ReadTimeout):
            provider.complete({})
        assert time.monotonic() - start < 0.55
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_email_in_argument_name_is_denied_without_renaming(model):
    model.provider.tool_calls = [proposal('{"person@example.org":"value"}')]
    response = model.call(tools=MAIL_TOOLS)
    assert response.status_code == 403
    assert "tool_calls" not in response.text
