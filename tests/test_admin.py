import secrets
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from test_gateway import Harness
from test_gateway import harness as harness

from agentgate.admin import COOKIE, attach_admin_routes, bootstrap_operator
from agentgate.app import create_app
from agentgate.cli import initialize_demo
from agentgate.control_plane import ControlPlane
from agentgate.policy import Policy
from agentgate.storage import Store, credential_digest

ORIGIN = "https://operator.test"


@dataclass
class AdminHarness:
    client: TestClient
    gateway: Harness
    token: str

    def login(self):
        return self.client.post(
            "/admin/session", headers={"Origin": ORIGIN}, json={"token": self.token}
        )

    def headers(self):
        session = self.client.get("/admin/session").json()
        return {"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]}


@pytest.fixture
def admin(harness):
    app = create_app(harness.service)
    attach_admin_routes(app, harness.service, origin=ORIGIN)
    token = secrets.token_urlsafe(32)
    with harness.store.connection() as db:
        db.execute("INSERT INTO operator_credentials VALUES (1, ?)", (credential_digest(token),))
    with TestClient(app, base_url=ORIGIN) as client:
        yield AdminHarness(client, harness, token)


PROTECTED = [
    ("GET", "/admin/session"),
    ("DELETE", "/admin/session"),
    ("GET", "/admin/overview"),
    ("GET", "/admin/events"),
    ("GET", "/admin/policy"),
    ("POST", "/admin/policy/validate"),
    ("POST", "/admin/policy/activate"),
    ("GET", "/admin/feed"),
    ("POST", "/admin/feed"),
    ("POST", "/admin/playground"),
    ("GET", "/admin/audit/export"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_agent_credentials_cannot_access_any_admin_route(admin, method, path):
    result = admin.client.request(
        method, path, headers={"Origin": ORIGIN, "Authorization": f"Bearer {admin.gateway.token}"}
    )
    assert result.status_code == 401
    assert result.headers["cache-control"] == "no-store"
    assert admin.gateway.executor.calls == []
    assert admin.gateway.store.events() == []


def test_agent_token_cannot_login_and_operator_token_cannot_execute(admin):
    result = admin.client.post(
        "/admin/session", headers={"Origin": ORIGIN}, json={"token": admin.gateway.token}
    )
    assert result.status_code == 401
    result = admin.client.post(
        "/v1/actions/execute",
        headers={"Authorization": f"Bearer {admin.token}"},
        json={"operation": "documents.read", "arguments": {"document_id": "tenant-a-notes"}},
    )
    assert result.status_code == 401
    assert admin.gateway.executor.calls == []


def test_session_cookie_introspection_rotation_expiry_and_logout_replay(admin):
    login = admin.login()
    assert login.status_code == 200
    header = login.headers["set-cookie"]
    for attribute in ("HttpOnly", "SameSite=strict", "Secure", "Path=/admin", "Max-Age=900"):
        assert attribute in header
    old = admin.client.cookies.get(COOKIE)
    assert admin.token not in login.text
    assert admin.client.get("/admin/session").json() == login.json()
    assert admin.login().status_code == 200
    rotated = admin.client.cookies.get(COOKIE)
    assert old != rotated
    result = admin.client.get("/admin/session", headers={"Cookie": f"{COOKIE}={old}"})
    assert result.status_code == 401
    header_csrf = admin.headers()
    assert admin.client.delete("/admin/session", headers=header_csrf).status_code == 200
    assert (
        admin.client.get("/admin/session", headers={"Cookie": f"{COOKIE}={rotated}"}).status_code
        == 401
    )
    assert admin.client.delete("/admin/session", headers=header_csrf).status_code == 401
    assert admin.login().status_code == 200
    admin.gateway.now[0] += 900
    assert admin.client.get("/admin/session").status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://evil.invalid"},
        {"Origin": "null"},
        {"Origin": ORIGIN, "Host": "evil.invalid"},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "same-site"},
    ],
)
def test_login_requires_exact_configured_origin_and_host(admin, headers):
    result = admin.client.post("/admin/session", headers=headers, json={"token": admin.token})
    assert result.status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": ORIGIN},
        {"Origin": ORIGIN, "X-CSRF-Token": "wrong"},
        {"Origin": "https://evil.invalid", "X-CSRF-Token": "wrong"},
    ],
)
def test_cookie_writes_require_csrf_and_origin(admin, headers):
    admin.login()
    result = admin.client.post(
        "/admin/playground",
        headers=headers,
        json={"mode": "document", "document_id": "tenant-a-notes"},
    )
    assert result.status_code == 403
    assert admin.gateway.executor.calls == []


