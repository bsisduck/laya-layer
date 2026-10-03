"""Atomic multi-resource reservations, credential recheck and durable model intent."""

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from agentgate.budgets import BudgetExceeded
from agentgate.contracts import AuditEvent, Identity
from agentgate.model_config import ModelPolicy
from agentgate.storage import CredentialInvalid, Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_accounts (
    scope TEXT NOT NULL, scope_key TEXT NOT NULL, resource TEXT NOT NULL,
    reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0),
    spent INTEGER NOT NULL DEFAULT 0 CHECK(spent>=0),
    frozen INTEGER NOT NULL DEFAULT 0 CHECK(frozen IN (0,1)),
    PRIMARY KEY(scope,scope_key,resource)
);
CREATE TABLE IF NOT EXISTS model_attempts (
    action_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('dispatched','uncertain','settled')),
    created_at REAL NOT NULL, tariff_revision TEXT NOT NULL,
    input_bound INTEGER NOT NULL, output_bound INTEGER NOT NULL,
    input_tariff INTEGER NOT NULL, output_tariff INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS model_reservations (
    action_id TEXT NOT NULL REFERENCES model_attempts(action_id),
    scope TEXT NOT NULL, scope_key TEXT NOT NULL, resource TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount>=0),
    PRIMARY KEY(action_id,scope,resource),
    FOREIGN KEY(scope,scope_key,resource) REFERENCES model_accounts(scope,scope_key,resource)
);
"""


class ModelLedger:
    def __init__(self, store: Store) -> None:
        self.store = store
        with store.connection() as db:
            db.executescript("BEGIN IMMEDIATE;" + SCHEMA + "COMMIT;")

    def reserve(
        self,
        digest: str,
        identity: Identity,
        event: AuditEvent,
        policy: ModelPolicy,
        input_bound: int,
        output_bound: int,
        clock: Callable[[], float],
    ) -> None:
        amounts = {
            "calls": 1,
            "tokens": input_bound + output_bound,
            "micro_usd": input_bound * policy.input_micro_usd
            + output_bound * policy.output_micro_usd,
        }
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = clock()
            if self.store._resolve(db, digest, now) != identity:
                raise CredentialInvalid
            # Uncertain requests may still be computing and retain an admission slot.
            active = db.execute(
                "SELECT COUNT(*) FROM model_attempts WHERE state!='settled'"
            ).fetchone()[0]
            if active >= policy.max_concurrent:
                raise BudgetExceeded
            day = datetime.fromtimestamp(now, UTC).date().isoformat()
            scopes = [
                ("tenant_day", [identity.tenant_id, day], policy.tenant_day),
                (
                    "principal_day",
                    [identity.tenant_id, identity.principal_id, day],
                    policy.principal_day,
                ),
                ("root_run", [identity.tenant_id, identity.root_run_id], policy.root_run),
            ]
            db.execute(
                "INSERT INTO model_attempts VALUES (?,?,'dispatched',?,?,?,?,?,?)",
                (
                    event.action_id,
                    identity.tenant_id,
                    now,
                    policy.tariff_revision,
                    input_bound,
                    output_bound,
                    policy.input_micro_usd,
                    policy.output_micro_usd,
                ),
            )
            for scope, components, limits in scopes:
                key = json.dumps(components, separators=(",", ":"))
                for resource, amount in amounts.items():
                    db.execute(
                        "INSERT OR IGNORE INTO model_accounts(scope,scope_key,resource) "
                        "VALUES (?,?,?)",
                        (scope, key, resource),
                    )
                    changed = db.execute(
                        "UPDATE model_accounts SET reserved=reserved+? "
                        "WHERE scope=? AND scope_key=? AND resource=? AND frozen=0 "
                        "AND reserved+spent+?<=?",
                        (amount, scope, key, resource, amount, getattr(limits, resource)),
                    ).rowcount
                    if changed != 1:
                        raise BudgetExceeded
                    db.execute(
                        "INSERT INTO model_reservations VALUES (?,?,?,?,?)",
                        (event.action_id, scope, key, resource, amount),
                    )
            self.store._append(db, event)
            db.execute("COMMIT")

    def finish(self, event: AuditEvent, usage: tuple[int, int] | None) -> bool:
        """Settle and audit atomically; return False when reservation bounds broke."""
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM model_attempts WHERE action_id=?", (event.action_id,)
            ).fetchone()
            if row is None or row["state"] == "settled":
                raise sqlite3.IntegrityError("Missing live model reservation")
            bounded = True
            if usage is None:
                db.execute(
                    "UPDATE model_attempts SET state='uncertain' WHERE action_id=?",
                    (event.action_id,),
                )
            else:
                inp, out = usage
                bounded = inp <= row["input_bound"] and out <= row["output_bound"]
                actual = {
                    "calls": 1,
                    "tokens": inp + out,
                    "micro_usd": inp * row["input_tariff"] + out * row["output_tariff"],
                }
                reservations = db.execute(
                    "SELECT * FROM model_reservations WHERE action_id=?", (event.action_id,)
                ).fetchall()
                if len(reservations) != 9:
                    raise sqlite3.IntegrityError("Incomplete model reservation")
                for reservation in reservations:
                    changed = db.execute(
                        "UPDATE model_accounts SET reserved=reserved-?,spent=spent+?,"
                        "frozen=MAX(frozen,?) WHERE scope=? AND scope_key=? AND resource=? "
                        "AND reserved>=?",
                        (
                            reservation["amount"],
                            actual[reservation["resource"]],
                            int(not bounded),
                            reservation["scope"],
                            reservation["scope_key"],
                            reservation["resource"],
                            reservation["amount"],
                        ),
                    ).rowcount
                    if changed != 1:
                        raise sqlite3.IntegrityError("Missing reserved model capacity")
                db.execute(
                    "UPDATE model_attempts SET state='settled' WHERE action_id=?",
                    (event.action_id,),
                )
            self.store._append(db, event)
            db.execute("COMMIT")
            return bounded

    def counters(self) -> list[dict[str, str | int]]:
        with self.store.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM model_accounts ORDER BY scope,scope_key,resource LIMIT 1000"
                )
            ]
