import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from test_gateway import Harness
from test_gateway import harness as harness

from agentgate.budgets import ToolBudgets
from agentgate.contracts import Reason
from agentgate.scoped_tools import ToolSnapshot
from agentgate.service import GateError
from agentgate.storage import StorageUnavailable, credential_digest


@pytest.fixture
def tools(harness: Harness):
    harness.identity = harness.identity.model_copy(
        update={
            "operations": ("documents.read", "memory.query", "mail.send"),
        }
    )
    harness.token = harness.store.issue(harness.identity, expires_at=2000.0)
    harness.service.policy = harness.service.policy.model_copy(
        update={
            "tool_budgets": ToolBudgets(tenant_day=100, principal_day=100, root_run=30),
        }
    )
    with harness.store.connection() as connection:
        connection.executemany(
            "INSERT INTO memory_entries VALUES (?,?,?,?)",
            [
                ("tenant-a", "notes", "internal", "Quarterly scoped notes"),
                ("tenant-b", "notes", "internal", "Quarterly other tenant private"),
                ("tenant-a", "secret", "secret", "Quarterly restricted"),
            ],
        )
    return harness


def execute(tools, operation, arguments):
    return tools.client.post(
        "/v1/actions/execute",
        headers=tools.headers,
        json={"operation": operation, "arguments": arguments},
    )


def mail(tools, **changes):
    arguments = {
        "recipient": "analyst@demo.internal",
        "subject": "Quarterly report",
        "body": "Approved fixture content",
        "idempotency_key": "mail-1",
    } | changes
    return execute(tools, "mail.send", arguments)


def rows(tools, table):
    assert table in ("tool_outbox", "tool_actions", "tool_reservations")
    with tools.store.connection() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM " + table)]


def decide(tools, approve=True, **changes):
    action = tools.service.tools.list_approvals(tenant_id="tenant-a")[0]
    return tools.service.tools.decide(
        **(
            {
                "tenant_id": "tenant-a",
                "action_id": action["action_id"],
                "fingerprint": action["fingerprint"],
                "approve": approve,
                "actor": "operator-test",
            }
            | changes
        )
    )


def resume(tools, action_id):
    return tools.client.post(f"/v1/actions/{action_id}/resume", headers=tools.headers, json={})


def test_memory_scopes_authorization_before_query_and_output(tools):
    result = execute(tools, "memory.query", {"query": "Quarterly"})
    assert result.status_code == 200
    assert result.json()["result"]["entries"] == [
        {"entry_id": "notes", "content": "Quarterly scoped notes"}
    ]
    assert all(c["spent"] == 1 for c in tools.store.budget_counters())
    assert [e.operation for e in tools.store.events()] == ["memory.query", "memory.query"]
    forged = execute(tools, "memory.query", {"query": "Quarterly", "tenant_id": "tenant-b"})
    assert forged.status_code == 422
    assert all(c["spent"] == 1 for c in tools.store.budget_counters())
    tools.identity = tools.identity.model_copy(update={"tenant_id": "tenant-b"})
    tools.token = tools.store.issue(tools.identity, 2000.0)
    assert execute(tools, "memory_query", {"query": "Quarterly"}).json()["result"]["entries"] == [
        {"entry_id": "notes", "content": "Quarterly other tenant private"}
    ]


@pytest.mark.parametrize(
    "operation,arguments",
    [
        ("memory.query", {"query": "Quarterly"}),
        (
            "mail.send",
            {
                "recipient": "analyst@demo.internal",
                "subject": "x",
                "body": "x",
                "idempotency_key": "k",
            },
        ),
    ],
)
def test_unscoped_identity_and_discovery_deny(harness, operation, arguments):
    result = execute(harness, operation, arguments)
    assert result.status_code == 403
    assert result.json()["executed"] is False
    assert harness.client.get("/v1/tools", headers=harness.headers).json() == {
        "tools": ["documents.read"]
    }
    assert rows(harness, "tool_outbox") == []


