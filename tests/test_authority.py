"""Local authority unit/functional/integration evidence, never real-model evaluation."""

import hashlib
import hmac
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_gateway import Harness
from test_gateway import harness as harness
from test_models import ObservedProvider

from agentgate.admin_credentials import CredentialRenewalError, renew_agent_credential
from agentgate.app import create_app
from agentgate.authority import (
    MAX_LIFETIME,
    issue_child,
    matches,
    provision_subject,
)
from agentgate.authority_contracts import DelegationPolicy, HumanSubject, RecordGrant
from agentgate.budgets import ToolBudgets
from agentgate.control_plane import ControlPlane
from agentgate.model_config import ModelPolicy, ResourceLimits
from agentgate.models import ModelService
from agentgate.scoped_contracts import REGISTRY_DIGEST
from agentgate.scoped_tools import canonical
from agentgate.storage import CredentialInvalid, StorageUnavailable, Store, credential_digest

OPS = ("documents.read", "memory.query", "mail.send", "chat.completions")


def grants(documents=("tenant-a-notes",), memory=("hr",), models=("local-demo",)):
    return [
        {"operation": "documents.read", "resources": documents, "classifications": ["internal"]},
        {"operation": "memory.query", "resources": memory, "classifications": ["internal"]},
        {"operation": "mail.send", "domains": ["demo.internal"]},
        {"operation": "chat.completions", "models": models},
    ]


def config(human=None, agent=None):
    return DelegationPolicy.model_validate_json(
        json.dumps(
            {
                "profiles": [
                    {"role_id": "employee-hr", "grants": human if human is not None else grants()},
                    {
                        "role_id": "analyst",
                        "grants": agent
                        if agent is not None
                        else grants(
                            ("tenant-a-notes", "tenant-a-contact"),
                            ("hr", "finance"),
                            ("local-demo", "finance-model"),
                        ),
                    },
                ],
                "required": [{"tenant_id": "tenant-a", "agent_id": "reader", "operations": OPS}],
            }
        )
    )


@pytest.fixture
def authority(harness: Harness):
    harness.identity = harness.identity.model_copy(update={"operations": OPS})
    parent = harness.store.issue(harness.identity, 2000.0)
    harness.service.policy = harness.service.policy.model_copy(
        update={
            "delegation": config(),
            "models": ModelPolicy(),
            "tool_budgets": ToolBudgets(tenant_day=100, principal_day=100, root_run=10),
        }
    )
    person = HumanSubject(
        subject_id="employee",
        tenant_id="tenant-a",
        roles=("employee-hr",),
        department="HR",
        revision=1,
        assertion_deadline=1250.0,
    )
    provision_subject(harness.store, person)
    harness.token = issue_child(
        harness.store, parent, person.subject_id, harness.service.policy, now=harness.now[0]
    )
    with harness.store.connection() as db:
        db.executemany(
            "INSERT INTO memory_entries VALUES (?,?,?,?)",
            [
                ("tenant-a", "hr", "internal", "Quarterly HR only"),
                ("tenant-a", "finance", "internal", "Quarterly Finance forbidden"),
                ("tenant-a", "public-forbidden", "public", "Quarterly public forbidden"),
                ("tenant-b", "hr", "internal", "Quarterly wrong tenant forbidden"),
            ],
        )
    provider = ObservedProvider(harness.store)
    models = ModelService(harness.service, provider)
    with TestClient(
        create_app(harness.service, models, enable_mcp=True), base_url="http://localhost"
    ) as client:
        harness.client = client
        yield harness, parent, person, models, provider


def action(h, op, arguments):
    return h.client.post(
        "/v1/actions/execute", headers=h.headers, json={"operation": op, "arguments": arguments}
    )


def mail(h, key="exact-1", **changes):
    return action(
        h,
        "mail.send",
        {
            "recipient": "review@demo.internal",
            "subject": "Local HR review",
            "body": "Synthetic payload",
            "idempotency_key": key,
        }
        | changes,
    )


def decide(h, action_id):
    row = next(
        r
        for r in h.service.tools.list_approvals(tenant_id="tenant-a")
        if r["action_id"] == action_id
    )
    return h.service.tools.decide(
        tenant_id="tenant-a",
        action_id=action_id,
        fingerprint=row["fingerprint"],
        approve=True,
        actor="local-test",
        actor_mode="credential",
    )


def resume(h, action_id):
    return h.client.post(f"/v1/actions/{action_id}/resume", headers=h.headers, json={})


