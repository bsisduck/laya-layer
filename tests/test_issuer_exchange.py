"""Generated-key person-token unit/functional/wire evidence; provider is a fixture."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from test_authority import action, chat, config, decide, mail, resume
from test_gateway import harness as harness
from test_models import ObservedProvider

from agentgate.app import create_app
from agentgate.authority import issue_child, provision_subject, subject
from agentgate.authority_contracts import HumanSubject, parse_binding, parse_human
from agentgate.issuer_exchange import exchange, revoke_subject
from agentgate.issuer_trust import TrustConfig, import_trust, subject_id
from agentgate.model_config import ModelPolicy
from agentgate.models import ModelService
from agentgate.storage import CredentialInvalid, credential_digest

OPS = ("documents.read", "memory.query", "mail.send", "chat.completions")


@pytest.fixture
def issuer(harness):
    h = harness
    h.identity = h.identity.model_copy(update={"operations": OPS})
    parent = h.store.issue(h.identity, 2000.0)
    h.token = parent
    h.service.policy = h.service.policy.model_copy(
        update={"delegation": config(), "models": ModelPolicy()}
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {
        "kid": "fixture-key",
        "alg": "RS256",
        "use": "sig",
    }
    trust = TrustConfig.model_validate_json(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "fixture-issuer",
                        "issuer": "https://issuer.invalid/people",
                        "audience": "agentgate-exchange",
                        "keys": [jwk],
                        "parents": [
                            {
                                "parent": credential_digest(parent),
                                "agent_id": h.identity.agent_id,
                                "tenant_id": h.identity.tenant_id,
                                "client_id": "fixture-client",
                            }
                        ],
                        "tenants": [{"value": "signed-tenant", "tenant_id": "tenant-a"}],
                        "groups": [
                            {"value": "employees", "roles": ["employee-hr"], "department": "HR"},
                            {"value": "agents", "roles": ["analyst"], "department": "HR"},
                        ],
                    }
                ]
            }
        )
    )
    import_trust(h.store, trust, 0, h.service.clock)
    provider = ObservedProvider(h.store)
    models = ModelService(h.service, provider)
    with TestClient(
        create_app(h.service, models, enable_mcp=True), base_url="http://localhost"
    ) as client:
        h.client = client
        yield h, parent, key, trust, provider


def signed(f, **changes):
    h, _, key, _, _ = f
    claims = {
        "iss": "https://issuer.invalid/people",
        "sub": "exact-person",
        "aud": "agentgate-exchange",
        "exp": int(h.now[0]) + 250,
        "iat": int(h.now[0]),
        "nbf": int(h.now[0]),
        "auth_time": int(h.now[0]),
        "idtyp": "user",
        "client_id": "fixture-client",
        "tid": "signed-tenant",
        "groups": ["employees"],
    } | changes
    return jwt.encode(
        claims, key, algorithm="RS256", headers={"kid": "fixture-key", "typ": "at+jwt"}
    )


def request(f, token=None):
    h, parent, *_ = f
    return h.client.post(
        "/v1/authority/exchange",
        headers={"Authorization": f"Bearer {parent}"},
        json={"access_token": token or signed(f)},
    )


def child(f, **changes):
    response = request(f, signed(f, **changes))
    assert response.status_code == 200, response.status_code
    return response.json()["token"]


def context(f):
    h, parent, *_ = f
    ctx = h.service.new_context()
    h.service.authenticate(ctx, parent)
    return ctx


def rows(f):
    with f[0].store.connection() as db:
        return tuple(
            db.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
            for name in (
                "human_subjects",
                "credentials",
                "delegated_bindings",
                "issuer_assertion_order",
            )
        )


def test_unit_exact_subject_pairs_and_versioned_local_bytes():
    assert subject_id("a", "bc") != subject_id("ab", "c")
    assert subject_id("a", "x") != subject_id("a", "X")
    assert subject_id("é", "x") != subject_id("e\u0301", "x")
    local = HumanSubject(
        subject_id="old", tenant_id="tenant-a", roles=("analyst",), department="HR", revision=1
    )
    raw = local.model_dump_json()
    assert parse_human(raw).model_dump_json() == raw
    assert set(json.loads(raw)) == {
        "version",
        "subject_id",
        "provenance",
        "tenant_id",
        "roles",
        "department",
        "revision",
        "revoked",
        "assertion_deadline",
    }


def test_functional_exchange_actual_intersection_and_accounting(issuer):
    h, parent, _, _, provider = issuer
    h.token = child(issuer)
    assert h.read().status_code == 200
    before = len(h.executor.calls)
    assert h.read("tenant-a-contact").status_code == 403
    assert len(h.executor.calls) == before
    assert chat(h).status_code == 200
    before = len(provider.calls)
    assert chat(h, "finance-model").status_code == 403
    assert len(provider.calls) == before
    pending = mail(h).json()
    assert pending["action_state"] == "pending"
    decide(h, pending["action_id"])
    assert resume(h, pending["action_id"]).json()["executed"]
    with h.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM tool_outbox").fetchone()[0] == 1
        row = db.execute(
            "SELECT identity FROM credentials WHERE digest=?", (credential_digest(h.token),)
        ).fetchone()
        assert json.loads(row[0]) == h.identity.model_dump(mode="json")
    event = next(e for e in h.store.events() if e.authority)
    assert event.authority["issuer_id"] == "fixture-issuer"
    assert event.authority["trust_version"] == 1
    assert event.authority["accounting_principal"] == h.identity.principal_id
    assert "exact-person" not in json.dumps(event.model_dump(mode="json"))
    assert request(issuer).headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://wrong.invalid"},
        {"aud": "other"},
        {"aud": ["agentgate-exchange"]},
        {"idtyp": "app"},
        {"client_id": "wrong"},
        {"client_id": None},
        {"sub": ""},
        {"exp": 1000},
        {"exp": True},
        {"exp": 1200.1},
        {"iat": True},
        {"iat": 900},
        {"iat": 1010},
        {"nbf": 1010},
        {"auth_time": 1},
        {"auth_time": 1010},
        {"tid": "unmapped"},
        {"groups": ["unmapped"]},
        {"groups": "employees"},
        {"groups": ["employees"] * 33},
        {"groups": ["employees", "employees"]},
        {"azp": "fixture-client"},
        {"unexpected": "claim"},
        {"sub": ["person"]},
    ],
)
def test_functional_malformed_machine_stale_unmapped_fail_closed(issuer, changes):
    before = rows(issuer)
    response = request(issuer, signed(issuer, **changes))
    assert response.status_code == 401
    assert response.json() == {"reason": "EXCHANGE_DENIED"}
    assert rows(issuer) == before
    assert issuer[0].executor.calls == [] and issuer[4].calls == []


@pytest.mark.parametrize(
    "missing",
    ["iss", "sub", "aud", "exp", "iat", "nbf", "auth_time", "idtyp", "client_id", "tid", "groups"],
)
def test_functional_mandatory_claims(issuer, missing):
    payload = jwt.decode(
        signed(issuer),
        issuer[2].public_key(),
        algorithms=["RS256"],
        options={
            "verify_aud": False,
            "verify_exp": False,
            "verify_iat": False,
            "verify_nbf": False,
        },
    )
    del payload[missing]
    token = jwt.encode(
        payload, issuer[2], algorithm="RS256", headers={"kid": "fixture-key", "typ": "at+jwt"}
    )
    assert request(issuer, token).status_code == 401
    assert rows(issuer)[0] == 0


def test_functional_unchanged_refresh_keeps_consent_revision_and_old_freshness(issuer):
    h, *_ = issuer
    old_token = child(issuer)
    h.token = old_token
    pending = mail(h).json()
    with h.store.connection() as db:
        old_record = db.execute("SELECT record FROM human_subjects").fetchone()[0]
        old_binding = db.execute("SELECT binding FROM delegated_bindings").fetchone()[0]
        consent = db.execute("SELECT binding FROM action_authority").fetchone()[0]
    h.now[0] += 10
    newer = child(issuer)
    with h.store.connection() as db:
        assert db.execute("SELECT record FROM human_subjects").fetchone()[0] == old_record
        assert (
            db.execute(
                "SELECT binding FROM delegated_bindings WHERE child_digest=?",
                (credential_digest(old_token),),
            ).fetchone()[0]
            == old_binding
        )
        assert db.execute("SELECT binding FROM action_authority").fetchone()[0] == consent
        assert db.execute("SELECT assertion_iat FROM issuer_assertion_order").fetchone()[0] == 1010
    decide(h, pending["action_id"])
    assert resume(h, pending["action_id"]).json()["executed"]
    h.now[0] = 1120
    assert h.read().status_code == 401
    h.token = newer
    assert h.read().status_code == 200


def test_functional_changed_revision_stale_equal_conflicts_and_revocation(issuer):
    h, *_ = issuer
    old = child(issuer)
    h.now[0] += 1
    current = child(issuer, groups=["agents"])
    h.token = old
    assert h.read().status_code == 401
    before = rows(issuer)
    assert request(issuer, signed(issuer, groups=["employees"], iat=1000)).status_code == 401
    assert request(issuer, signed(issuer, groups=["employees"])).status_code == 401
    assert rows(issuer) == before
    sid = subject_id("https://issuer.invalid/people", "exact-person")
    revoke_subject(h.store, sid, 2)
    h.token = current
    assert h.read().status_code == 401
    h.now[0] += 1
    assert request(issuer, signed(issuer, groups=["agents"])).status_code == 401
    with h.store.connection() as db:
        assert subject(db, sid).revoked


def test_functional_trust_generation_disables_issued_child_and_race(issuer):
    h, _, _, config, _ = issuer
    old = child(issuer)
    ctx = context(issuer)
    token = signed(issuer)
    with pytest.raises(CredentialInvalid):
        exchange(
            h.service,
            ctx,
            token,
            before_write=lambda: import_trust(h.store, config, 1, h.service.clock),
        )
    h.token = old
    assert h.read().status_code == 401
    assert h.executor.calls == []
    config = config.model_copy(
        update={"profiles": (config.profiles[0].model_copy(update={"enabled": False}),)}
    )
    import_trust(h.store, config, 2, h.service.clock)
    assert request(issuer).status_code == 401


def test_functional_atomic_audit_failure_rolls_back_refresh_and_admission(issuer):
    h, *_ = issuer
    child(issuer)
    h.now[0] += 1
    before = rows(issuer)
    with h.store.connection() as db:
        old = db.execute("SELECT record FROM human_subjects").fetchone()[0]
        order = tuple(db.execute("SELECT * FROM issuer_assertion_order").fetchone())
        admissions = tuple(db.execute("SELECT * FROM issuer_admission").fetchone())
        db.execute(
            "CREATE TRIGGER fail_issuance BEFORE INSERT ON issuer_events WHEN NEW.kind='child_issued' BEGIN SELECT RAISE(ABORT,'fixture failure'); END"
        )
    assert request(issuer, signed(issuer, groups=["agents"])).status_code == 503
    assert rows(issuer) == before
    with h.store.connection() as db:
        assert db.execute("SELECT record FROM human_subjects").fetchone()[0] == old
        assert tuple(db.execute("SELECT * FROM issuer_assertion_order").fetchone()) == order
        assert tuple(db.execute("SELECT * FROM issuer_admission").fetchone()) == admissions


def test_functional_limits_are_transactional_bounded_and_no_growth(issuer):
    h, _, _, config, _ = issuer
    profile = config.profiles[0].model_copy(
        update={"max_active_children": 1, "max_total_children": 2, "exchanges_per_day": 3}
    )
    import_trust(h.store, config.model_copy(update={"profiles": (profile,)}), 1, h.service.clock)
    first = child(issuer)
    before = rows(issuer)
    assert request(issuer).status_code == 429
    assert rows(issuer) == before
    h.store.revoke(first)
    second = child(issuer)
    h.store.revoke(second)
    assert request(issuer).status_code == 429
    assert rows(issuer)[2] == 2
    assert request(issuer, "malformed").status_code == 401
    assert request(issuer, "malformed").status_code == 429
    with h.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM issuer_admission").fetchone()[0] == 1


def test_unit_concurrent_unchanged_and_changed_refresh(issuer):
    h, *_ = issuer
    token = signed(issuer)
    with ThreadPoolExecutor(max_workers=4) as pool:
        children = list(
            pool.map(lambda _: exchange(h.service, context(issuer), token)[0], range(4))
        )
    sid = subject_id("https://issuer.invalid/people", "exact-person")
    with h.store.connection() as db:
        assert subject(db, sid).revision == 1
    h.now[0] += 1
    changed = signed(issuer, groups=["agents"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        changed_children = list(
            pool.map(lambda _: exchange(h.service, context(issuer), changed)[0], range(4))
        )
    with h.store.connection() as db:
        assert subject(db, sid).revision == 2
    for token in children:
        with pytest.raises(CredentialInvalid):
            h.store.resolve(credential_digest(token), h.now[0])
    for token in changed_children:
        assert h.store.resolve(credential_digest(token), h.now[0]) == h.identity


def test_unit_lock_wait_expiry_rechecks_fresh_clock(issuer):
    h, *_ = issuer
    token = signed(issuer, exp=1001)
    before = rows(issuer)
    started = Event()
    ctx = context(issuer)
    with h.store.connection() as db, ThreadPoolExecutor(max_workers=1) as pool:
        db.execute("BEGIN IMMEDIATE")
        future = pool.submit(exchange, h.service, ctx, token, before_write=started.set)
        assert started.wait(2)
        h.now[0] = 1001
        db.execute("COMMIT")
        with pytest.raises(CredentialInvalid):
            future.result(2)
    assert rows(issuer) == before


def test_unit_local_v1_binding_stays_identical_under_issuer_migration(issuer):
    h, parent, *_ = issuer
    local = HumanSubject(
        subject_id="local",
        tenant_id="tenant-a",
        roles=("employee-hr",),
        department="HR",
        revision=1,
        assertion_deadline=1250.0,
    )
    provision_subject(h.store, local)
    token = issue_child(h.store, parent, "local", h.service.policy, now=1000.0)
    with h.store.connection() as db:
        raw = db.execute(
            "SELECT binding FROM delegated_bindings WHERE child_digest=?",
            (credential_digest(token),),
        ).fetchone()[0]
    assert parse_binding(raw).version == 1
    h.token = token
    pending = mail(h, "local-v1").json()
    with h.store.connection() as db:
        consent = db.execute("SELECT binding FROM action_authority").fetchone()[0]
    h.store.initialize()
    child(issuer)
    with h.store.connection() as db:
        assert (
            db.execute(
                "SELECT binding FROM delegated_bindings WHERE child_digest=?",
                (credential_digest(token),),
            ).fetchone()[0]
            == raw
        )
        assert db.execute("SELECT binding FROM action_authority").fetchone()[0] == consent
    decide(h, pending["action_id"])
    assert resume(h, pending["action_id"]).json()["executed"]


@pytest.mark.parametrize(
    "fragment",
    [
        '"exp":NaN',
        '"exp":Infinity',
        '"exp":-Infinity',
        '"unused":{"nested":NaN}',
        '"unused":{"nested":Infinity}',
        '"sub":"second-subject"',
        '"unused":' + "[" * 1100 + "0" + "]" * 1100,
        '"unused":' + "[" * 5 + "0" + "]" * 5,
    ],
)
def test_functional_signed_malformed_json_and_duplicate_members(issuer, fragment):
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    def b64(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    original = signed(issuer).split(".")
    payload = base64.urlsafe_b64decode(original[1] + "=" * (-len(original[1]) % 4))
    raw = payload[:-1] + b"," + fragment.encode() + b"}"
    signing = original[0].encode() + b"." + b64(raw)
    signature = issuer[2].sign(signing, padding.PKCS1v15(), hashes.SHA256())
    token = (signing + b"." + b64(signature)).decode()
    before = rows(issuer)
    response = request(issuer, token)
    assert response.status_code == 401
    assert response.json() == {"reason": "EXCHANGE_DENIED"}
    assert rows(issuer) == before


@pytest.mark.parametrize(
    "headers",
    [
        {"kid": "unknown"},
        {"typ": "JWT"},
        {"jku": "https://attacker.invalid/key"},
        {"x5u": "https://attacker.invalid/key"},
        {"jwk": {"kty": "RSA"}},
        {"crit": ["exp"]},
    ],
)
def test_functional_wrong_header_no_discovery_or_diagnostics(issuer, headers):
    payload = jwt.decode(
        signed(issuer),
        issuer[2].public_key(),
        algorithms=["RS256"],
        options={
            "verify_aud": False,
            "verify_exp": False,
            "verify_iat": False,
            "verify_nbf": False,
        },
    )
    token = jwt.encode(
        payload,
        issuer[2],
        algorithm="RS256",
        headers={"kid": "fixture-key", "typ": "at+jwt"} | headers,
    )
    assert request(issuer, token).status_code == 401
    assert rows(issuer)[0] == 0


def test_functional_wrong_algorithm_key_and_no_plaintext_storage(issuer):
    payload = jwt.decode(
        signed(issuer),
        issuer[2].public_key(),
        algorithms=["RS256"],
        options={
            "verify_aud": False,
            "verify_exp": False,
            "verify_iat": False,
            "verify_nbf": False,
        },
    )
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for key, alg in (
        (wrong, "RS256"),
        (issuer[2], "RS512"),
        ("fixture-symmetric-key-with-32-bytes", "HS256"),
    ):
        token = jwt.encode(
            payload, key, algorithm=alg, headers={"kid": "fixture-key", "typ": "at+jwt"}
        )
        assert request(issuer, token).status_code == 401
    token = signed(issuer)
    new = request(issuer, token).json()["token"]
    with issuer[0].store.connection() as db:
        for table in (
            "human_subjects",
            "delegated_bindings",
            "issuer_assertion_order",
            "issuer_admission",
            "issuer_events",
            "audit_events",
            "credentials",
        ):
            serialized = repr([tuple(row) for row in db.execute("SELECT * FROM " + table)])
            assert token not in serialized and new not in serialized
            assert "exact-person" not in serialized


@pytest.mark.parametrize("boundary", ["documents", "memory", "models", "approved_mail"])
@pytest.mark.parametrize("mutation", ["trust", "parent", "subject"])
def test_integration_current_trust_parent_human_at_transaction_dispatch(
    issuer, monkeypatch, boundary, mutation
):
    h, parent, _, config, provider = issuer
    h.token = child(issuer)
    pending = None
    if boundary == "approved_mail":
        pending = mail(h).json()["action_id"]
        decide(h, pending)
    # Capture model ledger owner via the app's route-independent attached service.
    # The provider retains the store; model reserve is a class boundary here.
    from agentgate.model_budgets import ModelLedger

    owner, name = {
        "documents": (h.store, "dispatch_intent"),
        "memory": (h.service.tools, "query"),
        "models": (ModelLedger, "reserve"),
        "approved_mail": (h.service.tools, "retrieve"),
    }[boundary]
    original = getattr(owner, name)

    def mutate(*args, **kwargs):
        monkeypatch.setattr(owner, name, original)
        if mutation == "trust":
            import_trust(h.store, config, 1, h.service.clock)
        elif mutation == "parent":
            h.store.revoke(parent)
        else:
            revoke_subject(h.store, subject_id("https://issuer.invalid/people", "exact-person"), 1)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, mutate)
    result = {
        "documents": h.read,
        "memory": lambda: action(h, "memory.query", {"query": "Quarterly"}),
        "models": lambda: chat(h),
        "approved_mail": lambda: resume(h, pending),
    }[boundary]()
    assert result.status_code == 401
    assert h.executor.calls == [] and provider.calls == []
    with h.store.connection() as db:
        for table in ("tool_outbox", "tool_reservations", "model_attempts"):
            assert db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0


def test_integration_exchange_mcp_wire_protects_actual_reads(issuer):
    h, *_ = issuer
    h.token = child(issuer)
    headers = h.headers | {"Accept": "application/json, text/event-stream"}
    response = h.client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "issuer-fixture-wire", "version": "1"},
            },
        },
    )
    assert response.status_code == 200
    headers |= {
        "Mcp-Session-Id": response.headers["mcp-session-id"],
        "MCP-Protocol-Version": "2025-11-25",
    }
    assert (
        h.client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        ).status_code
        == 202
    )
    for document, allowed in (("tenant-a-notes", True), ("tenant-a-contact", False)):
        response = h.client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": "call",
                "method": "tools/call",
                "params": {"name": "documents_read", "arguments": {"document_id": document}},
            },
        )
        assert response.status_code == 200
        assert response.json()["result"]["structuredContent"]["executed"] is allowed
    assert h.executor.calls == [("tenant-a-notes", "tenant-a")]