@pytest.mark.parametrize(
    "recipient", ["x@evil.example", "x@demo.internal.evil", "x@sub.demo.internal"]
)
def test_forbidden_mail_has_no_action_budget_or_outbox(tools, recipient):
    result = mail(tools, recipient=recipient)
    assert result.status_code == 403
    assert result.json()["reason_codes"] == ["RECIPIENT_DOMAIN_NOT_ALLOWED"]
    assert rows(tools, "tool_outbox") == rows(tools, "tool_actions") == []
    assert tools.store.budget_counters() == []


@pytest.mark.parametrize(
    "recipient",
    [
        "a@DEMO.internal",
        "a@demo.internal\nBcc:other@evil.example",
        "a@@demo.internal",
        "a@demo.internal.",
        "a@demo.internal,b@evil.example",
    ],
)
def test_malformed_recipient_never_rewritten(tools, recipient):
    assert mail(tools, recipient=recipient).status_code == 422
    assert rows(tools, "tool_outbox") == []


def test_pending_approval_exact_payload_and_private_audit(tools):
    first = mail(tools)
    repeated = mail(tools)
    assert first.status_code == repeated.status_code == 202
    assert first.json()["action_id"] == repeated.json()["action_id"]
    assert first.json()["executed"] is False
    assert rows(tools, "tool_outbox") == []
    assert tools.store.budget_counters() == []
    action = tools.service.tools.list_approvals(tenant_id="tenant-a")[0]
    assert action["payload"]["recipient"] == "analyst@demo.internal"
    assert action["payload"]["body"] == "Approved fixture content"
    assert len(action["fingerprint"]) == 64
    audit = "\n".join(event.model_dump_json() for event in tools.store.events())
    assert "Approved fixture content" not in audit
    assert "analyst@demo.internal" not in audit
    assert tools.token not in audit
    assert tools.service.tools.list_approvals(tenant_id="tenant-b") == []


def test_approval_resume_and_replay_commit_one_actual_outbox_row(tools):
    action_id = mail(tools).json()["action_id"]
    assert decide(tools).action_state == "approved"
    assert rows(tools, "tool_outbox") == []
    result = resume(tools, action_id)
    assert result.status_code == 200
    assert result.json()["action_state"] == "consumed"
    assert result.json()["result"] == {"outbox_id": action_id, "delivery_state": "fixture"}
    assert resume(tools, action_id).json()["action_id"] == action_id
    assert mail(tools).json()["action_id"] == action_id
    outbox = rows(tools, "tool_outbox")
    assert len(outbox) == 1
    assert outbox[0]["recipient"] == "analyst@demo.internal"
    assert outbox[0]["body"] == "Approved fixture content"
    assert all(c["spent"] == 1 and c["reserved"] == 0 for c in tools.store.budget_counters())
    assert sum(e.event_type == "dispatch_intent" for e in tools.store.events()) == 1
    assert sum(e.event_type == "action_completed" for e in tools.store.events()) == 1


def test_concurrent_proposals_and_resumes_have_one_effect(tools):
    with ThreadPoolExecutor(max_workers=8) as pool:
        proposals = list(pool.map(lambda _: mail(tools), range(16)))
    assert {r.status_code for r in proposals} == {202}
    assert len({r.json()["action_id"] for r in proposals}) == 1
    action_id = proposals[0].json()["action_id"]
    decide(tools)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda i: resume(tools, action_id) if i % 2 else mail(tools), range(16))
        )
    assert {r.status_code for r in results} == {200}
    assert len(rows(tools, "tool_outbox")) == 1
    assert all(c["spent"] == 1 for c in tools.store.budget_counters())


def test_payload_mutation_conflicts_and_snapshot_is_immutable(tools):
    action_id = mail(tools).json()["action_id"]
    decide(tools)
    assert mail(tools, body="Different content").status_code == 409
    assert (
        tools.client.post(
            f"/v1/actions/{action_id}/resume",
            headers=tools.headers,
            json={"body": "Different content"},
        ).status_code
        == 422
    )
    with pytest.raises(StorageUnavailable), tools.store.connection() as connection:
        connection.execute("UPDATE tool_actions SET payload='{}' WHERE action_id=?", (action_id,))
    assert rows(tools, "tool_outbox") == []
    assert resume(tools, action_id).status_code == 200
    assert rows(tools, "tool_outbox")[0]["body"] == "Approved fixture content"