def test_playground_uses_server_owned_scope_and_real_document_enforcement(admin):
    admin.login()
    headers = admin.headers()

    def play(document, **overrides):
        return admin.client.post(
            "/admin/playground",
            headers=headers,
            json={"mode": "document", "document_id": document, **overrides},
        )

    assert play("tenant-a-notes", tenant_id="tenant-b").status_code == 422
    assert play("tenant-b-notes").status_code == 403
    assert admin.gateway.executor.calls == []
    assert play("tenant-a-notes").json()["decision"] == "allow"
    assert play("tenant-a-contact").json()["decision"] == "redact"
    assert play("tenant-a-leak").json()["decision"] == "deny"
    event = admin.gateway.store.events()[-1]
    assert event.principal_id == "operator-playground"
    assert event.tenant_id == "tenant-a"
    assert event.root_run_id == "operator-playground"
    with admin.gateway.store.connection() as db:
        assert db.execute("SELECT count(*) FROM credentials").fetchone()[0] == 2


def test_private_bootstrap_never_overwrites_and_preserves_agent_auth(tmp_path):
    directory = tmp_path / "state"
    initialize_demo(directory)
    original = (directory / "client.token").read_bytes()
    bootstrap_operator(directory, Policy(policy_id="test", revision=1))
    token = (directory / "operator.token").read_text()
    assert token.encode() != original
    assert (directory / "operator.token").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        bootstrap_operator(directory, Policy(policy_id="test", revision=1))
    assert (directory / "operator.token").read_text() == token
    assert (directory / "client.token").read_bytes() == original
    with Store(directory / "agentgate.sqlite3").connection() as db:
        assert db.execute("SELECT digest FROM operator_credentials").fetchone()[
            0
        ] == credential_digest(token)
        assert db.execute("SELECT count(*) FROM credentials").fetchone()[0] == 1


def test_policy_validation_activation_replay_and_last_good(admin):
    admin.login()
    headers = admin.headers()
    current = admin.client.get("/admin/policy").json()
    candidate = current["policy"] | {"revision": 2}
    result = admin.client.post(
        "/admin/policy/validate", headers=headers, json={"policy": candidate}
    )
    assert result.json() == {"valid": True, "version": "test:2"}
    assert admin.client.get("/admin/policy").json() == current
    result = admin.client.post(
        "/admin/policy/activate",
        headers=headers,
        json={"policy": candidate, "expected_version": "test:1"},
    )
    assert result.status_code == 200
    assert (
        admin.client.post(
            "/admin/policy/activate",
            headers=headers,
            json={"policy": candidate, "expected_version": "test:1"},
        ).status_code
        == 409
    )
    for invalid in (
        candidate | {"unknown": True},
        candidate | {"revision": -1},
        candidate | {"semantic_required": True},
    ):
        assert (
            admin.client.post(
                "/admin/policy/activate",
                headers=headers,
                json={"policy": invalid, "expected_version": "test:2"},
            ).status_code
            == 422
        )
    assert admin.gateway.service.policy.version == "test:2"
    assert ControlPlane(admin.gateway.store).snapshot().policy.version == "test:2"