def count(h, table):
    assert table in (
        "credentials",
        "delegated_bindings",
        "tool_actions",
        "tool_outbox",
        "tool_reservations",
        "model_attempts",
        "action_authority",
    )
    with h.store.connection() as db:
        return db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]


def chat(h, alias="local-demo"):
    return h.client.post(
        "/v1/chat/completions",
        headers=h.headers,
        json={
            "model": alias,
            "messages": [{"role": "user", "content": "Synthetic request"}],
            "max_tokens": 10,
        },
    )


def test_unit_relational_grants_do_not_form_cartesian_products():
    pairs = (
        RecordGrant(operation="documents.read", resources=("hr",), classifications=("internal",)),
        RecordGrant(
            operation="documents.read", resources=("finance",), classifications=("confidential",)
        ),
    )
    assert matches(pairs, "documents.read", "hr", "internal")
    assert matches(pairs, "documents.read", "finance", "confidential")
    assert not matches(pairs, "documents.read", "hr", "confidential")
    assert not matches(pairs, "mail.send", "hr", "internal")
    assert not matches((), "documents.read", "public", "public")


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": [{"role_id": "a", "grants": []}, {"role_id": "a", "grants": []}]},
        {
            "profiles": [
                {
                    "role_id": "a",
                    "grants": [
                        {
                            "operation": "documents.read",
                            "resources": [],
                            "classifications": ["public"],
                        }
                    ],
                }
            ]
        },
        {"profiles": [{"role_id": "a", "grants": [{"operation": "shell", "code": "ignored"}]}]},
        {
            "profiles": [
                {
                    "role_id": "a",
                    "grants": [
                        {
                            "operation": "documents.read",
                            "resources": ["*"],
                            "classifications": ["public"],
                        }
                    ],
                }
            ]
        },
    ],
)
def test_unit_grant_schema_rejects_unbounded_or_ambiguous_authority(change):
    with pytest.raises(ValidationError):
        DelegationPolicy.model_validate_json(json.dumps(change))


def test_functional_asymmetric_union_and_exact_same_tenant_isolation(authority):
    h, _, _, _, provider = authority
    assert h.read().status_code == 200  # Role names differ; permissions overlap.
    assert h.read("tenant-a-contact").status_code == 403
    assert h.read("tenant-b-notes").status_code == 403
    assert h.read("tenant-a-secret").status_code == 403
    assert h.executor.calls == [("tenant-a-notes", "tenant-a")]
    response = action(h, "memory.query", {"query": "Quarterly"})
    assert response.json()["result"]["entries"] == [
        {"entry_id": "hr", "content": "Quarterly HR only"}
    ]
    assert "forbidden" not in response.text
    assert chat(h, "finance-model").status_code == 403
    assert provider.calls == []
    assert [r["id"] for r in h.client.get("/v1/models", headers=h.headers).json()["data"]] == [
        "local-demo"
    ]


def test_functional_broad_human_narrow_agent_and_unknown_roles(authority):
    h, parent, person, _, _ = authority
    h.service.policy = h.service.policy.model_copy(
        update={
            "delegation": config(
                human=grants(("tenant-a-notes", "tenant-a-contact"), ("hr", "finance")),
                agent=grants(),
            )
        }
    )
    h.token = issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0)
    assert h.read().status_code == 200
    assert h.read("tenant-a-contact").status_code == 403
    provision_subject(
        h.store,
        person.model_copy(update={"roles": ("unknown",), "revision": 2}),
        expected_revision=1,
    )
    h.token = issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0)
    assert h.client.get("/v1/tools", headers=h.headers).json()["tools"] == []
    assert h.read().status_code == 403
    assert chat(h).status_code == 403


