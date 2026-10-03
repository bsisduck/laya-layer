import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_gateway import Harness
from test_gateway import harness as harness

from agentgate import budgets
from agentgate.budgets import ToolBudgets
from agentgate.contracts import Reason
from agentgate.storage import StorageUnavailable, Store, credential_digest


def enable(harness: Harness, **overrides):
    limits = ToolBudgets(**({"tenant_day": 100, "principal_day": 100, "root_run": 100} | overrides))
    harness.service.policy = harness.service.policy.model_copy(update={"tool_budgets": limits})


def rebind(harness: Harness, **changes):
    harness.identity = harness.identity.model_copy(update=changes)
    harness.token = harness.store.issue(harness.identity, expires_at=harness.now[0] + 200000)


def states(harness: Harness):
    with harness.store.connection() as connection:
        return [row[0] for row in connection.execute("SELECT state FROM tool_reservations")]


@pytest.mark.parametrize("scope", ["tenant_day", "principal_day", "root_run"])
def test_each_exhausted_scope_rolls_back_all_reservations(harness: Harness, scope):
    enable(harness, **{scope: 0})
    result = harness.read()
    assert result.status_code == 429
    assert result.json()["reason_codes"] == ["BUDGET_EXCEEDED"]
    assert result.json()["executed"] is False
    assert harness.executor.calls == []
    assert harness.store.budget_counters() == []
    assert states(harness) == []
    assert harness.store.events()[-1].event_type == "action_denied"


@pytest.mark.parametrize("scope", ["tenant_day", "principal_day", "root_run"])
def test_concurrent_admission_cannot_overspend_any_scope(harness: Harness, scope):
    enable(harness, **{scope: 3})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: harness.read(), range(16)))
    assert sorted(r.status_code for r in results) == [200] * 3 + [429] * 13
    assert len(harness.executor.calls) == 3
    assert states(harness) == ["settled"] * 3
    assert all(c["spent"] == 3 and c["reserved"] == 0 for c in harness.store.budget_counters())


def test_reservation_is_durable_before_executor(harness: Harness, monkeypatch):
    enable(harness)
    original = harness.executor.read

    def observe(*args):
        counters = Store(harness.store.path).budget_counters()
        assert len(counters) == 3
        assert all(c["reserved"] == 1 and c["spent"] == 0 for c in counters)
        assert states(harness) == ["dispatched"]
        return original(*args)

    monkeypatch.setattr(harness.executor, "read", observe)
    assert harness.read().status_code == 200


def test_agents_and_reissued_credentials_share_root_allowance(harness: Harness):
    enable(harness, root_run=1)
    assert harness.read().status_code == 200
    rebind(harness, agent_id="delegated-agent")
    assert harness.read().status_code == 429
    assert len(harness.executor.calls) == 1


def test_new_roots_do_not_reset_principal_allowance(harness: Harness):
    enable(harness, principal_day=1)
    assert harness.read().status_code == 200
    rebind(harness, root_run_id="new-root")
    assert harness.read().status_code == 429
    assert len(harness.store.budget_counters()) == 3


def test_new_principals_do_not_reset_tenant_allowance(harness: Harness):
    enable(harness, tenant_day=1)
    assert harness.read().status_code == 200
    rebind(harness, principal_id="other-principal", root_run_id="new-root")
    assert harness.read().status_code == 429


def test_equal_principal_and_root_names_in_other_tenant_have_separate_budget(harness: Harness):
    enable(harness, root_run=1, principal_day=1, tenant_day=1)
    assert harness.read().status_code == 200
    rebind(harness, tenant_id="tenant-b")
    assert harness.read("tenant-b-notes").status_code == 200
    assert len(harness.store.budget_counters()) == 6


def test_utc_rollover_resets_daily_limits_but_preserves_root(harness: Harness):
    enable(harness, tenant_day=1, principal_day=1, root_run=2)
    assert harness.read().status_code == 200
    harness.now[0] += 86400
    rebind(harness)
    assert harness.read().status_code == 200
    harness.now[0] += 86400
    rebind(harness)
    assert harness.read().status_code == 429
    root = [c for c in harness.store.budget_counters() if c["scope"] == "root_run"]
    assert root[0]["spent"] == 2


def test_policy_revision_and_restart_do_not_reset_usage(harness: Harness):
    enable(harness, root_run=1)
    assert harness.read().status_code == 200
    harness.service.store = Store(harness.store.path)
    harness.service.policy = harness.service.policy.model_copy(update={"revision": 2})
    assert harness.read().status_code == 429