def test_feed_http_validation_enforcement_and_restart(admin):
    admin.login()
    headers = admin.headers()
    feed = {
        "feed_id": "local",
        "revision": 2,
        "indicators": [
            {
                "id": "deny-doc",
                "kind": "literal_text",
                "value": "tenant-a-notes",
                "stages": ["tool_action"],
            }
        ],
    }
    payload = {"feed": feed, "expected_version": "local:1"}
    assert admin.client.post("/admin/feed", headers=headers, json=payload).status_code == 200
    assert admin.gateway.read().json()["reason_codes"] == ["THREAT_FEED_BLOCKED"]
    assert admin.gateway.executor.calls == []
    assert admin.client.post("/admin/feed", headers=headers, json=payload).status_code == 409
    for invalid in [
        feed | {"indicators": [feed["indicators"][0] | {"kind": "python", "value": "eval(x)"}]},
        feed | {"indicators": feed["indicators"] * 129},
        feed | {"revision": 1},
        feed | {"unknown": True},
    ]:
        result = admin.client.post(
            "/admin/feed", headers=headers, json={"feed": invalid, "expected_version": "local:2"}
        )
        assert result.status_code in (409, 422)
    assert admin.client.get("/admin/feed").json()["version"] == "local:2"
    assert ControlPlane(admin.gateway.store).snapshot().feed.version == "local:2"


@pytest.mark.parametrize(
    "body,status",
    [
        (b'{"token":"x","token":"y"}', 422),
        (b'{"x":NaN}', 422),
        (b"[" * 30 + b"0" + b"]" * 30, 422),
        (b"\xff", 422),
        (b"x" * 1025, 413),
    ],
)
def test_bounded_parser_rejects_without_echoing_input(admin, body, status):
    result = admin.client.post(
        "/admin/session",
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
        content=body,
    )
    assert result.status_code == status
    assert set(result.json()) == {"detail"}
    assert len(result.text) < 150
    assert "set-cookie" not in result.headers


def test_metadata_is_minimized_and_export_schema_is_unchanged(admin):
    import json

    from agentgate.audit_export import export_page

    admin.login()
    for document in ("tenant-a-notes", "tenant-a-contact", "tenant-a-leak"):
        admin.client.post(
            "/admin/playground",
            headers=admin.headers(),
            json={"mode": "document", "document_id": document},
        )
    result = admin.client.get("/admin/overview").json()
    assert result["counts"] == {"allow": 1, "redact": 1, "deny": 1, "pending": None}
    assert result["latency"]["status"] == "unknown"
    assert result["count_window"]["audit_rows"] == 6
    timeline = admin.client.get("/admin/events?limit=2").json()
    assert len(timeline["events"]) == 2
    assert timeline["events"][0]["event_type"] == "output_blocked"
    for event in timeline["events"]:
        assert "payload_digest" not in event
        assert "semantic" not in event
        assert "result" not in event
    response = admin.client.get("/admin/audit/export?tenant=tenant-a&limit=3")
    page = export_page(admin.gateway.store.path, tenant="tenant-a", limit=3)
    assert response.text == "\n".join(page.lines) + "\n"
    assert json.loads(response.headers["x-agentgate-cursor"]) == page.metadata()
    assert "attachment" in response.headers["content-disposition"]
    assert "feed_version" not in json.loads(response.text.splitlines()[0])
    cursor = page.metadata()
    response2 = admin.client.get(
        f"/admin/audit/export?tenant=tenant-a&after_sequence={cursor['next_after_sequence']}&through_sequence={cursor['through_sequence']}&limit=3"
    )
    assert len(response2.text.splitlines()) == 3
    for text in (
        admin.token,
        admin.gateway.token,
        "AGENTGATE_SECRET[",
        "analyst@demo.internal",
        "quarterly notes",
    ):
        assert text not in response.text
        assert text not in str(timeline)


@pytest.mark.parametrize(
    "path",
    [
        "/admin/events?limit=1001",
        "/admin/events?limit=0",
        "/admin/events?limit=1&limit=2",
        "/admin/policy?token=anything",
        "/admin/audit/export",
        "/admin/audit/export?tenant=tenant-a&unattributed=true",
        "/admin/audit/export?unattributed=false",
        "/admin/audit/export?unattributed=true&format=csv",
        "/admin/audit/export?unattributed=true&through_sequence=999999",
    ],
)
def test_admin_query_limits_and_export_selection(admin, path):
    admin.login()
    assert admin.client.get(path).status_code == 422


