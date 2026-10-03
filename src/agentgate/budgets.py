"""Tool-attempt accounting inside the store's authoritative write transaction."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Annotated

from pydantic import Field

from agentgate.contracts import Contract, Identity

Limit = Annotated[int, Field(ge=0, le=1_000_000_000)]


class ToolBudgets(Contract):
    tenant_day: Limit
    principal_day: Limit
    root_run: Limit


class BudgetExceeded(Exception):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_counters (
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0),
    spent INTEGER NOT NULL DEFAULT 0 CHECK(spent >= 0),
    PRIMARY KEY(scope, scope_key)
);
CREATE TABLE IF NOT EXISTS tool_reservations (
    action_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK(state IN ('dispatched', 'uncertain', 'settled')),
    created_at REAL NOT NULL,
    policy_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reservation_scopes (
    action_id TEXT NOT NULL REFERENCES tool_reservations(action_id),
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    PRIMARY KEY(action_id, scope),
    FOREIGN KEY(scope, scope_key) REFERENCES budget_counters(scope, scope_key)
);
"""


def reserve(
    connection: sqlite3.Connection,
    action_id: str,
    identity: Identity,
    limits: ToolBudgets,
    now: float,
    policy_version: str,
) -> None:
    day = datetime.fromtimestamp(now, UTC).date().isoformat()
    scopes = [
        ("tenant_day", [identity.tenant_id, day], limits.tenant_day),
        ("principal_day", [identity.tenant_id, identity.principal_id, day], limits.principal_day),
        (
            "root_run",
            [identity.tenant_id, identity.principal_id, identity.root_run_id],
            limits.root_run,
        ),
    ]
    connection.execute(
        "INSERT INTO tool_reservations VALUES (?, 'dispatched', ?, ?)",
        (action_id, now, policy_version),
    )
    for scope, components, limit in scopes:
        key = json.dumps(components, separators=(",", ":"))
        connection.execute(
            "INSERT OR IGNORE INTO budget_counters(scope, scope_key) VALUES (?, ?)", (scope, key)
        )
        changed = connection.execute(
            "UPDATE budget_counters SET reserved=reserved+1 "
            "WHERE scope=? AND scope_key=? AND reserved+spent<?",
            (scope, key, limit),
        ).rowcount
        if changed != 1:
            # The enclosing transaction rolls back all earlier scope updates.
            raise BudgetExceeded
        connection.execute(
            "INSERT INTO reservation_scopes VALUES (?, ?, ?)", (action_id, scope, key)
        )


def settle(connection: sqlite3.Connection, action_id: str, *, uncertain: bool) -> None:
    row = connection.execute(
        "SELECT state FROM tool_reservations WHERE action_id=?", (action_id,)
    ).fetchone()
    if row is None or row["state"] == "settled":
        return
    if uncertain:
        connection.execute(
            "UPDATE tool_reservations SET state='uncertain' WHERE action_id=?", (action_id,)
        )
        return
    scopes = connection.execute(
        "SELECT scope, scope_key FROM reservation_scopes WHERE action_id=?", (action_id,)
    ).fetchall()
    if len(scopes) != 3:
        raise sqlite3.IntegrityError("Incomplete reservation scopes")
    for scope in scopes:
        if (
            connection.execute(
                "UPDATE budget_counters SET reserved=reserved-1, spent=spent+1 "
                "WHERE scope=? AND scope_key=? AND reserved>=1",
                (scope["scope"], scope["scope_key"]),
            ).rowcount
            != 1
        ):
            raise sqlite3.IntegrityError("Missing reserved capacity")
    connection.execute(
        "UPDATE tool_reservations SET state='settled' WHERE action_id=?", (action_id,)
    )