def test_integration_memory_sql_preserves_class_resource_pairs_before_content(authority):
    h, parent, person, _, _ = authority
    narrow = grants()
    narrow[1] = {"operation": "memory.query", "resources": ["hr"], "classifications": ["internal"]}
    narrow.append(
        {"operation": "memory.query", "resources": ["finance"], "classifications": ["confidential"]}
    )
    h.service.policy = h.service.policy.model_copy(
        update={
            "delegation": config(human=narrow, agent=narrow),
            "scoped_tools": h.service.policy.scoped_tools.model_copy(
                update={"memory_classifications": ("internal", "confidential")}
            ),
        }
    )
    h.token = issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0)
    with h.store.connection() as db:
        db.execute(
            "UPDATE memory_entries SET classification='confidential' WHERE tenant_id='tenant-a' AND entry_id='hr'"
        )
        db.execute(
            "UPDATE memory_entries SET classification='confidential', content='Quarterly permitted Finance' WHERE tenant_id='tenant-a' AND entry_id='finance'"
        )
        # Abort if SQLite tries to inspect forbidden content, proving SQL filtering.
    original = h.store.connection
    from contextlib import contextmanager

    @contextmanager
    def observed():
        with original() as db:

            def inspect(content, query):
                assert "HR only" not in content and "forbidden" not in content
                return content.lower().find(query.lower()) + 1

            db.create_function("instr", 2, inspect)
            yield db

    h.store.connection = observed
    result = action(h, "memory.query", {"query": "Quarterly"})
    assert result.json()["result"]["entries"] == [
        {"entry_id": "finance", "content": "Quarterly permitted Finance"}
    ]


@pytest.mark.parametrize("operation", OPS)
def test_functional_parent_cannot_omit_required_delegation(authority, operation):
    h, parent, _, _, provider = authority
    h.token = parent
    if operation == "documents.read":
        result = h.read()
    elif operation == "memory.query":
        result = action(h, operation, {"query": "Quarterly"})
    elif operation == "mail.send":
        result = mail(h)
    else:
        result = chat(h)
    assert result.status_code == 403
    assert not result.json()["executed"]
    assert h.executor.calls == [] and provider.calls == []
    assert count(h, "tool_outbox") == count(h, "tool_actions") == count(h, "model_attempts") == 0
    assert h.store.budget_counters() == []


@pytest.mark.parametrize(
    "header", ["x-human-id", "x-on-behalf-of", "x-department", "x-delegation-id"]
)
def test_functional_public_identity_override_never_grants(authority, header):
    h, _, _, _, provider = authority
    for path, payload in (
        (
            "/v1/actions/execute",
            {"operation": "documents.read", "arguments": {"document_id": "tenant-a-contact"}},
        ),
        (
            "/v1/chat/completions",
            {"model": "finance-model", "messages": [{"role": "user", "content": "hello"}]},
        ),
    ):
        assert (
            h.client.post(path, headers=h.headers | {header: "finance"}, json=payload).status_code
            == 422
        )
    assert h.executor.calls == [] and provider.calls == []


def test_integration_exact_parent_child_deadlines_cas_and_one_hop(authority):
    h, parent, person, _, _ = authority
    with h.store.connection() as db:
        child = db.execute(
            "SELECT * FROM credentials WHERE digest=?", (credential_digest(h.token),)
        ).fetchone()
        assert child["identity"] == h.identity.model_dump_json()
        assert child["expires_at"] == 1250.0
        binding = db.execute(
            "SELECT * FROM delegated_bindings WHERE child_digest=?", (credential_digest(h.token),)
        ).fetchone()
        assert binding["parent_digest"] == credential_digest(parent)
    with pytest.raises(ValueError):
        provision_subject(h.store, person)
    with pytest.raises(ValueError):
        issue_child(h.store, h.token, person.subject_id, h.service.policy, now=1000.0)
    with pytest.raises(ValueError):
        issue_child(
            h.store,
            parent,
            person.subject_id,
            h.service.policy,
            now=1000.0,
            lifetime=MAX_LIFETIME + 1,
        )
    h.now[0] = 1250.0
    assert h.read().status_code == 401
    assert h.executor.calls == []


@pytest.mark.parametrize(
    "mutation", ["parent", "child", "human", "revision", "parent_expiry", "human_deadline"]
)
def test_integration_lifecycle_invalidates_descendants(authority, mutation):
    h, parent, person, _, provider = authority
    pending = mail(h).json()["action_id"]
    if mutation in ("parent", "child"):
        h.store.revoke(parent if mutation == "parent" else h.token)
    elif mutation == "parent_expiry":
        with h.store.connection() as db:
            db.execute(
                "UPDATE credentials SET expires_at=1000 WHERE digest=?",
                (credential_digest(parent),),
            )
    else:
        change = {"revision": 2} | (
            {"revoked": True}
            if mutation == "human"
            else {"assertion_deadline": 999.0}
            if mutation == "human_deadline"
            else {"department": "Finance"}
        )
        provision_subject(h.store, person.model_copy(update=change), expected_revision=1)
    assert h.read().status_code == 401
    assert decide(h, pending).status == "denied"
    assert resume(h, pending).status_code == 401
    assert h.executor.calls == [] and provider.calls == [] and count(h, "tool_outbox") == 0


