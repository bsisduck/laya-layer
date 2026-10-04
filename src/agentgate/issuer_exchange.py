"""Pinned person access tokens become bounded children, never browser sessions."""

from __future__ import annotations

import math
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

import jwt

from agentgate.authority import canonical, digest, subject
from agentgate.authority_contracts import IssuanceCeiling, IssuerBinding, IssuerHumanSubject
from agentgate.contracts import Identity
from agentgate.issuer_trust import (
    IssuerProfile,
    TrustSnapshot,
    load_trust,
    subject_id,
    token_parts,
)
from agentgate.service import ActionService, Context
from agentgate.storage import CredentialInvalid, Store, credential_digest


class ExchangeLimit(Exception):
    pass


@dataclass(frozen=True)
class Assertion:
    profile: IssuerProfile
    subject_id: str
    tenant_id: str
    roles: tuple[str, ...]
    department: str
    client_id: str
    iat: int
    exp: int
    nbf: int
    auth_time: int

    @property
    def deadline(self) -> float:
        return float(
            min(
                self.exp,
                self.iat + self.profile.max_assertion_age,
                self.auth_time + self.profile.max_auth_age,
            )
        )

    def valid_at(self, now: float) -> None:
        skew = self.profile.clock_skew
        if (
            not math.isfinite(now)
            or now >= self.deadline
            or self.iat > now + skew
            or self.nbf > now + skew
            or self.auth_time > now + skew
            or self.exp <= self.iat
            or self.nbf >= self.exp
            or self.auth_time > self.iat + skew
        ):
            raise CredentialInvalid


