"""SQLite credential binding and minimized, append-only audit events."""

import hashlib
import math
import secrets
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from agentgate import budgets
from agentgate.budgets import ToolBudgets
from agentgate.contracts import AuditEvent, Identity
from agentgate.scoped_contracts import SCHEMA as TOOL_SCHEMA


class StorageUnavailable(Exception):
    pass


class CredentialInvalid(Exception):
    pass


def credential_digest(token: str) -> str:
    # Credentials contain 256 random bits; unlike low-entropy payloads, SHA-256 is suitable here.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=1, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
        except (sqlite3.Error, ValidationError) as error:
            raise StorageUnavailable from error
        finally:
            if connection is not None:
                connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise StorageUnavailable
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS credentials (
                    digest TEXT PRIMARY KEY,
                    identity TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0, 1))
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    action_id TEXT NOT NULL,
                    event TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS audit_action ON audit_events(action_id);
                CREATE TABLE IF NOT EXISTS health_probe (id INTEGER PRIMARY KEY CHECK(id = 1));
            """
                + budgets.SCHEMA
                + TOOL_SCHEMA
                + "PRAGMA user_version=2;"
            )
            from agentgate.authority import migrate

            migrate(connection)
            from agentgate.model_budgets import migrate as migrate_model

            migrate_model(connection)
            budgets.migrate_root_counters(connection)
            connection.execute("COMMIT")
        self.path.chmod(0o600)

    def issue(self, identity: Identity, expires_at: float) -> str:
        if not math.isfinite(expires_at):
            raise ValueError("Credential expiry must be finite")
        token = secrets.token_urlsafe(32)
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO credentials(digest, identity, expires_at) VALUES (?, ?, ?)",
                (credential_digest(token), identity.model_dump_json(), expires_at),
            )
        return token

    def revoke(self, token: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE credentials SET revoked=1 WHERE digest=?", (credential_digest(token),)
            )

    @staticmethod
    def _resolve(connection: sqlite3.Connection, digest: str, now: float) -> Identity:
        row = connection.execute(
            "SELECT identity FROM credentials WHERE digest=? AND revoked=0 AND expires_at>?",
            (digest, now),
        ).fetchone()
        if row is None:
            raise CredentialInvalid
        from agentgate.authority import lifecycle

        columns = {r[1] for r in connection.execute("PRAGMA table_info(credentials)")}
        # Preserve read-only credential resolution for genuine schema-1 backups
        # and failed migrations. Such databases are never ready to serve.
        legacy_backup = (
            "authority_kind" not in columns
            and connection.execute("PRAGMA user_version").fetchone()[0] == 1
            and connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name IN ('authority_schema','delegated_bindings','human_subjects','action_authority') LIMIT 1"
            ).fetchone()
            is None
        )
        if not legacy_backup:
            if "authority_kind" not in columns:
                raise StorageUnavailable
            lifecycle(connection, digest, now)
        return Identity.model_validate_json(row["identity"])

    def resolve(self, digest: str, now: float) -> Identity:
        with self.connection() as connection:
            return self._resolve(connection, digest, now)

    @staticmethod
    def _append(connection: sqlite3.Connection, event: AuditEvent) -> None:
        connection.execute(
            "INSERT INTO audit_events(event_id, action_id, event) VALUES (?, ?, ?)",
            (event.event_id, event.action_id, event.model_dump_json()),
        )

    def append(self, event: AuditEvent) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if event.executed:
                budgets.settle(
                    connection, event.action_id, uncertain=event.event_type == "execution_failed"
                )
            self._append(connection, event)
            connection.execute("COMMIT")

    def dispatch_intent(
        self,
        digest: str,
        identity: Identity,
        event: AuditEvent,
        clock: Callable[[], float],
        limits: ToolBudgets | None = None,
        before_dispatch: Callable[[sqlite3.Connection], None] | None = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            # Lock acquisition can wait; never authorize using a timestamp sampled before it.
            now = clock()
            if self._resolve(connection, digest, now) != identity:
                raise CredentialInvalid
            if before_dispatch is not None:
                before_dispatch(connection)
            if limits is not None:
                budgets.reserve(
                    connection, event.action_id, identity, limits, now, event.policy_version
                )
            self._append(connection, event)
            connection.execute("COMMIT")

    def ready(self) -> bool:
        try:
            with self.connection() as connection:
                if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
                    return False
                connection.execute(
                    "SELECT digest, identity, expires_at, revoked FROM credentials LIMIT 0"
                )
                connection.execute("SELECT event_id, action_id, event FROM audit_events LIMIT 0")
                connection.execute(
                    "SELECT scope, scope_key, reserved, spent FROM budget_counters LIMIT 0"
                )
                connection.execute(
                    "SELECT action_id, state, created_at, policy_version FROM tool_reservations LIMIT 0"
                )
                connection.execute(
                    "SELECT action_id, scope, scope_key FROM reservation_scopes LIMIT 0"
                )
                if (
                    connection.execute(
                        "SELECT version FROM scoped_tool_schema WHERE version=1"
                    ).fetchone()
                    is None
                ):
                    return False
                if (
                    connection.execute(
                        "SELECT version FROM authority_schema WHERE version=1"
                    ).fetchone()
                    is None
                ):
                    return False
                connection.execute("SELECT authority_kind FROM credentials LIMIT 0")
                connection.execute("SELECT subject_id,record FROM human_subjects LIMIT 0")
                connection.execute(
                    "SELECT child_digest,parent_digest,subject_id,binding,binding_digest FROM delegated_bindings LIMIT 0"
                )
                connection.execute(
                    "SELECT action_id,binding,attribution FROM action_authority LIMIT 0"
                )
                if connection.execute(
                    "SELECT 1 FROM credentials c LEFT JOIN delegated_bindings b ON b.child_digest=c.digest WHERE c.authority_kind='delegated' AND b.child_digest IS NULL LIMIT 1"
                ).fetchone():
                    return False
                connection.execute("SELECT action_id,state FROM tool_actions LIMIT 0")
                if [r[0] for r in connection.execute("SELECT version FROM model_usage_schema")] != [
                    1
                ]:
                    return False
                connection.execute("SELECT action_id,attribution FROM model_attribution LIMIT 0")
                connection.execute(
                    "SELECT action_id,input_tokens,output_tokens,simulated_micro_usd FROM model_settlement LIMIT 0"
                )
                connection.execute("SELECT action_id FROM tool_outbox LIMIT 0")
                connection.execute("SELECT tenant_id,entry_id FROM memory_entries LIMIT 0")
                if connection.execute(
                    "SELECT 1 FROM budget_counters WHERE scope='root_run' "
                    "AND json_array_length(scope_key)!=2 LIMIT 1"
                ).fetchone():
                    return False
                connection.execute("INSERT OR REPLACE INTO health_probe(id) VALUES (1)")
            return True
        except StorageUnavailable:
            return False

    def events(self, limit: int = 100) -> list[AuditEvent]:
        if not 1 <= limit <= 1000:
            raise ValueError("Event limit must be between 1 and 1000")
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT event FROM audit_events ORDER BY sequence DESC LIMIT ?", (limit,)
            ).fetchall()
        return [AuditEvent.model_validate_json(row["event"]) for row in reversed(rows)]

    def budget_counters(self, limit: int = 100) -> list[dict[str, str | int]]:
        if not 1 <= limit <= 1000:
            raise ValueError("Counter limit must be between 1 and 1000")
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT scope, scope_key, reserved, spent FROM budget_counters "
                "ORDER BY scope, scope_key LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
