"""Actual admin/session/storage boundary, without classifier or provider inference."""

import secrets

import pytest
from fastapi.testclient import TestClient
from test_gateway import harness as harness

from agentgate.admin import COOKIE, MAX_SESSIONS
from agentgate.app import create_app
from agentgate.storage import credential_digest

ORIGIN = "http://127.0.0.1:8765"
ADDRESS = ("127.0.0.1", 8765)


@pytest.fixture
def local(harness):
    app = create_app(
        harness.service, admin_origin=ORIGIN, local_console=True, serving_address=ADDRESS
    )
    token = secrets.token_urlsafe(32)
    with harness.store.connection() as db:
        db.execute("INSERT INTO operator_credentials VALUES (1, ?)", (credential_digest(token),))
    # TestClient's server address comes from base_url, just like the ASGI wire transport.
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, harness, token


def bootstrap(client, **kwargs):
    return client.post("/admin/session/bootstrap", headers={"Origin": ORIGIN}, json={}, **kwargs)


def effects(harness):
    with harness.store.connection() as db:
        tables = [
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] not in ("operator_sessions", "health_probe", "sqlite_sequence")
        ]
        return {
            table: [tuple(row) for row in db.execute(f'SELECT * FROM "{table}"')]
            for table in tables
        }


def test_bootstrap_cookie_restore_csrf_expiry_and_revocation(local):
    client, harness, token = local
    before = effects(harness)
    assert client.get("/admin/config").json() == {"mode": "local"}
    assert client.get("/admin/overview").status_code == 401
    result = bootstrap(client)
    assert result.status_code == 200
    assert set(result.json()) == {"authenticated", "expires_at", "csrf_token"}
    assert token not in result.text and harness.token not in result.text
    for value in ("HttpOnly", "SameSite=strict", "Path=/admin", "Max-Age=900"):
        assert value in result.headers["set-cookie"]
    assert "Secure" not in result.headers["set-cookie"]
    cookie = client.cookies.get(COOKIE)
    assert bootstrap(client).json() == result.json()
    assert client.cookies.get(COOKIE) == cookie  # No rolling expiry or rotation.
    assert client.get("/admin/session").json() == result.json()
    assert client.get("/admin/overview").status_code == 200
    play = {"mode": "document", "document_id": "tenant-a-notes"}
    assert (
        client.post("/admin/playground", headers={"Origin": ORIGIN}, json=play).status_code == 403
    )
    assert effects(harness) == before and harness.executor.calls == []
    headers = {"Origin": ORIGIN, "X-CSRF-Token": result.json()["csrf_token"]}
    assert client.delete("/admin/session", headers=headers).status_code == 200
    assert client.get("/admin/session", headers={"Cookie": f"{COOKIE}={cookie}"}).status_code == 401
    renewed = bootstrap(client)
    harness.now[0] += 900
    assert (
        client.post(
            "/admin/playground",
            headers={"Origin": ORIGIN, "X-CSRF-Token": renewed.json()["csrf_token"]},
            json=play,
        ).status_code
        == 401
    )
    assert bootstrap(client).status_code == 200
    assert effects(harness) == before and harness.executor.calls == []
    assert (
        client.post(
            "/v1/actions/execute",
            json={"operation": "documents.read", "arguments": {"document_id": "tenant-a-notes"}},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/actions/execute",
            headers={"Authorization": f"Bearer {client.cookies.get(COOKIE)}"},
            json={"operation": "documents.read", "arguments": {"document_id": "tenant-a-notes"}},
        ).status_code
        == 401
    )
    assert harness.executor.calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "null"},
        {"Origin": "http://evil.invalid:8765"},
        {"Origin": "http://127.0.0.1:8766"},
        {"Origin": "https://127.0.0.1:8765"},
        {"Origin": ORIGIN, "Host": "rebind.invalid:8765"},
        {"Origin": ORIGIN, "Host": "127.0.0.1:8766"},
        {"Origin": ORIGIN, "Host": "localhost:8765"},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "same-site"},
        {"Origin": ORIGIN, "Forwarded": "for=127.0.0.1;host=127.0.0.1:8765"},
        {"Origin": ORIGIN, "X-Forwarded-Host": "127.0.0.1:8765"},
        {"Origin": ORIGIN, "X-Forwarded-For": "127.0.0.1"},
        {"Origin": ORIGIN, "X-Forwarded-Proto": "http"},
        [("Origin", ORIGIN), ("Origin", ORIGIN)],
        [("Origin", ORIGIN), ("Host", "127.0.0.1:8765"), ("Host", "127.0.0.1:8765")],
        [("Origin", ORIGIN), ("Sec-Fetch-Site", "same-origin"), ("Sec-Fetch-Site", "same-origin")],
        [("Origin", ORIGIN), ("X-CSRF-Token", "a"), ("X-CSRF-Token", "a")],
        [("Origin", ORIGIN), ("Authorization", "a"), ("Authorization", "a")],
    ],
)
def test_invalid_browser_boundary_has_zero_effects(local, headers):
    client, harness, _ = local
    before = effects(harness)
    assert client.post("/admin/session/bootstrap", headers=headers, json={}).status_code == 403
    with harness.store.connection() as db:
        assert db.execute("SELECT count(*) FROM operator_sessions").fetchone()[0] == 0
    assert effects(harness) == before and harness.executor.calls == []