def test_lowered_limit_below_existing_usage_denies_next_dispatch(harness: Harness):
    enable(harness)
    assert harness.read().status_code == 200
    enable(harness, root_run=0)
    assert harness.read().status_code == 429
    assert all(c["spent"] == 1 for c in harness.store.budget_counters())


def test_hard_denial_and_revocation_reserve_nothing(harness: Harness):
    enable(harness)
    assert harness.read("tenant-b-notes").status_code == 403
    harness.store.revoke(harness.token)
    assert harness.read().status_code == 401
    assert harness.store.budget_counters() == []


def test_output_block_still_spends_the_executed_call(harness: Harness):
    enable(harness, root_run=1)
    result = harness.read("tenant-a-leak")
    assert result.status_code == 403
    assert result.json()["executed"] is True
    assert states(harness) == ["settled"]
    assert all(c["spent"] == 1 for c in harness.store.budget_counters())
    assert harness.read().status_code == 429


def test_executor_failure_keeps_uncertain_reservation_after_restart(harness: Harness, monkeypatch):
    enable(harness, root_run=1)

    def fail(*args):
        raise TimeoutError("private exception")

    monkeypatch.setattr(harness.executor, "read", fail)
    assert harness.read().status_code == 503
    assert states(harness) == ["uncertain"]
    assert all(c["reserved"] == 1 and c["spent"] == 0 for c in harness.store.budget_counters())
    harness.service.store = Store(harness.store.path)
    assert harness.read().status_code == 429


def test_outcome_audit_failure_rolls_back_settlement(harness: Harness, monkeypatch):
    enable(harness, root_run=1)
    append = harness.store._append

    def fail_outcome(connection, event):
        if event.executed:
            raise sqlite3.OperationalError("simulated audit write failure")
        append(connection, event)

    monkeypatch.setattr(harness.store, "_append", fail_outcome)
    result = harness.read()
    assert result.status_code == 503
    assert result.json()["reason_codes"] == ["AUDIT_UNAVAILABLE"]
    assert "result" not in result.json()
    assert states(harness) == ["dispatched"]
    assert all(c["reserved"] == 1 and c["spent"] == 0 for c in harness.store.budget_counters())
    assert harness.read().status_code == 429


def test_dispatch_audit_failure_rolls_back_capacity(harness: Harness, monkeypatch):
    enable(harness)
    append = harness.store._append

    def fail_intent(connection, event):
        if event.event_type == "dispatch_intent":
            raise sqlite3.OperationalError("simulated disk failure")
        append(connection, event)

    monkeypatch.setattr(harness.store, "_append", fail_intent)
    assert harness.read().status_code == 503
    assert harness.executor.calls == []
    assert states(harness) == []
    assert harness.store.budget_counters() == []


def test_duplicate_settlement_cannot_charge_twice(harness: Harness):
    enable(harness)
    assert harness.read().status_code == 200
    event = harness.store.events()[-1]
    harness.store.append(event.model_copy(update={"event_id": "second-outcome"}))
    assert all(c["spent"] == 1 and c["reserved"] == 0 for c in harness.store.budget_counters())


@pytest.mark.parametrize("value", [-1, 1.5, True, "2", 1_000_000_001])
def test_budget_limits_are_bounded_strict_integers(value):
    with pytest.raises(ValidationError):
        ToolBudgets(tenant_day=value, principal_day=1, root_run=1)


def make_legacy(harness: Harness, path: Path):
    legacy = Store(path)
    with legacy.connection() as connection:
        connection.executescript("""
            CREATE TABLE credentials (digest TEXT PRIMARY KEY, identity TEXT NOT NULL,
                expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1)));
            CREATE TABLE audit_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE, action_id TEXT NOT NULL, event TEXT NOT NULL);
            CREATE INDEX audit_action ON audit_events(action_id);
            CREATE TABLE health_probe (id INTEGER PRIMARY KEY CHECK(id=1));
            PRAGMA user_version=1;
        """)
    token = legacy.issue(harness.identity, expires_at=2000.0)
    event = harness.service.event(
        harness.service.new_context(), "action_denied", Reason.INVALID_CREDENTIAL, "deny"
    )
    legacy.append(event)
    return legacy, token, event


def test_v1_upgrade_preserves_data_and_backup_restores_old_contract(harness: Harness, tmp_path):
    legacy, token, event = make_legacy(harness, tmp_path / "legacy.sqlite3")
    backup = Store(tmp_path / "backup.sqlite3")
    with legacy.connection() as source, backup.connection() as target:
        source.backup(target)
    assert not legacy.ready()
    legacy.initialize()
    legacy.initialize()
    assert legacy.ready()
    assert legacy.resolve(credential_digest(token), 1000.0) == harness.identity
    assert legacy.events() == [event]
    assert legacy.budget_counters() == []
    # Rollback is restoration of the stopped, pre-upgrade snapshot, not dropping live counters.
    with backup.connection() as source, legacy.connection() as target:
        source.backup(target)
    with legacy.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert legacy.resolve(credential_digest(token), 1000.0) == harness.identity
    assert legacy.events() == [event]