def test_integration_renewal_rejects_children_before_persist_and_parent_renewal_revokes_children(
    authority,
):
    h, parent, _, _, _ = authority
    writes = []
    for now in (1000.0, 1251.0):
        with pytest.raises(CredentialRenewalError, match="delegated"):
            renew_agent_credential(
                h.store, h.token, now=now, expires_at=now + 100, persist=writes.append
            )
    assert writes == []
    replacement = renew_agent_credential(h.store, parent, now=2000.0, expires_at=2100.0)
    assert h.store.resolve(credential_digest(replacement), 2001.0) == h.identity
    with pytest.raises(CredentialInvalid):
        h.store.resolve(credential_digest(h.token), 1001.0)


def test_integration_ceiling_policy_expansion_narrowing_and_approval_binding(authority):
    h, _, _, _, _ = authority
    pending = mail(h).json()["action_id"]
    h.service.policy = h.service.policy.model_copy(
        update={
            "revision": 2,
            "delegation": config(
                human=grants(("tenant-a-notes", "tenant-a-contact"), ("hr", "finance"))
            ),
        }
    )
    assert h.read("tenant-a-contact").status_code == 403  # expansion cannot widen child
    assert decide(h, pending).status == "denied"  # unchanged mail still needs new consent
    h.service.policy = h.service.policy.model_copy(
        update={"revision": 3, "delegation": config(agent=[])}
    )
    assert h.read().status_code == 403
    assert h.client.get("/v1/tools", headers=h.headers).json()["tools"] == []
    assert count(h, "tool_outbox") == 0


def test_integration_approval_replay_attribution_and_shared_accounting(authority):
    h, parent, person, models, _ = authority
    first = mail(h).json()
    assert count(h, "tool_outbox") == 0
    row = h.service.tools.list_approvals(tenant_id="tenant-a")[0]
    assert row["authority"]["human_subject"] == person.subject_id
    assert row["authority"]["accounting_principal"] == h.identity.principal_id
    assert decide(h, first["action_id"]).status == "approved"
    assert count(h, "tool_outbox") == 0
    assert resume(h, first["action_id"]).json()["executed"]
    assert resume(h, first["action_id"]).status_code == 200
    assert mail(h).json()["action_state"] == "consumed"
    assert mail(h, body="mutated").status_code == 409
    assert count(h, "tool_outbox") == 1
    decision = next(e for e in h.store.events() if e.event_type == "approval_decided")
    assert decision.approval_actor == {"version": 1, "actor_id": "local-test", "mode": "credential"}
    assert decision.authority["human_subject"] == "employee"
    assert chat(h).status_code == 200
    h.token = issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0)
    assert chat(h).status_code == 200
    for counter in models.ledger.counters():
        if counter["resource"] == "calls":
            assert counter["spent"] == 2
    assert (
        len({c["scope_key"] for c in models.ledger.counters() if c["scope"] == "principal_day"})
        == 1
    )
    assert len({c["scope_key"] for c in models.ledger.counters() if c["scope"] == "root_run"}) == 1


@pytest.mark.parametrize("boundary", ["documents", "memory", "models", "approved_mail"])
def test_integration_revocation_race_before_transaction_has_zero_effect(
    authority, monkeypatch, boundary
):
    h, _, person, models, provider = authority
    entered, release = Event(), Event()
    action_id = None
    if boundary == "approved_mail":
        action_id = mail(h).json()["action_id"]
        decide(h, action_id)
    owner, method = {
        "documents": (h.store, "dispatch_intent"),
        "memory": (h.service.tools, "query"),
        "models": (models.ledger, "reserve"),
        "approved_mail": (h.service.tools, "retrieve"),
    }[boundary]
    original = getattr(owner, method)

    def pause(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, method, pause)
    operation = {
        "documents": h.read,
        "memory": lambda: action(h, "memory.query", {"query": "Quarterly"}),
        "models": lambda: chat(h),
        "approved_mail": lambda: resume(h, action_id),
    }[boundary]
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(operation)
        try:
            assert entered.wait(5)
            provision_subject(
                h.store,
                person.model_copy(update={"revision": 2, "revoked": True}),
                expected_revision=1,
            )
        finally:
            release.set()
        assert future.result().status_code == 401
    assert h.executor.calls == [] and provider.calls == []
    assert (
        count(h, "tool_outbox") == count(h, "tool_reservations") == count(h, "model_attempts") == 0
    )
    assert h.store.budget_counters() == []