@pytest.mark.parametrize(
    "body,status",
    [
        (b"", 422),
        (b"{", 422),
        (b"[]", 422),
        (b"null", 422),
        (b'{"token":"hidden"}', 422),
        (b'{"x":1,"x":2}', 422),
        (b" " * 1025, 413),
    ],
)
def test_bootstrap_body_is_bounded_and_empty(local, body, status):
    client, harness, _ = local
    before = effects(harness)
    assert (
        client.post(
            "/admin/session/bootstrap",
            headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            content=body,
        ).status_code
        == status
    )
    with harness.store.connection() as db:
        assert db.execute("SELECT count(*) FROM operator_sessions").fetchone()[0] == 0
    assert effects(harness) == before


def test_get_query_cookie_duplicate_and_capacity(local):
    client, harness, _ = local
    assert client.get("/admin/session/bootstrap").status_code == 405
    assert (
        client.post("/admin/session/bootstrap?x=1", headers={"Origin": ORIGIN}, json={}).status_code
        == 422
    )
    assert (
        client.post(
            "/admin/session/bootstrap",
            headers={"Origin": ORIGIN, "Cookie": f"{COOKIE}=a; {COOKIE}=b"},
            json={},
        ).status_code
        == 401
    )
    for _ in range(MAX_SESSIONS):
        client.cookies.clear()
        assert bootstrap(client).status_code == 200
    client.cookies.clear()
    assert bootstrap(client).status_code == 429
    with harness.store.connection() as db:
        assert db.execute("SELECT count(*) FROM operator_sessions").fetchone()[0] == MAX_SESSIONS
    assert harness.executor.calls == []


def test_default_disabled_and_runtime_socket_mismatch(harness):
    normal = create_app(harness.service, admin_origin=ORIGIN)
    with TestClient(normal, base_url=ORIGIN) as client:
        assert client.get("/admin/config").json() == {"mode": "credential"}
        assert bootstrap(client).status_code == 401
    local = create_app(
        harness.service, admin_origin=ORIGIN, local_console=True, serving_address=ADDRESS
    )
    with TestClient(local, base_url="http://192.0.2.1:8765") as client:
        assert client.get("/admin/config", headers={"Host": "127.0.0.1:8765"}).status_code == 403
        assert (
            client.post(
                "/admin/session/bootstrap",
                headers={"Host": "127.0.0.1:8765", "Origin": ORIGIN},
                json={},
            ).status_code
            == 403
        )
    assert harness.executor.calls == []


@pytest.mark.parametrize(
    "origin,address",
    [
        (ORIGIN, None),
        (ORIGIN, ("0.0.0.0", 8765)),
        (ORIGIN, ("localhost", 8765)),
        ("http://localhost:8765", ADDRESS),
        ("https://remote.invalid:8765", ADDRESS),
        ("http://127.1:8765", ADDRESS),
        (ORIGIN + "/", ADDRESS),
        (ORIGIN + "?x=1", ADDRESS),
        ("http://127.0.0.1", ADDRESS),
        (ORIGIN, ("127.0.0.1", 8766)),
        ("http://user@127.0.0.1:8765", ADDRESS),
        ("http://2130706433:8765", ADDRESS),
    ],
)
def test_invalid_local_serving_configuration_refused(harness, origin, address):
    with pytest.raises(ValueError):
        create_app(
            harness.service, admin_origin=origin, local_console=True, serving_address=address
        )