def verify(
    token: str, trust: TrustSnapshot, parent: str, identity: Identity, now: float
) -> Assertion:
    """The unverified issuer/kid only selects an already-pinned local key."""
    try:
        header, raw = token_parts(token)
        profile = next(p for p in trust.config.profiles if p.issuer == raw.get("iss") and p.enabled)
        required = [
            "iss",
            "sub",
            "aud",
            "exp",
            "iat",
            "nbf",
            "auth_time",
            profile.person_claim,
            profile.client_claim,
            profile.tenant_claim,
            profile.groups_claim,
        ]
        if set(raw) != set(required):
            raise CredentialInvalid
        key = next(k for k in profile.keys if k.kid == header["kid"])
        # Signature, exact issuer/audience and required claims use the pinned API.
        # Strict time types and validity use the injected clock below and again
        # AFTER BEGIN IMMEDIATE, rather than PyJWT's process wall clock.
        claims = jwt.decode(
            token,
            jwt.PyJWK.from_dict(key.model_dump(), algorithm="RS256"),
            algorithms=["RS256"],
            issuer=profile.issuer,
            audience=profile.audience,
            options={
                "require": required,
                "strict_aud": True,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
        if claims != raw:
            raise CredentialInvalid
        for name in (
            "iss",
            "sub",
            "aud",
            profile.person_claim,
            profile.client_claim,
            profile.tenant_claim,
        ):
            value = claims[name]
            if not isinstance(value, str) or not 1 <= len(value.encode("utf-8")) <= 512:
                raise CredentialInvalid
        for name in ("exp", "iat", "nbf", "auth_time"):
            if type(claims[name]) is not int or not 0 <= claims[name] <= 253402300799:
                raise CredentialInvalid
        if claims[profile.person_claim] != profile.person_value or not profile.permits(
            parent, identity, claims[profile.client_claim]
        ):
            raise CredentialInvalid
        tenant = next(
            m.tenant_id for m in profile.tenants if m.value == claims[profile.tenant_claim]
        )
        if tenant != identity.tenant_id:
            raise CredentialInvalid
        groups = claims[profile.groups_claim]
        if (
            not isinstance(groups, list)
            or not 1 <= len(groups) <= 32
            or any(not isinstance(g, str) or not 1 <= len(g.encode("utf-8")) <= 256 for g in groups)
            or len(set(groups)) != len(groups)
        ):
            raise CredentialInvalid
        mapped = [next(m for m in profile.groups if m.value == g) for g in groups]
        if len({m.department for m in mapped}) != 1:
            raise CredentialInvalid
        roles = tuple(sorted({role for m in mapped for role in m.roles}))
        if len(roles) > 32:
            raise CredentialInvalid
        result = Assertion(
            profile,
            subject_id(profile.issuer, claims["sub"]),
            tenant,
            roles,
            mapped[0].department,
            claims[profile.client_claim],
            claims["iat"],
            claims["exp"],
            claims["nbf"],
            claims["auth_time"],
        )
        result.valid_at(now)
        return result
    except (
        jwt.PyJWTError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        UnicodeError,
        RecursionError,
    ) as error:
        raise CredentialInvalid from error


def _refresh(db: sqlite3.Connection, assertion: Assertion) -> IssuerHumanSubject:
    authority = digest([assertion.tenant_id, assertion.roles, assertion.department])
    row = db.execute(
        "SELECT assertion_iat,authority_digest FROM issuer_assertion_order WHERE subject_id=?",
        (assertion.subject_id,),
    ).fetchone()
    human_row = db.execute(
        "SELECT 1 FROM human_subjects WHERE subject_id=?", (assertion.subject_id,)
    ).fetchone()
    revision = 1
    deadline = None
    if human_row:
        old = subject(db, assertion.subject_id)
        if not isinstance(old, IssuerHumanSubject) or old.revoked or row is None:
            raise CredentialInvalid
        if old.issuer_profile != assertion.profile.profile_id:
            raise CredentialInvalid
        changed = authority != row["authority_digest"]
        if changed and assertion.iat <= row["assertion_iat"]:
            raise CredentialInvalid
        revision = old.revision + int(changed)
        deadline = old.assertion_deadline
    elif row is not None:
        raise CredentialInvalid
    human = IssuerHumanSubject(
        subject_id=assertion.subject_id,
        tenant_id=assertion.tenant_id,
        roles=assertion.roles,
        department=assertion.department,
        revision=revision,
        assertion_deadline=deadline,
        issuer_profile=assertion.profile.profile_id,
    )
    db.execute(
        "INSERT INTO human_subjects VALUES (?,?) ON CONFLICT(subject_id) DO UPDATE SET record=excluded.record",
        (human.subject_id, human.model_dump_json()),
    )
    db.execute(
        "INSERT INTO issuer_assertion_order VALUES (?,?,?) ON CONFLICT(subject_id) DO UPDATE SET assertion_iat=MAX(assertion_iat,excluded.assertion_iat),authority_digest=excluded.authority_digest",
        (human.subject_id, assertion.iat, authority),
    )
    return human


def exchange(
    service: ActionService,
    context: Context,
    human_token: str,
    *,
    before_write: Callable[[], None] | None = None,
) -> tuple[str, float]:
    """One owning transaction for refresh, bounded admission, issue and audit.

    Invalid verification attempts consume the bounded per-parent admission counter and
    sanitized denial audit, without persisting the assertion or changing humans.
    Verification is bounded and preflight-limited; transaction rechecks remain
    authoritative. All durable child rows count toward a lifetime growth cap.
    """
    assert context.credential_digest is not None and context.identity is not None
    parent_key, identity = context.credential_digest, context.identity
    controls = service.context_controls(context)
    with service.store.connection() as db:
        trust = load_trust(db)
        candidates = [
            p
            for p in trust.config.profiles
            if p.enabled
            and any(
                (m.parent, m.agent_id, m.tenant_id)
                == (parent_key, identity.agent_id, identity.tenant_id)
                for m in p.parents
            )
        ]
        if not candidates:
            raise CredentialInvalid
        day = int(service.clock() // 86400)
        limit = min(p.exchanges_per_day for p in candidates)
        admission = db.execute(
            "SELECT day,count FROM issuer_admission WHERE parent_digest=?", (parent_key,)
        ).fetchone()
        if admission and admission["day"] == day and admission["count"] >= limit:
            raise ExchangeLimit
    try:
        assertion = verify(human_token, trust, parent_key, identity, service.clock())
    except CredentialInvalid:
        assertion = None
    if before_write:
        before_write()
    token = secrets.token_urlsafe(32)
    key = credential_digest(token)
    denial: CredentialInvalid | ExchangeLimit | None = None
    with service.store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        now = service.clock()
        if not math.isfinite(now):
            raise CredentialInvalid
        trust.assert_current(db)
        controls.assert_current(db)
        # Re-resolve in the owning transaction, including parent revocation.
        if service.store._resolve(db, parent_key, now) != identity:
            raise CredentialInvalid
        parent = db.execute("SELECT * FROM credentials WHERE digest=?", (parent_key,)).fetchone()
        if parent is None or parent["authority_kind"] != "legacy":
            raise CredentialInvalid
        day = int(now // 86400)
        admission = db.execute(
            "SELECT day,count FROM issuer_admission WHERE parent_digest=?", (parent_key,)
        ).fetchone()
        used = admission["count"] if admission and admission["day"] == day else 0
        if used >= limit:
            raise ExchangeLimit
        db.execute(
            "INSERT INTO issuer_admission VALUES (?,?,?) ON CONFLICT(parent_digest) DO UPDATE SET day=excluded.day,count=excluded.count",
            (parent_key, day, used + 1),
        )
        expires = now
        db.execute("SAVEPOINT authority_mutations")
        try:
            if assertion is None:
                raise CredentialInvalid
            assertion.valid_at(now)
            profile = assertion.profile
            if not profile.permits(parent_key, identity, assertion.client_id):
                raise CredentialInvalid
            config = controls.policy.delegation
            if config is None or not set(assertion.roles).issubset(
                {p.role_id for p in config.profiles}
            ):
                raise CredentialInvalid
            counts = db.execute(
                "SELECT COUNT(*) AS total,SUM(c.revoked=0 AND c.expires_at>?) AS active FROM delegated_bindings b JOIN credentials c ON c.digest=b.child_digest WHERE b.parent_digest=?",
                (now, parent_key),
            ).fetchone()
            if counts["total"] >= min(p.max_total_children for p in candidates) or (
                counts["active"] or 0
            ) >= min(p.max_active_children for p in candidates):
                raise ExchangeLimit
            human = _refresh(db, assertion)
            expires = min(
                now + profile.child_lifetime,
                parent["expires_at"],
                assertion.deadline,
                human.assertion_deadline if human.assertion_deadline is not None else math.inf,
            )
            if expires <= now:
                raise CredentialInvalid
            binding = IssuerBinding(
                child=key,
                parent=parent_key,
                subject=human.subject_id,
                revision=human.revision,
                identity=parent["identity"],
                issued=now,
                expires=float(expires),
                deadline=assertion.deadline,
                issuance_policy=digest(controls.policy.model_dump(mode="json")),
                ceiling=IssuanceCeiling(
                    human=config.grants_for(human.roles), agent=config.grants_for(identity.roles)
                ),
                issuer_profile=profile.profile_id,
                trust_generation=trust.generation,
                client_claim=profile.client_claim,
                client_id=assertion.client_id,
                assertion_expires=assertion.exp,
                assertion_iat=assertion.iat,
                assertion_auth_time=assertion.auth_time,
            ).model_dump(mode="json")
            db.execute(
                "INSERT INTO credentials(digest,identity,expires_at,authority_kind) VALUES (?,?,?,'delegated')",
                (key, parent["identity"], expires),
            )
            db.execute(
                "INSERT INTO delegated_bindings VALUES (?,?,?,?,?)",
                (key, parent_key, human.subject_id, canonical(binding), digest(binding)),
            )
            db.execute(
                "INSERT INTO issuer_events(timestamp,kind,generation,parent_digest,child_digest,subject_id) VALUES (?,'child_issued',?,?,?,?)",
                (now, trust.generation, parent_key, key, human.subject_id),
            )
        except (CredentialInvalid, ExchangeLimit) as error:
            # Business denial commits only admission and a minimized denial.
            # Authority/child mutations never escape the savepoint. Any audit or
            # storage error propagates and rolls back the WHOLE transaction.
            db.execute("ROLLBACK TO authority_mutations")
            denial = error
            db.execute(
                "INSERT INTO issuer_events(timestamp,kind,generation,parent_digest) VALUES (?,'exchange_denied',?,?)",
                (now, trust.generation, parent_key),
            )
        db.execute("RELEASE authority_mutations")
        db.execute("COMMIT")
    if denial is not None:
        raise denial
    return token, expires


def revoke_subject(store: Store, subject_id: str, expected_revision: int) -> None:
    """Trusted operator tombstone; exchange cannot clear it."""
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        human = subject(db, subject_id)
        if human.revision != expected_revision:
            raise ValueError("Subject revision conflict")
        record = human.model_copy(update={"revoked": True, "revision": human.revision + 1})
        db.execute(
            "UPDATE human_subjects SET record=? WHERE subject_id=?",
            (record.model_dump_json(), subject_id),
        )
        db.execute("COMMIT")