@pytest.mark.parametrize("boundary", ["documents", "memory", "models", "approved_mail", "proposal"])
def test_integration_audit_failure_rolls_back_before_dispatch(authority, monkeypatch, boundary):
    h, _, _, _, provider = authority
    action_id = None
    if boundary == "approved_mail":
        action_id = mail(h).json()["action_id"]
        decide(h, action_id)

    def fail(*args):
        raise StorageUnavailable

    monkeypatch.setattr(Store, "_append", fail)
    response = {
        "documents": h.read,
        "memory": lambda: action(h, "memory.query", {"query": "Quarterly"}),
        "models": lambda: chat(h),
        "approved_mail": lambda: resume(h, action_id),
        "proposal": lambda: mail(h),
    }[boundary]()
    assert response.status_code == 503
    assert h.executor.calls == [] and provider.calls == []
    assert (
        count(h, "tool_outbox") == count(h, "tool_reservations") == count(h, "model_attempts") == 0
    )
    if boundary == "proposal":
        assert count(h, "tool_actions") == count(h, "action_authority") == 0


def test_integration_missing_or_corrupt_sidecar_fails_closed(authority):
    h, _, _, _, _ = authority
    with h.store.connection() as db:
        db.execute(
            "DELETE FROM delegated_bindings WHERE child_digest=?", (credential_digest(h.token),)
        )
    assert not h.store.ready()
    assert h.read().status_code == 401
    assert h.executor.calls == []
    with h.store.connection() as db:
        db.execute("DROP TABLE delegated_bindings")
    assert not h.store.ready()
    assert h.read().status_code == 503


def test_integration_provisioning_callback_failure_is_atomic(authority):
    h, parent, person, _, _ = authority
    before = count(h, "credentials"), count(h, "delegated_bindings")

    def fail(token):
        raise OSError("Private file unavailable")

    with pytest.raises(OSError):
        issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0, persist=fail)
    assert (count(h, "credentials"), count(h, "delegated_bindings")) == before


def test_integration_legacy_fingerprint_pending_and_consumed_survive_migration_restart(authority):
    h, parent, _, _, _ = authority
    h.service.policy = h.service.policy.model_copy(update={"delegation": None})
    h.token = parent
    pending = mail(h, key="legacy-pending").json()["action_id"]
    consumed = mail(h, key="legacy-consumed").json()["action_id"]
    decide(h, consumed)
    resume(h, consumed)
    with h.store.connection() as db:
        rows = {r["action_id"]: dict(r) for r in db.execute("SELECT * FROM tool_actions")}
        old_policy = h.service.policy.model_dump(mode="json")
        old_policy.pop("delegation")
        old_digest = hashlib.sha256(
            canonical({"policy": old_policy, "controls": "0"}).encode()
        ).hexdigest()
        for row in rows.values():
            expected = hmac.new(
                h.service.audit_key,
                canonical(
                    {
                        "identity": json.loads(row["identity"]),
                        "credential": row["credential_digest"],
                        "operation": "mail.send",
                        "payload": row["payload_digest"],
                        "policy": old_digest,
                        "registry": REGISTRY_DIGEST,
                        "expires": row["expires_at"],
                    }
                ).encode(),
                hashlib.sha256,
            ).hexdigest()
            assert row["fingerprint"] == expected
        # Reconstruct an actual pre-extension database, without rewriting actions.
        db.execute("DELETE FROM delegated_bindings")
        db.execute("DELETE FROM credentials WHERE authority_kind='delegated'")
        for name in (
            "action_authority",
            "delegated_bindings",
            "human_subjects",
            "authority_schema",
        ):
            db.execute("DROP TABLE " + name)
        db.execute("DROP TRIGGER credential_authority_immutable")
        db.execute("ALTER TABLE credentials DROP COLUMN authority_kind")
    assert not h.store.ready()
    h.store.initialize()
    h.store = Store(h.store.path)
    h.service.store = h.store
    assert h.store.ready()
    with h.store.connection() as db:
        assert {r["action_id"]: dict(r) for r in db.execute("SELECT * FROM tool_actions")} == rows
    assert decide(h, pending).status == "approved"
    assert resume(h, pending).status_code == 200
    assert resume(h, consumed).json()["action_state"] == "consumed"
    assert count(h, "tool_outbox") == 2