def test_failed_migration_is_atomic(harness: Harness, tmp_path, monkeypatch):
    legacy, token, event = make_legacy(harness, tmp_path / "legacy.sqlite3")
    monkeypatch.setattr(budgets, "SCHEMA", budgets.SCHEMA + "INVALID SQL;")
    with pytest.raises(StorageUnavailable):
        legacy.initialize()
    with legacy.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='budget_counters'"
            ).fetchall()
            == []
        )
    assert legacy.resolve(credential_digest(token), 1000.0) == harness.identity
    assert legacy.events() == [event]


def test_delegated_principal_cannot_reset_root_allowance(harness: Harness):
    enable(harness, root_run=1)
    assert harness.read().status_code == 200
    rebind(harness, principal_id="delegate", agent_id="delegated-agent")
    assert harness.read().status_code == 429
    assert len(harness.executor.calls) == 1


def test_legacy_roots_merge_spend_reservations_and_settle_once(harness: Harness):
    import json

    enable(harness, root_run=4)
    assert harness.read().status_code == 200
    with harness.store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        # Seed two legacy principals, one with an unresolved dispatch, alongside
        # the already spent shared-root account. Keep all real reservation FKs.
        for principal, reserved, spent in (("parent", 0, 1), ("child", 1, 1)):
            key = json.dumps(["tenant-a", principal, "run-a"], separators=(",", ":"))
            connection.execute(
                "INSERT INTO budget_counters VALUES ('root_run', ?, ?, ?)",
                (key, reserved, spent),
            )
        connection.execute(
            "INSERT INTO tool_reservations VALUES ('legacy', 'uncertain', 999, 'old:1')"
        )
        counters = connection.execute(
            "SELECT scope, scope_key FROM budget_counters WHERE scope!='root_run'"
        ).fetchall()
        for row in counters:
            connection.execute(
                "UPDATE budget_counters SET reserved=reserved+1 WHERE scope=? AND scope_key=?",
                tuple(row),
            )
            connection.execute("INSERT INTO reservation_scopes VALUES ('legacy', ?, ?)", tuple(row))
        connection.execute(
            "INSERT INTO reservation_scopes VALUES ('legacy', 'root_run', ?)",
            ('["tenant-a","child","run-a"]',),
        )
        budgets.migrate_root_counters(connection)
        budgets.migrate_root_counters(connection)
        connection.execute("COMMIT")
    root = [c for c in harness.store.budget_counters() if c["scope"] == "root_run"]
    assert root == [
        {"scope": "root_run", "scope_key": '["tenant-a","run-a"]', "reserved": 1, "spent": 3}
    ]
    assert harness.read().status_code == 429
    with harness.store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        budgets.settle(connection, "legacy", uncertain=False)
        budgets.settle(connection, "legacy", uncertain=False)
        connection.execute("COMMIT")
    root = [c for c in harness.store.budget_counters() if c["scope"] == "root_run"]
    assert root[0]["reserved"] == 0 and root[0]["spent"] == 4
    assert harness.read().status_code == 429


def test_initialized_v2_migrates_legacy_keys_and_blocks_start_until_migrated(harness):
    enable(harness, root_run=1)
    assert harness.read().status_code == 200
    with harness.store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO budget_counters SELECT scope,?,reserved,spent FROM budget_counters WHERE scope='root_run'",
            ('["tenant-a","analyst","run-a"]',),
        )
        connection.execute(
            "UPDATE reservation_scopes SET scope_key=? WHERE scope='root_run'",
            ('["tenant-a","analyst","run-a"]',),
        )
        connection.execute(
            "DELETE FROM budget_counters WHERE scope='root_run' AND scope_key=?",
            ('["tenant-a","run-a"]',),
        )
        connection.execute("COMMIT")
    assert not harness.store.ready()
    assert harness.read().status_code == 503
    harness.store.initialize()
    harness.store.initialize()
    assert harness.store.ready()
    assert harness.read().status_code == 429
    root = [row for row in harness.store.budget_counters() if row["scope"] == "root_run"]
    assert root == [
        {"scope": "root_run", "scope_key": '["tenant-a","run-a"]', "reserved": 0, "spent": 1}
    ]
