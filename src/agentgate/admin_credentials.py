"""Trusted operator renewal; never renew authority while serving an agent request."""

import base64
import hashlib
import hmac
import math
import re
import secrets
import sqlite3
from collections.abc import Callable
from typing import Literal, TypedDict

from agentgate.contracts import Identity
from agentgate.service import ActionService
from agentgate.storage import StorageUnavailable, Store, credential_digest

LIFETIME = 86400
Scope = Literal["tools", "model"]
RenewalReason = Literal["missing", "revoked", "active", "conflict"]


class CredentialRenewalError(Exception):
    def __init__(self, reason: RenewalReason) -> None:
        self.reason = reason
        super().__init__(reason)


class CredentialStatus(TypedDict):
    scope: Scope
    epoch: int
    state: Literal["unissued", "active", "expired", "revoked"]
    expires_at: float | None


def _schema(db: sqlite3.Connection) -> None:
    # Additive, idempotent schema-2 extensions; no changes to budget/approval rows.
    db.execute(
        "CREATE TABLE IF NOT EXISTS operator_credential_epochs ("
        "scope TEXT PRIMARY KEY CHECK(scope IN ('tools','model')), "
        "epoch INTEGER NOT NULL CHECK(epoch>=0))"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS credential_renewals ("
        "old_digest TEXT PRIMARY KEY REFERENCES credentials(digest), "
        "new_digest TEXT NOT NULL UNIQUE REFERENCES credentials(digest), "
        "purpose TEXT NOT NULL, renewed_at REAL NOT NULL, expires_at REAL NOT NULL)"
    )


def _epoch(db: sqlite3.Connection, scope: Scope) -> int:
    row = db.execute(
        "SELECT epoch FROM operator_credential_epochs WHERE scope=?", (scope,)
    ).fetchone()
    return int(row[0]) if row else 0


def _token(service: ActionService, scope: Scope, epoch: int) -> str:
    domain = (
        b"operator-model-playground-credential-v1"
        if scope == "model"
        else b"operator-playground-credential-v1"
    )
    # Preserve previously issued epoch zero credentials, including model PR6.
    if epoch:
        domain += b":epoch:" + str(epoch).encode("ascii")
    return (
        base64.urlsafe_b64encode(hmac.new(service.audit_key, domain, hashlib.sha256).digest())
        .decode("ascii")
        .rstrip("=")
    )


def _times(now: float, expires_at: float) -> None:
    if (
        type(now) not in (int, float)
        or type(expires_at) not in (int, float)
        or not math.isfinite(now)
        or not math.isfinite(expires_at)
        or not now < expires_at <= now + LIFETIME
    ):
        raise ValueError("Renewal expiry must be within the next 24 hours")


def _replace(
    db: sqlite3.Connection, old: str, new: str, now: float, expires_at: float, purpose: str
) -> None:
    _times(now, expires_at)
    old_digest, new_digest = credential_digest(old), credential_digest(new)
    row = db.execute("SELECT * FROM credentials WHERE digest=?", (old_digest,)).fetchone()
    if row is None:
        raise CredentialRenewalError("missing")
    if row["revoked"]:
        raise CredentialRenewalError("revoked")
    if row["expires_at"] > now:
        raise CredentialRenewalError("active")
    # Validate the stored authority and copy it exactly; never accept caller scope.
    Identity.model_validate_json(row["identity"])
    db.execute(
        "INSERT INTO credentials(digest,identity,expires_at) VALUES (?,?,?)",
        (new_digest, row["identity"], expires_at),
    )
    db.execute("UPDATE credentials SET revoked=1 WHERE digest=?", (old_digest,))
    db.execute(
        "INSERT INTO credential_renewals VALUES (?,?,?,?,?)",
        (old_digest, new_digest, purpose, now, expires_at),
    )


def renew_agent_credential(
    store: Store,
    token: str,
    *,
    now: float,
    expires_at: float,
    persist: Callable[[str], None] | None = None,
) -> str:
    """Installer-only: privately persist the returned secret; no browser/agent route."""
    _times(now, expires_at)
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        raise ValueError("Invalid credential format")
    replacement = secrets.token_urlsafe(32)
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        _replace(db, token, replacement, now, expires_at, "agent")
        if persist is not None:
            # Trusted installer fsyncs a recoverable private file before authority commits.
            persist(replacement)
        db.execute("COMMIT")
    return replacement


def playground_credential(service: ActionService, *, model: bool = False) -> str:
    scope: Scope = "model" if model else "tools"
    with service.store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        epoch = _epoch(db, scope)
        token = _token(service, scope, epoch)
        digest = credential_digest(token)
        row = db.execute("SELECT 1 FROM credentials WHERE digest=?", (digest,)).fetchone()
        if row is None:
            if epoch:
                raise StorageUnavailable  # Never recreate a lost replacement's authority.
            identity = Identity(
                principal_id="operator-playground",
                tenant_id="tenant-a",
                agent_id="admin-demo",
                root_run_id="operator-playground",
                roles=("analyst",),
                operations=("chat.completions",)
                if model
                else ("documents.read", "memory.query", "mail.send"),
            )
            db.execute(
                "INSERT INTO credentials(digest,identity,expires_at) VALUES (?,?,?)",
                (digest, identity.model_dump_json(), service.clock() + LIFETIME),
            )
        db.execute("COMMIT")
    return token


def _status(
    db: sqlite3.Connection, service: ActionService, scope: Scope, epoch: int
) -> CredentialStatus:
    row = db.execute(
        "SELECT revoked,expires_at FROM credentials WHERE digest=?",
        (credential_digest(_token(service, scope, epoch)),),
    ).fetchone()
    return {
        "scope": scope,
        "epoch": epoch,
        "state": "unissued"
        if row is None
        else "revoked"
        if row["revoked"]
        else "expired"
        if row["expires_at"] <= service.clock()
        else "active",
        "expires_at": float(row["expires_at"]) if row else None,
    }


def playground_credential_status(
    service: ActionService, *, model: bool = False
) -> CredentialStatus:
    scope: Scope = "model" if model else "tools"
    with service.store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        result = _status(db, service, scope, _epoch(db, scope))
        db.execute("COMMIT")
    return result


def renew_playground_credential(
    service: ActionService, *, model: bool = False, expected_epoch: int
) -> CredentialStatus:
    if type(expected_epoch) is not int or not 0 <= expected_epoch < 2147483647:
        raise ValueError("Invalid expected epoch")
    scope: Scope = "model" if model else "tools"
    with service.store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        epoch = _epoch(db, scope)
        if epoch != expected_epoch:
            raise CredentialRenewalError("conflict")
        now = service.clock()
        _replace(
            db,
            _token(service, scope, epoch),
            _token(service, scope, epoch + 1),
            now,
            now + LIFETIME,
            scope,
        )
        db.execute(
            "INSERT INTO operator_credential_epochs VALUES (?,?) "
            "ON CONFLICT(scope) DO UPDATE SET epoch=excluded.epoch",
            (scope, epoch + 1),
        )
        result = _status(db, service, scope, epoch + 1)
        db.execute("COMMIT")
    return result