def test_integration_official_mcp_discovery_and_undiscovered_calls(authority):
    h, _, _, _, _ = authority
    headers = h.headers | {"Accept": "application/json, text/event-stream"}
    init = h.client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "local-authority-test", "version": "1"},
            },
        },
    )
    assert init.status_code == 200
    headers |= {"Mcp-Session-Id": init.headers["mcp-session-id"]}
    h.client.post(
        "/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
    )

    def rpc(method, params):
        return h.client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": "authority", "method": method, "params": params},
        )

    assert [r["name"] for r in rpc("tools/list", {}).json()["result"]["tools"]] == h.client.get(
        "/v1/tools", headers=h.headers
    ).json()["tools"]
    for alias, arguments in (
        ("documents_read", {"document_id": "tenant-a-contact"}),
        (
            "mail_send",
            {
                "recipient": "forbidden@outside.invalid",
                "subject": "No",
                "body": "No",
                "idempotency_key": "mcp-deny",
            },
        ),
    ):
        response = rpc("tools/call", {"name": alias, "arguments": arguments}).json()["result"]
        assert response["isError"] and not response["structuredContent"]["executed"]
    assert h.executor.calls == [] and count(h, "tool_outbox") == 0


def test_unit_aggregate_bound_and_expired_zero_assertion(authority):
    h, parent, person, _, _ = authority
    one = {"operation": "mail.send", "domains": ["demo.internal"]}
    with pytest.raises(ValidationError, match="aggregate grants"):
        DelegationPolicy.model_validate_json(
            json.dumps(
                {
                    "profiles": [
                        {"role_id": "a", "grants": [one] * 64},
                        {"role_id": "b", "grants": [one]},
                    ]
                }
            )
        )
    provision_subject(
        h.store,
        person.model_copy(update={"revision": 2, "assertion_deadline": 0.0}),
        expected_revision=1,
    )
    before = count(h, "credentials")
    with pytest.raises(CredentialInvalid):
        issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0)
    assert count(h, "credentials") == before


def test_integration_model_allowed_by_global_policy_but_disjoint_grants_is_denied(authority):
    h, parent, person, _, provider = authority
    human = grants(models=("finance-model",))
    h.service.policy = h.service.policy.model_copy(update={"delegation": config(human=human)})
    h.token = issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0)
    assert h.client.get("/v1/models", headers=h.headers).json()["data"] == []
    assert chat(h).status_code == 403
    assert provider.calls == [] and count(h, "model_attempts") == 0


def test_integration_model_and_tool_budgets_cannot_reset_by_fresh_children(authority):
    h, parent, person, models, provider = authority
    policy = h.service.policy
    h.service.policy = policy.model_copy(
        update={
            "tool_budgets": ToolBudgets(tenant_day=100, principal_day=1, root_run=1),
            "models": ModelPolicy(
                principal_day=ResourceLimits(calls=1), root_run=ResourceLimits(calls=1)
            ),
        }
    )
    assert h.read().status_code == 200 and chat(h).status_code == 200
    h.token = issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0)
    assert h.read().status_code == 429 and chat(h).status_code == 429
    assert len(h.executor.calls) == len(provider.calls) == 1
    assert all(c["spent"] == 1 for c in h.store.budget_counters())
    assert all(c["spent"] == 1 for c in models.ledger.counters() if c["resource"] == "calls")


