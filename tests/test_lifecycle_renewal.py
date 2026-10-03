"""Installer file recovery against the actual integrated operator renewal helper."""

import time
from pathlib import Path

import pytest

from agentgate.lifecycle import renewal
from agentgate.lifecycle.provision import initialize
from agentgate.lifecycle.state import LifecycleError, write_new
from agentgate.storage import CredentialInvalid, Store, credential_digest

credentials = pytest.importorskip(
    "agentgate.admin_credentials",
    reason="Operator renewal PR24 must be integrated; file recovery is not verified by a fixture",
)


@pytest.fixture
def installed(tmp_path):
    directory = tmp_path / "data"
    proxy = tmp_path / "proxy.yaml"
    proxy.write_text("model_list: []\n")
    initialize(directory, Path(__file__).resolve().parents[1] / "config/policy.yaml", proxy, "off")
    store = Store(directory / "agentgate.sqlite3")
    token = (directory / "client.token").read_text()
    identity = store.resolve(credential_digest(token), time.time())
    with store.connection() as db:
        db.execute(
            "UPDATE credentials SET expires_at=99 WHERE digest=?", (credential_digest(token),)
        )
    return directory, store, token, identity


def test_expired_agent_replacement_preserves_identity_and_root(installed):
    directory, store, old, identity = installed
    renewal.renew_agent(directory, now=100)
    current = (directory / "client.token").read_text()
    assert current != old
    assert store.resolve(credential_digest(current), 101) == identity
    with pytest.raises(CredentialInvalid):
        store.resolve(credential_digest(old), 101)
    assert not (directory / "client.token.next").exists()
    assert (directory / "client.token").stat().st_mode & 0o777 == 0o600


def test_crash_after_database_commit_recovers_exact_issued_token(installed, monkeypatch):
    directory, store, old, identity = installed
    original = renewal.recover_agent_file
    attempts = 0

    def crash_after_commit(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated process loss after commit")
        return original(*args)

    monkeypatch.setattr(renewal, "recover_agent_file", crash_after_commit)
    with pytest.raises(OSError):
        renewal.renew_agent(directory, now=100)
    candidate = (directory / "client.token.next").read_text()
    assert (directory / "client.token").read_text() == old
    assert store.resolve(credential_digest(candidate), 101) == identity
    monkeypatch.setattr(renewal, "recover_agent_file", original)
    renewal.renew_agent(directory, now=102)
    assert (directory / "client.token").read_text() == candidate
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM credential_renewals").fetchone()[0] == 1


def test_precommit_file_failure_rolls_back_and_can_retry(installed, monkeypatch):
    directory, store, old, identity = installed
    original = renewal.sync_directory

    def failure(directory):
        raise OSError("simulated file synchronization failure")

    monkeypatch.setattr(renewal, "sync_directory", failure)
    with pytest.raises(OSError):
        renewal.renew_agent(directory, now=100)
    assert (directory / "client.token.next").exists()
    with store.connection() as db:
        row = db.execute(
            "SELECT revoked FROM credentials WHERE digest=?", (credential_digest(old),)
        ).fetchone()
        assert not row[0]
        assert db.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] == 1
    monkeypatch.setattr(renewal, "sync_directory", original)
    renewal.renew_agent(directory, now=101)
    current = (directory / "client.token").read_text()
    assert store.resolve(credential_digest(current), 102) == identity


def test_revoked_agent_and_revoked_recovery_file_never_resurrect(installed):
    directory, store, old, _ = installed
    pending = directory / "client.token.next"
    candidate = credentials.renew_agent_credential(
        store,
        old,
        now=100,
        expires_at=200,
        persist=lambda token: write_new(pending, token.encode()),
    )
    store.revoke(candidate)
    with pytest.raises(LifecycleError, match="revoked"):
        renewal.renew_agent(directory, now=101)
    assert (directory / "client.token").read_text() == old
    assert pending.read_text() == candidate
    for token in (old, candidate):
        with pytest.raises(CredentialInvalid):
            store.resolve(credential_digest(token), 101)


def test_active_or_revoked_renewal_does_not_replace_file(installed):
    directory, store, old, _ = installed
    with store.connection() as db:
        db.execute("UPDATE credentials SET expires_at=200")
    with pytest.raises(credentials.CredentialRenewalError) as active:
        renewal.renew_agent(directory, now=100)
    assert active.value.reason == "active"
    store.revoke(old)
    with pytest.raises(credentials.CredentialRenewalError) as revoked:
        renewal.renew_agent(directory, now=300)
    assert revoked.value.reason == "revoked"
    assert (directory / "client.token").read_text() == old
    assert not (directory / "client.token.next").exists()


def test_renewed_file_cannot_escape_exhausted_root_budget(installed):
    from agentgate.budgets import ToolBudgets
    from agentgate.contracts import ActionRequest
    from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
    from agentgate.policy import load_policy
    from agentgate.service import ActionService, GateError

    directory, store, old, _ = installed
    policy = load_policy(directory / "policy.yaml").model_copy(
        update={"tool_budgets": ToolBudgets(tenant_day=10, principal_day=10, root_run=1)}
    )
    documents = demo_documents()
    service = ActionService(
        store,
        policy,
        DocumentRegistry(documents),
        FixtureExecutor(documents),
        (directory / "audit.key").read_bytes(),
        clock=lambda: 98,
    )
    request = ActionRequest(operation="documents.read", arguments={"document_id": "tenant-a-notes"})
    context = service.new_context()
    service.authenticate(context, old)
    assert service.execute(context, request).executed
    before = store.budget_counters()
    renewal.renew_agent(directory, now=100)
    service.clock = lambda: 101
    context = service.new_context()
    service.authenticate(context, (directory / "client.token").read_text())
    with pytest.raises(GateError) as denied:
        service.execute(context, request)
    assert denied.value.reason.value == "BUDGET_EXCEEDED"
    assert store.budget_counters() == before
