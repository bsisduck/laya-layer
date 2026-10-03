import base64
import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_admin import ORIGIN
from test_admin import admin as admin
from test_budgets import enable
from test_gateway import harness as harness
from test_models import model as model

from agentgate.admin import playground_credential
from agentgate.admin_credentials import (
    CredentialRenewalError,
    playground_credential_status,
    renew_agent_credential,
    renew_playground_credential,
)
from agentgate.contracts import ActionRequest
from agentgate.model_config import ResourceLimits
from agentgate.models import ChatRequest
from agentgate.service import ActionService, GateError
from agentgate.storage import CredentialInvalid, StorageUnavailable, Store, credential_digest


@pytest.mark.parametrize("model", [False, True])
def test_epoch_zero_compatibility_and_separate_authority(admin, model):
    service = admin.gateway.service
    domain = (
        b"operator-model-playground-credential-v1"
        if model
        else b"operator-playground-credential-v1"
    )
    legacy = (
        base64.urlsafe_b64encode(hmac.new(service.audit_key, domain, hashlib.sha256).digest())
        .decode()
        .rstrip("=")
    )
    assert playground_credential(service, model=model) == legacy
    identity = service.store.resolve(credential_digest(legacy), service.clock())
    assert ("chat.completions" in identity.operations) is model
    assert ("mail.send" in identity.operations) is not model
    assert identity.root_run_id == identity.principal_id == "operator-playground"
    assert playground_credential(service, model=not model) != legacy


def test_explicit_playground_epoch_survives_restart_without_old_authority(admin):
    service = admin.gateway.service
    old = playground_credential(service)
    other = playground_credential(service, model=True)
    identity = service.store.resolve(credential_digest(old), service.clock())
    admin.gateway.now[0] += 86400
    assert playground_credential(service) == old  # No silent renewal.
    with pytest.raises(CredentialInvalid):
        service.store.resolve(credential_digest(old), service.clock())
    renewed = renew_playground_credential(service, expected_epoch=0)
    assert renewed == {
        "scope": "tools",
        "epoch": 1,
        "state": "active",
        "expires_at": service.clock() + 86400,
    }
    replacement = playground_credential(service)
    assert replacement != old
    assert service.store.resolve(credential_digest(replacement), service.clock()) == identity
    assert playground_credential(service, model=True) == other
    assert playground_credential_status(service, model=True)["state"] == "expired"
    restarted = ActionService(
        Store(service.store.path),
        service.policy,
        service.registry,
        service.executor,
        service.audit_key,
        clock=service.clock,
        controls=service.controls,
    )
    assert playground_credential(restarted) == replacement
    with pytest.raises(CredentialInvalid):
        restarted.store.resolve(credential_digest(old), service.clock())
    with service.store.connection() as db:
        assert (
            db.execute(
                "SELECT revoked FROM credentials WHERE digest=?", (credential_digest(old),)
            ).fetchone()[0]
            == 1
        )
        assert db.execute("SELECT COUNT(*) FROM credential_renewals").fetchone()[0] == 1
    for path in service.store.path.parent.glob("*.sqlite3*"):
        assert old.encode() not in path.read_bytes()
        assert replacement.encode() not in path.read_bytes()


def test_operator_routes_never_issue_on_read_or_bypass_csrf(admin):
    path = "/admin/playground/credential"
    renew = path + "/renew"
    for method, target in (("GET", path + "?scope=tools"), ("POST", renew)):
        assert admin.client.request(method, target).status_code in (401, 403)
        assert (
            admin.client.request(
                method,
                target,
                headers={"Origin": ORIGIN, "Authorization": f"Bearer {admin.gateway.token}"},
            ).status_code
            == 401
        )
    admin.login()
    assert admin.client.get(path + "?scope=tools").json() == {
        "scope": "tools",
        "epoch": 0,
        "state": "unissued",
        "expires_at": None,
    }
    for suffix in ("", "?scope=other", "?scope=tools&scope=model", "?scope=tools&token=x"):
        assert admin.client.get(path + suffix).status_code == 422
    body = {"scope": "tools", "expected_epoch": 0}
    for headers in ({"Origin": ORIGIN}, admin.headers() | {"Origin": "https://wrong.test"}):
        assert admin.client.post(renew, headers=headers, json=body).status_code == 403
    assert admin.client.post(renew, headers=admin.headers(), json=body).status_code == 404
    for bad_body in (body | {"token": "forbidden"}, body | {"expected_epoch": True}):
        assert admin.client.post(renew, headers=admin.headers(), json=bad_body).status_code == 422
    assert admin.gateway.executor.calls == []
    with admin.gateway.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] == 1


def test_operator_expired_renewal_replay_and_revocation(admin):
    service = admin.gateway.service
    old = playground_credential(service)
    admin.login()
    target = "/admin/playground/credential/renew"
    body = {"scope": "tools", "expected_epoch": 0}
    assert admin.client.post(target, headers=admin.headers(), json=body).status_code == 409
    admin.gateway.now[0] += 86400
    admin.login()
    response = admin.client.post(target, headers=admin.headers(), json=body)
    assert response.status_code == 200
    new = playground_credential(service)
    assert old not in response.text and new not in response.text
    assert set(response.json()) == {"scope", "epoch", "state", "expires_at"}
    assert response.headers["cache-control"] == "no-store"
    assert admin.client.post(target, headers=admin.headers(), json=body).status_code == 409
    service.store.revoke(new)
    admin.gateway.now[0] += 86400
    admin.login()
    body["expected_epoch"] = 1
    assert admin.client.post(target, headers=admin.headers(), json=body).status_code == 403
    assert playground_credential(service) == new
    assert playground_credential_status(service)["state"] == "revoked"
    assert admin.gateway.executor.calls == []