@pytest.mark.parametrize("registry", ["legacy", "catalog"])
def test_integration_frozen_prechange_actions_survive_migration_and_new_process(
    tmp_path, monkeypatch, registry
):
    """Snapshots produced by unmodified e4a5929, not by authority-aware code."""
    fixture = json.loads((Path(__file__).parent / "fixtures/authority-legacy-v0.json").read_text())
    if registry == "legacy":
        # Isolate authority compatibility from the independent catalog registry upgrade.
        monkeypatch.setattr(
            "agentgate.scoped_tools.REGISTRY_DIGEST",
            fixture["tables"]["tool_actions"][0]["registry_digest"],
        )
    store = Store(tmp_path / "frozen.sqlite3")
    store.initialize()
    allowed = {
        "credentials",
        "tool_actions",
        "tool_outbox",
        "budget_counters",
        "tool_reservations",
        "reservation_scopes",
        "audit_events",
    }
    with store.connection() as db:
        for table, records in fixture["tables"].items():
            assert table in allowed
            for row in records:
                columns = tuple(row)
                assert all(c.replace("_", "").isalnum() for c in columns)
                db.execute(
                    "INSERT INTO "
                    + table
                    + " ("
                    + ",".join(columns)
                    + ") VALUES ("
                    + ",".join("?" for _ in columns)
                    + ")",
                    tuple(row.values()),
                )
        for table in (
            "action_authority",
            "delegated_bindings",
            "human_subjects",
            "authority_schema",
        ):
            db.execute("DROP TABLE " + table)
        db.execute("DROP TRIGGER credential_authority_immutable")
        db.execute("ALTER TABLE credentials DROP COLUMN authority_kind")
    assert not store.ready()
    store.initialize()
    # Reopen a separate Store/service; no cached legacy action or control objects.
    store = Store(store.path)
    from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
    from agentgate.policy import Policy
    from agentgate.service import ActionService

    service = ActionService(
        store,
        Policy.model_validate_json(json.dumps(fixture["policy"])),
        DocumentRegistry(demo_documents()),
        FixtureExecutor(demo_documents()),
        b"explicit-test-hmac-key-not-a-secret",
        clock=lambda: 1000.0,
    )
    with store.connection() as db:
        assert [dict(r) for r in db.execute("SELECT * FROM tool_actions")] == fixture["tables"][
            "tool_actions"
        ]
    with TestClient(create_app(service)) as client:
        for row in fixture["tables"]["tool_actions"]:
            if row["state"] == "pending":
                approved = service.tools.decide(
                    tenant_id=row["tenant_id"],
                    action_id=row["action_id"],
                    fingerprint=row["fingerprint"],
                    approve=True,
                    actor="new-operator",
                )
                assert approved.status == ("approved" if registry == "legacy" else "denied")
            response = client.post(
                f"/v1/actions/{row['action_id']}/resume",
                headers={"Authorization": "Bearer " + "L" * 43},
                json={},
            )
            if row["state"] == "pending" and registry == "catalog":
                assert (
                    response.status_code == 403
                    and "POLICY_CHANGED" in response.json()["reason_codes"]
                )
            else:
                assert response.status_code == 200 and response.json()["action_state"] == "consumed"
    expected = 2 if registry == "legacy" else 1
    assert len(service.tools.outbox(tenant_id="tenant-a")) == expected
    assert all(c["spent"] == expected for c in store.budget_counters())


@pytest.mark.parametrize("boundary", ["documents", "memory", "models", "approved_mail"])
def test_integration_live_control_change_before_transaction_never_dispatches(
    authority, monkeypatch, boundary
):
    h, _, _, models, provider = authority
    controls = ControlPlane(h.store, clock=lambda: h.now[0])
    controls.initialize(h.service.policy)
    h.service.controls = controls
    pending = None
    if boundary == "approved_mail":
        pending = mail(h).json()["action_id"]
        decide(h, pending)
    owner, name = {
        "documents": (h.store, "dispatch_intent"),
        "memory": (h.service.tools, "query"),
        "models": (models.ledger, "reserve"),
        "approved_mail": (h.service.tools, "retrieve"),
    }[boundary]
    original = getattr(owner, name)

    def narrow(*args, **kwargs):
        monkeypatch.setattr(owner, name, original)
        snapshot = controls.snapshot()
        controls.activate_policy(
            snapshot.policy.model_copy(
                update={"revision": snapshot.policy.revision + 1, "delegation": config(agent=[])}
            ),
            snapshot.policy.version,
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, narrow)
    response = {
        "documents": h.read,
        "memory": lambda: action(h, "memory.query", {"query": "Quarterly"}),
        "models": lambda: chat(h),
        "approved_mail": lambda: resume(h, pending),
    }[boundary]()
    assert response.status_code in (403, 409)
    assert h.executor.calls == [] and provider.calls == [] and count(h, "tool_outbox") == 0
    assert count(h, "tool_reservations") == count(h, "model_attempts") == 0


def test_integration_corrupt_binding_and_authority_kind_cannot_downgrade(authority):
    h, _, _, _, _ = authority
    with pytest.raises(StorageUnavailable), h.store.connection() as db:
        db.execute(
            "UPDATE credentials SET authority_kind='legacy' WHERE digest=?",
            (credential_digest(h.token),),
        )
    with h.store.connection() as db:
        db.execute("DROP TRIGGER delegation_immutable")
        db.execute(
            "UPDATE delegated_bindings SET binding_digest=? WHERE child_digest=?",
            ("0" * 64, credential_digest(h.token)),
        )
    assert h.read().status_code == 401
    assert h.executor.calls == []