def test_expiry_and_denial_cannot_be_reapproved(tools):
    action_id = mail(tools).json()["action_id"]
    assert decide(tools, approve=False).action_state == "denied"
    assert decide(tools, approve=True).action_state == "denied"
    assert resume(tools, action_id).status_code == 403
    expired_id = mail(tools, idempotency_key="expires").json()["action_id"]
    tools.now[0] = 1300.0
    assert resume(tools, expired_id).status_code == 410
    assert rows(tools, "tool_outbox") == []
    assert tools.store.budget_counters() == []


@pytest.mark.parametrize(
    "change", ["policy_revision", "policy_same_revision", "registry", "credential"]
)
def test_changes_after_approval_prevent_dispatch(tools, monkeypatch, change):
    action_id = mail(tools).json()["action_id"]
    decide(tools)
    if change == "policy_revision":
        tools.service.policy = tools.service.policy.model_copy(update={"revision": 2})
    elif change == "policy_same_revision":
        tools.service.policy = tools.service.policy.model_copy(update={"semantic_mode": "observe"})
    elif change == "registry":
        monkeypatch.setattr("agentgate.scoped_tools.REGISTRY_DIGEST", "changed")
    else:
        tools.store.revoke(tools.token)
    assert resume(tools, action_id).status_code in (401, 403)
    assert rows(tools, "tool_outbox") == []
    assert tools.store.budget_counters() == []


@pytest.mark.parametrize(
    "identity_changes,expected",
    [
        ({"tenant_id": "tenant-b"}, 404),
        ({"principal_id": "other"}, 404),
        ({"root_run_id": "other-root"}, 404),
        ({"agent_id": "other-agent"}, 403),
        ({}, 403),
    ],
)
def test_wrong_scope_and_reissued_credentials_cannot_resume(tools, identity_changes, expected):
    action_id = mail(tools).json()["action_id"]
    decide(tools)
    tools.token = tools.store.issue(tools.identity.model_copy(update=identity_changes), 2000.0)
    assert resume(tools, action_id).status_code == expected
    assert (
        tools.client.get(f"/v1/actions/{action_id}", headers=tools.headers).status_code == expected
    )
    assert rows(tools, "tool_outbox") == []


def test_late_credential_revocation_and_lock_wait_expiry(tools, monkeypatch):
    action_id = mail(tools).json()["action_id"]
    decide(tools)
    entered = Event()
    original = tools.service.tools.retrieve

    def signal(*args, **kwargs):
        entered.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(tools.service.tools, "retrieve", signal)
    with ThreadPoolExecutor(max_workers=1) as pool, tools.store.connection() as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        future = pool.submit(resume, tools, action_id)
        assert entered.wait(2)
        blocker.execute(
            "UPDATE credentials SET revoked=1 WHERE digest=?", (credential_digest(tools.token),)
        )
        blocker.execute("COMMIT")
        assert future.result(3).status_code == 401
    assert rows(tools, "tool_outbox") == []


def test_approval_expiry_during_semantic_check_denies(tools, monkeypatch):
    action_id = mail(tools).json()["action_id"]
    decide(tools)
    original = tools.service.tools.check_mail

    def advance(*args):
        original(*args)
        tools.now[0] = 1300.0

    monkeypatch.setattr(tools.service.tools, "check_mail", advance)
    assert resume(tools, action_id).status_code == 410
    assert rows(tools, "tool_outbox") == []


@pytest.mark.parametrize("failure", ["dispatch_intent", "action_completed"])
def test_audit_failure_rolls_back_outbox_consumption_and_budget(tools, monkeypatch, failure):
    action_id = mail(tools).json()["action_id"]
    decide(tools)
    append = tools.store._append

    def fail(connection, event):
        if event.event_type == failure:
            raise sqlite3.OperationalError("fixture write failure")
        append(connection, event)

    monkeypatch.setattr(tools.store, "_append", fail)
    result = resume(tools, action_id)
    assert result.status_code == 503
    assert result.json()["executed"] is False
    assert rows(tools, "tool_outbox") == []
    assert rows(tools, "tool_actions")[0]["state"] == "approved"
    assert tools.store.budget_counters() == []
    monkeypatch.setattr(tools.store, "_append", append)
    assert resume(tools, action_id).status_code == 200
    assert len(rows(tools, "tool_outbox")) == 1