def test_unavailable_tools_are_explicit_and_real_hook_is_tenant_scoped(admin):
    admin.login()
    assert admin.client.get("/admin/approvals?tenant_id=tenant-a").status_code == 503
    assert admin.client.get("/admin/outbox?tenant_id=tenant-a").status_code == 503
    calls = []

    class Tools:
        def list_approvals(self, **kwargs):
            calls.append(("list", kwargs))
            return [{"action_id": "act-test", "fingerprint": "a" * 64}]

        def outbox(self, **kwargs):
            calls.append(("outbox", kwargs))
            return [{"message_id": "message-test"}]

        def decide(self, **kwargs):
            calls.append(("decide", kwargs))
            return {"status": "approved"}

    admin.gateway.service.tools = Tools()
    assert admin.client.get("/admin/approvals").status_code == 422
    assert admin.client.get("/admin/approvals?tenant_id=tenant-a&limit=2").json() == {
        "approvals": [{"action_id": "act-test", "fingerprint": "a" * 64}]
    }
    assert admin.client.get("/admin/outbox?tenant_id=tenant-a").json() == {
        "messages": [{"message_id": "message-test"}]
    }
    payload = {"tenant_id": "tenant-a", "fingerprint": "a" * 64, "approve": True}
    assert (
        admin.client.post(
            "/admin/approvals/act-test/decision",
            headers=admin.headers(),
            json=payload | {"actor": "forged"},
        ).status_code
        == 422
    )
    assert admin.client.post(
        "/admin/approvals/act-test/decision", headers=admin.headers(), json=payload
    ).json() == {"status": "approved"}
    assert calls == [
        ("list", {"tenant_id": "tenant-a", "limit": 2}),
        ("outbox", {"tenant_id": "tenant-a", "limit": 100}),
        (
            "decide",
            {
                "tenant_id": "tenant-a",
                "action_id": "act-test",
                "fingerprint": "a" * 64,
                "approve": True,
                "actor": "operator",
            },
        ),
    ]


def test_session_secrets_not_persisted_and_capacity_is_bounded(admin):
    cookies = []
    for _ in range(32):
        admin.client.cookies.clear()
        assert admin.login().status_code == 200
        cookies.append(admin.client.cookies.get(COOKIE))
    admin.client.cookies.clear()
    assert admin.login().status_code == 429
    with admin.gateway.store.connection() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM operator_sessions").fetchall()]
        assert len(rows) == 32
    assert admin.token not in str(rows)
    for cookie in cookies:
        assert cookie not in str(rows)
    admin.gateway.now[0] += 900
    assert admin.login().status_code == 200


def test_bootstrap_refuses_existing_files_symlinks_and_public_directory(tmp_path):
    directory = tmp_path / "state"
    initialize_demo(directory)
    policy = Policy(policy_id="test", revision=1)
    target = tmp_path / "target"
    target.write_text("do not overwrite")
    (directory / "operator.token").symlink_to(target)
    with pytest.raises(FileExistsError):
        bootstrap_operator(directory, policy)
    assert target.read_text() == "do not overwrite"
    with Store(directory / "agentgate.sqlite3").connection() as db:
        assert db.execute("SELECT count(*) FROM operator_credentials").fetchone()[0] == 0
    (directory / "operator.token").unlink()
    directory.chmod(0o755)
    with pytest.raises(ValueError):
        bootstrap_operator(directory, policy)


def test_storage_outage_is_safe_admin_error_and_no_action_dispatch(admin, monkeypatch):
    from agentgate.storage import StorageUnavailable

    admin.login()

    def fail():
        raise StorageUnavailable

    monkeypatch.setattr(admin.gateway.store, "connection", fail)
    assert admin.client.get("/admin/overview").status_code == 503
    response = admin.gateway.read()
    assert response.status_code == 503
    assert response.json()["reason_codes"] == ["AUDIT_UNAVAILABLE"]
    assert admin.gateway.executor.calls == []


def test_duplicate_security_headers_and_non_ascii_csrf_are_denied(admin):
    admin.login()
    csrf = admin.headers()["X-CSRF-Token"]
    for headers in [
        [("Origin", ORIGIN), ("Origin", ORIGIN), ("X-CSRF-Token", csrf)],
        [("Origin", ORIGIN), ("X-CSRF-Token", csrf), ("X-CSRF-Token", csrf)],
        [(b"Origin", ORIGIN.encode()), (b"X-CSRF-Token", b"\xff")],
    ]:
        response = admin.client.delete("/admin/session", headers=headers)
        assert response.status_code == 403
    assert admin.client.get("/admin/session").status_code == 200