@pytest.mark.parametrize("actor", ["reviewer@example.test", "HR Reviewer"])
@pytest.mark.parametrize("delegated", [True, False])
@pytest.mark.parametrize("mode", ["credential", "local_console", "trusted_local_hook"])
def test_integration_approval_actor_preserves_legacy_bounded_text(
    authority, actor, delegated, mode
):
    h, parent, _, _, _ = authority
    if not delegated:
        h.token = parent
        h.service.policy = h.service.policy.model_copy(update={"delegation": None})
    pending = mail(h).json()["action_id"]
    row = h.service.tools.list_approvals(tenant_id="tenant-a")[0]
    decision = h.service.tools.decide(
        tenant_id="tenant-a",
        action_id=pending,
        fingerprint=row["fingerprint"],
        approve=True,
        actor=actor,
        actor_mode=mode,
    )
    assert decision.status == "approved"
    event = next(e for e in h.store.events() if e.event_type == "approval_decided")
    assert event.approval_actor["actor_id"] == actor
    assert event.approval_actor["mode"] == mode
    assert (event.authority is not None) == delegated
    assert count(h, "tool_outbox") == 0  # The label grants no permission or implicit execution.


def test_integration_maximum_accepted_grants_mint_and_query_without_sql_depth_failure(authority):
    h, parent, person, _, _ = authority
    grant = {
        "operation": "memory.query",
        "resources": ["hr", *[f"entry-{i}" for i in range(63)]],
        "classifications": ["internal", "public", "confidential", "secret"],
    }
    bounded = DelegationPolicy.model_validate_json(
        json.dumps({"profiles": [{"role_id": "analyst", "grants": [grant] * 64}]})
    )
    h.service.policy = h.service.policy.model_copy(update={"delegation": bounded})
    provision_subject(
        h.store,
        person.model_copy(update={"revision": 2, "roles": ("analyst",)}),
        expected_revision=1,
    )
    h.token = issue_child(h.store, parent, person.subject_id, h.service.policy, now=1000.0)
    from agentgate.authority import lifecycle

    # Reopen storage and validate the constructed binding, not just the config.
    with Store(h.store.path).connection() as db:
        _, binding = lifecycle(db, credential_digest(h.token), 1000.0)
        assert len(binding.ceiling.human) == len(binding.ceiling.agent) == 64
    result = action(h, "memory.query", {"query": "Quarterly"})
    assert result.status_code == 200
    assert [e["entry_id"] for e in result.json()["result"]["entries"]] == ["hr"]


@pytest.mark.parametrize("local_console", [False, True])
@pytest.mark.parametrize("delegated", [False, True])
def test_integration_owned_admin_decision_records_configured_mode(
    authority, local_console, delegated
):
    h, parent, _, _, _ = authority
    if not delegated:
        h.token = parent
        h.service.policy = h.service.policy.model_copy(update={"delegation": None})
    origin = "http://127.0.0.1:8765"
    app = create_app(
        h.service,
        admin_origin=origin,
        local_console=local_console,
        serving_address=("127.0.0.1", 8765),
    )
    operator = secrets.token_urlsafe(32)
    with h.store.connection() as db:
        db.execute("INSERT INTO operator_credentials VALUES (1,?)", (credential_digest(operator),))
    pending = mail(h).json()["action_id"]
    row = h.service.tools.list_approvals(tenant_id="tenant-a")[0]
    with TestClient(app, base_url=origin) as client:
        session = client.post(
            "/admin/session/bootstrap" if local_console else "/admin/session",
            headers={"Origin": origin},
            json={} if local_console else {"token": operator},
        )
        assert session.status_code == 200
        decision = client.post(
            f"/admin/approvals/{pending}/decision",
            headers={"Origin": origin, "X-CSRF-Token": session.json()["csrf_token"]},
            json={"tenant_id": "tenant-a", "fingerprint": row["fingerprint"], "approve": True},
        )
        assert decision.status_code == 202 and decision.json()["action_state"] == "approved"
    event = next(e for e in h.store.events() if e.event_type == "approval_decided")
    assert event.approval_actor == {
        "version": 1,
        "actor_id": "local-console" if local_console else "operator",
        "mode": "local_console" if local_console else "credential",
    }
    assert (event.authority is not None) == delegated
    assert count(h, "tool_outbox") == 0
    assert resume(h, pending).status_code == 200 and count(h, "tool_outbox") == 1