def test_lost_ack_after_commit_reconciles_by_outbox_after_restart(tools, monkeypatch):
    from agentgate.scoped_tools import ScopedTools
    from agentgate.storage import Store

    action_id = mail(tools).json()["action_id"]
    decide(tools)

    def lost_ack(*args):
        raise StorageUnavailable

    monkeypatch.setattr(tools.service.tools, "response", lost_ack)
    assert resume(tools, action_id).status_code == 503
    assert len(rows(tools, "tool_outbox")) == 1
    tools.service.store = Store(tools.store.path)
    tools.service.tools = ScopedTools(tools.service)
    assert resume(tools, action_id).status_code == 200
    assert len(rows(tools, "tool_outbox")) == 1
    assert all(c["spent"] == 1 and c["reserved"] == 0 for c in tools.store.budget_counters())


def test_all_tools_share_root_across_delegated_principals(tools):
    tools.service.policy = tools.service.policy.model_copy(
        update={"tool_budgets": ToolBudgets(tenant_day=100, principal_day=100, root_run=1)}
    )
    action_id = mail(tools).json()["action_id"]
    decide(tools)
    assert tools.read().status_code == 200
    assert resume(tools, action_id).status_code == 429
    tools.token = tools.store.issue(
        tools.identity.model_copy(update={"principal_id": "delegate"}), 2000.0
    )
    assert execute(tools, "memory.query", {"query": "Quarterly"}).status_code == 429
    assert rows(tools, "tool_outbox") == []


def test_input_secret_and_required_unavailable_semantic_never_write(tools):
    assert mail(tools, body="AGENTGATE_SECRET[fixture]").status_code == 403
    tools.service.policy = tools.service.policy.model_copy(update={"semantic_required": True})
    assert mail(tools).status_code == 503
    assert execute(tools, "memory.query", {"query": "Quarterly"}).status_code == 503
    assert rows(tools, "tool_outbox") == rows(tools, "tool_actions") == []


def test_memory_result_is_inspected_before_release(tools):
    with tools.store.connection() as connection:
        connection.execute(
            "INSERT INTO memory_entries VALUES ('tenant-a','leak','internal','Quarterly AGENTGATE_SECRET[fixture]')"
        )
    response = execute(tools, "memory.query", {"query": "Quarterly"})
    assert response.status_code == 403
    assert response.json()["executed"] is True
    assert "result" not in response.json()
    assert all(c["spent"] == 1 for c in tools.store.budget_counters())


def test_live_snapshot_callback_rechecks_under_transaction(tools):
    generation = [1]
    stages = []

    def provider():
        expected = generation[0]

        def current(connection):
            assert connection.in_transaction
            if generation[0] != expected:
                raise GateError(409, Reason.POLICY_CHANGED)

        def inspect(stage, text):
            stages.append(stage)

        return ToolSnapshot(tools.service.policy, str(expected), inspect, current)

    tools.service.tools.snapshot_provider = provider
    action_id = mail(tools).json()["action_id"]
    decide(tools)
    generation[0] += 1
    assert resume(tools, action_id).status_code == 403
    assert rows(tools, "tool_outbox") == []
    assert "tool_action" in stages


def test_operator_hooks_require_exact_fingerprint_and_tenant(tools):
    mail(tools)
    with pytest.raises(GateError):
        decide(tools, fingerprint="wrong")
    with pytest.raises(GateError):
        decide(tools, tenant_id="tenant-b")
    with pytest.raises(ValueError):
        tools.service.tools.list_approvals(tenant_id="tenant-a", limit=101)
    assert tools.service.tools.outbox(tenant_id="tenant-b") == []
    assert (
        tools.client.post(
            "/admin/approvals/x/decision", headers=tools.headers, json={"approve": True}
        ).status_code
        == 404
    )