def test_stable_playground_credential_survives_retry_restart_and_respects_revocation(admin):
    from agentgate.admin import playground_credential
    from agentgate.service import ActionService, GateError

    service = admin.gateway.service
    token = playground_credential(service)
    assert playground_credential(service) == token
    restarted = ActionService(
        service.store,
        service.policy,
        service.registry,
        service.executor,
        service.audit_key,
        clock=service.clock,
        controls=service.controls,
    )
    assert playground_credential(restarted) == token
    with service.store.connection() as db:
        row = db.execute(
            "SELECT identity, expires_at FROM credentials WHERE digest=?",
            (credential_digest(token),),
        ).fetchone()
        assert row["expires_at"] == service.clock() + 86400
        assert '"mail.send"' in row["identity"]
    service.store.revoke(token)
    assert playground_credential(restarted) == token
    with pytest.raises(GateError) as error:
        restarted.authenticate(restarted.new_context(), token)
    assert error.value.status_code == 401


def test_stable_playground_credential_expiry_is_never_silently_extended(admin):
    from agentgate.admin import playground_credential
    from agentgate.service import GateError

    service = admin.gateway.service
    token = playground_credential(service)
    admin.gateway.now[0] += 86400
    assert playground_credential(service) == token
    with pytest.raises(GateError) as error:
        service.authenticate(service.new_context(), token)
    assert error.value.status_code == 401


def test_memory_mail_adapters_forward_exact_payload_with_same_internal_credential(
    admin, monkeypatch
):
    # Adapter contract fixture only. Real mail approval/execution belongs to PR19.
    from agentgate.contracts import ActionResponse, Reason

    admin.login()
    calls = []

    def execute(context, action):
        calls.append((context.identity, context.credential_digest, action))
        return ActionResponse(
            status="completed",
            action_id=context.action_id,
            trace_id=context.trace_id,
            decision="allow",
            reason_codes=(Reason.ALLOWED,),
            policy_version="test:1",
            executed=False,
        )

    memory = {"mode": "memory", "query": "quarterly", "limit": 2}
    mail = {
        "mode": "mail",
        "recipient": "analyst@demo.internal",
        "subject": "subject",
        "body": "exact body",
        "idempotency_key": "mail-key",
    }
    assert (
        admin.client.post("/admin/playground", headers=admin.headers(), json=memory).status_code
        == 503
    )
    admin.gateway.service.tools = object()
    monkeypatch.setattr(admin.gateway.service, "execute", execute)
    for payload in (memory, mail, mail):
        assert (
            admin.client.post(
                "/admin/playground", headers=admin.headers(), json=payload
            ).status_code
            == 200
        )
    assert len({digest for _, digest, _ in calls}) == 1
    assert all(
        identity.tenant_id == "tenant-a" and identity.root_run_id == "operator-playground"
        for identity, _, _ in calls
    )
    assert calls[0][2].operation == "memory.query"
    assert calls[0][2].arguments == {"query": "quarterly", "limit": 2}
    assert calls[1][2].operation == "mail.send"
    assert calls[1][2].arguments == {k: v for k, v in mail.items() if k != "mode"}
    assert calls[1][2] == calls[2][2]
    assert (
        admin.client.post(
            "/admin/playground", headers=admin.headers(), json=memory | {"limit": 11}
        ).status_code
        == 422
    )
    assert admin.client.get("/admin/approvals?tenant_id=tenant-a&limit=101").status_code == 422


@pytest.mark.parametrize(
    "state,status",
    [
        ("pending", 202),
        ("approved", 202),
        ("expired", 410),
        ("denied", 403),
        ("consumed", 200),
        (None, 200),
    ],
)
def test_forwarded_tool_response_http_status(state, status):
    from types import SimpleNamespace

    from agentgate.app import response_status

    assert response_status(SimpleNamespace(action_state=state)) == status
