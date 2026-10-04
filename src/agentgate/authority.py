"""One-hop local/issuer authority resolved inside the owning SQLite transaction.

A durable committed dispatch is the revocation boundary. The separate optional
issuer adapter verifies pinned assertions; accounting Identity remains immutable.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from agentgate.authority_contracts import (
    AuthorityAttribution,
    BindingRecord,
    DelegatedBinding,
    Grant,
    HumanRecord,
    HumanSubject,
    IssuanceCeiling,
    IssuerAttribution,
    IssuerBinding,
    IssuerHumanSubject,
    MailGrant,
    ModelGrant,
    RecordGrant,
    parse_binding,
    parse_human,
)
from agentgate.contracts import Identity
from agentgate.storage import CredentialInvalid, StorageUnavailable, credential_digest

if TYPE_CHECKING:
    from agentgate.policy import Policy
    from agentgate.storage import Store

MAX_LIFETIME = 300


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def migrate(db: sqlite3.Connection) -> None:
    if "authority_kind" not in {r[1] for r in db.execute("PRAGMA table_info(credentials)")}:
        db.execute(
            "ALTER TABLE credentials ADD COLUMN authority_kind TEXT NOT NULL DEFAULT 'legacy' "
            "CHECK(authority_kind IN ('legacy','delegated'))"
        )
    # executescript would implicitly commit the caller's migration transaction.
    for statement in (
        "CREATE TABLE IF NOT EXISTS authority_schema (version INTEGER PRIMARY KEY CHECK(version=1))",
        "INSERT OR IGNORE INTO authority_schema VALUES (1)",
        "CREATE TRIGGER IF NOT EXISTS credential_authority_immutable BEFORE UPDATE OF authority_kind ON credentials BEGIN SELECT RAISE(ABORT, 'Immutable credential authority kind'); END",
        "CREATE TABLE IF NOT EXISTS human_subjects (subject_id TEXT PRIMARY KEY, record TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS delegated_bindings (child_digest TEXT PRIMARY KEY REFERENCES credentials(digest), parent_digest TEXT NOT NULL REFERENCES credentials(digest), subject_id TEXT NOT NULL REFERENCES human_subjects(subject_id), binding TEXT NOT NULL, binding_digest TEXT NOT NULL)",
        "CREATE TRIGGER IF NOT EXISTS delegation_immutable BEFORE UPDATE ON delegated_bindings BEGIN SELECT RAISE(ABORT, 'Immutable delegation'); END",
        "CREATE TABLE IF NOT EXISTS action_authority (action_id TEXT PRIMARY KEY REFERENCES tool_actions(action_id), binding TEXT NOT NULL, attribution TEXT NOT NULL)",
        "CREATE TRIGGER IF NOT EXISTS action_authority_immutable BEFORE UPDATE ON action_authority BEGIN SELECT RAISE(ABORT, 'Immutable consent authority'); END",
    ):
        db.execute(statement)
    from agentgate.issuer_trust import migrate as migrate_issuer

    migrate_issuer(db)


def subject(db: sqlite3.Connection, subject_id: str) -> HumanRecord:
    row = db.execute(
        "SELECT record FROM human_subjects WHERE subject_id=?", (subject_id,)
    ).fetchone()
    if row is None:
        raise CredentialInvalid
    human = parse_human(row[0])
    if human.subject_id != subject_id:
        raise CredentialInvalid
    return human


def provision_subject(
    store: Store, record: HumanSubject, *, expected_revision: int | None = None
) -> None:
    """Trusted operator CAS. Empty roles explicitly remove all authority."""
    if record.assertion_deadline is not None and not math.isfinite(record.assertion_deadline):
        raise ValueError("Nonfinite assertion deadline")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT record FROM human_subjects WHERE subject_id=?", (record.subject_id,)
        ).fetchone()
        if row is None:
            if expected_revision is not None or record.revision != 1:
                raise ValueError("New subject requires revision one")
            db.execute(
                "INSERT INTO human_subjects VALUES (?,?)",
                (record.subject_id, record.model_dump_json()),
            )
        else:
            old = HumanSubject.model_validate_json(row[0])
            if expected_revision != old.revision or record.revision != old.revision + 1:
                raise ValueError("Subject revision conflict")
            if (record.tenant_id, record.provenance) != (old.tenant_id, old.provenance):
                raise ValueError("Subject tenant/provenance is immutable")
            db.execute(
                "UPDATE human_subjects SET record=? WHERE subject_id=?",
                (record.model_dump_json(), record.subject_id),
            )
        db.execute("COMMIT")


def _credential(db: sqlite3.Connection, key: str, now: float) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM credentials WHERE digest=? AND revoked=0 AND expires_at>?", (key, now)
    ).fetchone()
    if row is None:
        raise CredentialInvalid
    return cast(sqlite3.Row, row)


def lifecycle(
    db: sqlite3.Connection, key: str, now: float
) -> tuple[HumanRecord, BindingRecord] | None:
    child = _credential(db, key, now)
    if "authority_kind" not in child.keys():
        raise StorageUnavailable
    if child["authority_kind"] == "legacy":
        if (
            db.execute("SELECT 1 FROM delegated_bindings WHERE child_digest=?", (key,)).fetchone()
            is not None
        ):
            raise CredentialInvalid
        return None
    row = db.execute("SELECT * FROM delegated_bindings WHERE child_digest=?", (key,)).fetchone()
    if row is None:
        raise CredentialInvalid
    try:
        binding = parse_binding(row["binding"])
        if digest(binding.model_dump(mode="json")) != row["binding_digest"]:
            raise CredentialInvalid
        parent = _credential(db, row["parent_digest"], now)
        human = subject(db, row["subject_id"])
        if (
            parent["authority_kind"] != "legacy"
            or parent["identity"] != child["identity"]
            or binding.child != key
            or binding.parent != row["parent_digest"]
            or binding.subject != human.subject_id
            or binding.revision != human.revision
            or binding.identity != child["identity"]
            or human.revoked
            or human.tenant_id != Identity.model_validate_json(child["identity"]).tenant_id
            or not now < binding.expires <= parent["expires_at"]
            or child["expires_at"] != binding.expires
            or binding.expires > binding.issued + MAX_LIFETIME
            or binding.version != human.version
            or (
                isinstance(binding, DelegatedBinding)
                and binding.deadline != human.assertion_deadline
            )
            or (human.assertion_deadline is not None and binding.expires > human.assertion_deadline)
        ):
            raise CredentialInvalid
        if isinstance(binding, IssuerBinding):
            from agentgate.issuer_trust import check_binding

            if not isinstance(human, IssuerHumanSubject):
                raise CredentialInvalid
            check_binding(db, binding, human, Identity.model_validate_json(child["identity"]))
        return human, binding
    except (KeyError, TypeError, ValueError) as error:
        raise CredentialInvalid from error


def matches(
    grants: tuple[Grant, ...], operation: str, resource: str | None, classification: str | None
) -> bool:
    return any(
        g.operation == operation
        and (
            isinstance(g, RecordGrant)
            and resource in g.resources
            and classification in g.classifications
            or isinstance(g, MailGrant)
            and resource in g.domains
            or isinstance(g, ModelGrant)
            and resource in g.models
        )
        for g in grants
    )


@dataclass(frozen=True)
class EffectiveAuthority:
    identity: Identity
    human: HumanRecord | None = None
    binding: BindingRecord | None = None
    human_grants: tuple[Grant, ...] = ()
    agent_grants: tuple[Grant, ...] = ()
    ceiling: IssuanceCeiling | None = None
    required_operations: tuple[str, ...] = ()

    def allows(
        self, operation: str, resource: str | None = None, classification: str | None = None
    ) -> bool:
        if operation not in self.identity.operations:
            return False
        if self.human is None:
            return operation not in self.required_operations
        assert self.ceiling is not None
        return all(
            matches(g, operation, resource, classification)
            for g in (self.human_grants, self.agent_grants, self.ceiling.human, self.ceiling.agent)
        )

    def record_predicate(self, operation: str) -> tuple[str, list[str]]:
        """Bound relational predicates evaluated in SQL before content is touched."""
        if self.human is None:
            return ("0" if operation in self.required_operations else "1"), []
        assert self.ceiling is not None
        groups: list[str] = []
        values: list[str] = []
        for grants in (
            self.human_grants,
            self.agent_grants,
            self.ceiling.human,
            self.ceiling.agent,
        ):
            terms = []
            for grant in grants:
                if isinstance(grant, RecordGrant) and grant.operation == operation:
                    terms.append(
                        "(entry_id IN (SELECT value FROM json_each(?)) AND classification IN (SELECT value FROM json_each(?)))"
                    )
                    values.extend((json.dumps(grant.resources), json.dumps(grant.classifications)))
            groups.append("(" + " OR ".join(terms or ["0"]) + ")")
        return " AND ".join(groups), values

    @property
    def attribution(self) -> AuthorityAttribution | IssuerAttribution | None:
        if self.human is None or self.binding is None:
            return None
        if isinstance(self.human, IssuerHumanSubject) and isinstance(self.binding, IssuerBinding):
            return IssuerAttribution(
                accounting_principal=self.identity.principal_id,
                human_subject=self.human.subject_id,
                agent_id=self.identity.agent_id,
                delegation_id=digest(self.binding.model_dump(mode="json")),
                subject_revision=self.human.revision,
                department=self.human.department,
                issuer_id=self.human.issuer_profile,
                trust_version=self.binding.trust_generation,
            )
        if not isinstance(self.human, HumanSubject):
            raise CredentialInvalid
        return AuthorityAttribution(
            accounting_principal=self.identity.principal_id,
            human_subject=self.human.subject_id,
            agent_id=self.identity.agent_id,
            delegation_id=digest(self.binding.model_dump(mode="json")),
            provenance=self.human.provenance,
            subject_revision=self.human.revision,
            department=self.human.department,
        )

    def consent_binding(self, resource: str) -> dict[str, object] | None:
        if self.human is None:
            return None
        return {
            "version": self.human.version,
            "delegation": self.binding.model_dump(mode="json") if self.binding else None,
            "human": self.human.model_dump(mode="json"),
            "human_grants": [g.model_dump(mode="json") for g in self.human_grants],
            "agent_grants": [g.model_dump(mode="json") for g in self.agent_grants],
            "operation": "mail.send",
            "metadata": {"recipient_domain": resource},
        }


def resolve(
    db: sqlite3.Connection, key: str, identity: Identity, policy: Policy, now: float
) -> EffectiveAuthority:
    row = _credential(db, key, now)
    if Identity.model_validate_json(row["identity"]) != identity:
        raise CredentialInvalid
    local = lifecycle(db, key, now)
    config = policy.delegation
    if local is None:
        required = tuple(
            op
            for r in (config.required if config else ())
            if (r.tenant_id, r.agent_id) == (identity.tenant_id, identity.agent_id)
            for op in r.operations
        )
        return EffectiveAuthority(identity, required_operations=required)
    human, binding = local
    ceiling = binding.ceiling
    return EffectiveAuthority(
        identity,
        human,
        binding,
        config.grants_for(human.roles) if config else (),
        config.grants_for(identity.roles) if config else (),
        ceiling,
    )


def issue_child(
    store: Store,
    parent_token: str,
    subject_id: str,
    policy: Policy,
    *,
    now: float,
    lifetime: int = MAX_LIFETIME,
    persist: Callable[[str], None] | None = None,
    before_issue: Callable[[sqlite3.Connection], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> str:
    """Private local provisioning only; never exposed as agent issuance/renewal."""
    if not math.isfinite(now) or type(lifetime) is not int or not 1 <= lifetime <= MAX_LIFETIME:
        raise ValueError("Child lifetime must be 1..300 seconds")
    if policy.delegation is None:
        raise ValueError("Delegation policy required")
    token = secrets.token_urlsafe(32)
    key, parent_key = credential_digest(token), credential_digest(parent_token)
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if before_issue:
            before_issue(db)
        if clock is not None:
            now = clock()
            if not math.isfinite(now):
                raise ValueError("Nonfinite issuance clock")
        parent = _credential(db, parent_key, now)
        if parent["authority_kind"] != "legacy":
            raise ValueError("Children cannot delegate or renew")
        identity = Identity.model_validate_json(parent["identity"])
        human = subject(db, subject_id)
        if (
            not isinstance(human, HumanSubject)
            or human.revoked
            or human.tenant_id != identity.tenant_id
        ):
            raise CredentialInvalid
        expires = min(
            now + lifetime,
            parent["expires_at"],
            human.assertion_deadline if human.assertion_deadline is not None else math.inf,
        )
        if expires <= now:
            raise CredentialInvalid
        ceiling = IssuanceCeiling(
            human=policy.delegation.grants_for(human.roles),
            agent=policy.delegation.grants_for(identity.roles),
        )
        binding = {
            "version": 1,
            "child": key,
            "parent": parent_key,
            "subject": human.subject_id,
            "revision": human.revision,
            "identity": parent["identity"],
            "issued": now,
            "expires": expires,
            "deadline": human.assertion_deadline,
            "issuance_policy": digest(policy.model_dump(mode="json")),
            "trust_version": 1,
            "ceiling": ceiling.model_dump(mode="json"),
        }
        binding = DelegatedBinding.model_validate_json(canonical(binding)).model_dump(mode="json")
        db.execute(
            "INSERT INTO credentials(digest,identity,expires_at,authority_kind) VALUES (?,?,?,'delegated')",
            (key, parent["identity"], expires),
        )
        db.execute(
            "INSERT INTO delegated_bindings VALUES (?,?,?,?,?)",
            (key, parent_key, human.subject_id, canonical(binding), digest(binding)),
        )
        if persist:
            persist(token)
        db.execute("COMMIT")
    return token