def test_playground_concurrent_cas_creates_one_epoch(admin):
    service = admin.gateway.service
    playground_credential(service)
    admin.gateway.now[0] += 86400

    def renew(_):
        try:
            return renew_playground_credential(service, expected_epoch=0)["epoch"]
        except CredentialRenewalError as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(renew, range(8)))
    assert results.count(1) == 1 and results.count("conflict") == 7
    assert playground_credential_status(service)["epoch"] == 1
    with service.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM credential_renewals").fetchone()[0] == 1


def test_agent_renewal_preserves_exact_scope_and_root_spend(harness):
    enable(harness, root_run=1)
    assert harness.read().status_code == 200
    counters = harness.store.budget_counters()
    old = harness.token
    harness.now[0] = 2000
    new = renew_agent_credential(harness.store, old, now=2000, expires_at=3000)
    assert new != old
    assert harness.store.resolve(credential_digest(new), 2000) == harness.identity
    assert harness.store.budget_counters() == counters
    assert harness.read().status_code == 401
    harness.token = new
    assert harness.read().status_code == 429
    assert len(harness.executor.calls) == 1
    with pytest.raises(CredentialRenewalError, match="revoked"):
        renew_agent_credential(harness.store, old, now=2000, expires_at=3000)


def test_playground_renewal_preserves_tool_root_spend(harness):
    enable(harness, root_run=1)
    service = harness.service
    token = playground_credential(service)
    request = ActionRequest(operation="documents.read", arguments={"document_id": "tenant-a-notes"})
    context = service.new_context()
    service.authenticate(context, token)
    assert service.execute(context, request).executed
    counters = harness.store.budget_counters()
    harness.now[0] += 86400
    renew_playground_credential(service, expected_epoch=0)
    assert harness.store.budget_counters() == counters
    context = service.new_context()
    service.authenticate(context, playground_credential(service))
    with pytest.raises(GateError) as error:
        service.execute(context, request)
    assert error.value.status_code == 429
    assert len(harness.executor.calls) == 1


@pytest.mark.parametrize("uncertain", [False, True])
def test_model_renewal_preserves_root_spend_and_uncertain_reservations(model, uncertain):
    import httpx

    model.limits(root_run=ResourceLimits(calls=1))
    now = [1000.0]
    model.actions.clock = lambda: now[0]
    service = model.actions
    if uncertain:
        model.provider.failure = httpx.ReadTimeout("fixture")
    token = playground_credential(service, model=True)
    request = ChatRequest(model="local-demo", messages=[{"role": "user", "content": "hello"}])
    context = service.new_context()
    service.authenticate(context, token)
    if uncertain:
        with pytest.raises(GateError):
            model.models.complete(context, request)
    else:
        model.models.complete(context, request)
    counters = model.models.ledger.counters()
    now[0] += 86400
    renew_playground_credential(service, model=True, expected_epoch=0)
    assert model.models.ledger.counters() == counters
    context = service.new_context()
    service.authenticate(context, playground_credential(service, model=True))
    with pytest.raises(GateError) as error:
        model.models.complete(context, request)
    assert error.value.status_code == 429
    assert len(model.provider.calls) == 1


def test_agent_concurrent_renewal_issues_once(harness):
    def renew(_):
        try:
            return renew_agent_credential(harness.store, harness.token, now=2000, expires_at=3000)
        except CredentialRenewalError as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=8) as pool:
        result = list(pool.map(renew, range(8)))
    assert result.count("revoked") == 7
    assert len([token for token in result if len(token) == 43]) == 1


@pytest.mark.parametrize("revoked", [False, True])
def test_agent_active_or_revoked_is_not_renewable(harness, revoked):
    if revoked:
        harness.store.revoke(harness.token)
    with pytest.raises(CredentialRenewalError, match="revoked" if revoked else "active"):
        renew_agent_credential(harness.store, harness.token, now=1000, expires_at=3000)
    with harness.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] == 1


@pytest.mark.parametrize("expires_at", [2000, 88401, float("inf"), float("nan"), True, "3000"])
def test_invalid_renewal_expiry_cannot_change_authority(harness, expires_at):
    with pytest.raises(ValueError):
        renew_agent_credential(harness.store, harness.token, now=2000, expires_at=expires_at)
    with harness.store.connection() as db:
        assert db.execute("SELECT revoked FROM credentials").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] == 1


def test_renewal_evidence_failure_rolls_back_all_changes(admin):
    service = admin.gateway.service
    old = playground_credential(service)
    admin.gateway.now[0] += 86400
    with service.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_renewal BEFORE INSERT ON credential_renewals "
            "BEGIN SELECT RAISE(FAIL,'fixture'); END"
        )
    with pytest.raises(StorageUnavailable):
        renew_playground_credential(service, expected_epoch=0)
    assert playground_credential_status(service)["epoch"] == 0
    assert playground_credential(service) == old
    with service.store.connection() as db:
        assert (
            db.execute(
                "SELECT revoked FROM credentials WHERE digest=?", (credential_digest(old),)
            ).fetchone()[0]
            == 0
        )
        assert db.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] == 2
        db.execute("DROP TRIGGER fail_renewal")
    assert renew_playground_credential(service, expected_epoch=0)["epoch"] == 1
