"""Offline public trust snapshots. No URL discovery or network key loading."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, NoReturn, Self

import jwt
from pydantic import Field, model_validator

from agentgate.authority_contracts import IssuerBinding, IssuerHumanSubject
from agentgate.contracts import Contract, Identifier, Identity
from agentgate.storage import CredentialInvalid, Store

MAX_TRUST_BYTES = 65536
MAX_TOKEN_BYTES = 16384
Text = Annotated[str, Field(min_length=1, max_length=256)]


def subject_id(issuer: str, sub: str) -> str:
    pair = json.dumps([issuer, sub], ensure_ascii=True, separators=(",", ":"))
    return "issuer-" + hashlib.sha256(pair.encode("ascii")).hexdigest()


class PublicKey(Contract):
    kty: Literal["RSA"]
    kid: Identifier
    use: Literal["sig"] = "sig"
    alg: Literal["RS256"] = "RS256"
    n: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", min_length=342, max_length=1366)]
    e: Literal["AQAB"] = "AQAB"
    key_ops: tuple[Literal["verify"], ...] = ("verify",)

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        if self.key_ops != ("verify",):
            raise ValueError("Public key must permit verification only")
        modulus = int.from_bytes(base64.urlsafe_b64decode(self.n + "=" * (-len(self.n) % 4)))
        if not 2048 <= modulus.bit_length() <= 8192:
            raise ValueError("RSA modulus must be 2048..8192 bits")
        jwt.PyJWK.from_dict(self.model_dump(), algorithm="RS256")
        return self


class TenantMapping(Contract):
    value: Text
    tenant_id: Identifier


class GroupMapping(Contract):
    value: Text
    roles: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=32)]
    department: Identifier


class ParentMapping(Contract):
    """Exact credential digest is required; agent and tenant are also rechecked."""

    parent: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    agent_id: Identifier
    tenant_id: Identifier
    client_id: Text


class IssuerProfile(Contract):
    profile_id: Identifier
    enabled: bool = True
    issuer: Annotated[str, Field(min_length=1, max_length=512, pattern=r"^https://[^\s]+$")]
    audience: Text
    algorithm: Literal["RS256"] = "RS256"
    keys: Annotated[tuple[PublicKey, ...], Field(min_length=1, max_length=8)]
    person_claim: Identifier = "idtyp"
    person_value: Text = "user"
    client_claim: Literal["client_id", "azp"] = "client_id"
    tenant_claim: Identifier = "tid"
    groups_claim: Identifier = "groups"
    tenants: Annotated[tuple[TenantMapping, ...], Field(min_length=1, max_length=32)]
    groups: Annotated[tuple[GroupMapping, ...], Field(min_length=1, max_length=32)]
    parents: Annotated[tuple[ParentMapping, ...], Field(min_length=1, max_length=32)]
    max_assertion_age: Annotated[int, Field(ge=1, le=300)] = 120
    max_auth_age: Annotated[int, Field(ge=1, le=3600)] = 300
    clock_skew: Annotated[int, Field(ge=0, le=5)] = 2
    child_lifetime: Annotated[int, Field(ge=1, le=300)] = 120
    max_active_children: Annotated[int, Field(ge=1, le=64)] = 8
    max_total_children: Annotated[int, Field(ge=1, le=4096)] = 128
    exchanges_per_day: Annotated[int, Field(ge=1, le=4096)] = 128

    @model_validator(mode="after")
    def unique(self) -> Self:
        for values in (
            [k.kid for k in self.keys],
            [t.value for t in self.tenants],
            [g.value for g in self.groups],
            [p.parent for p in self.parents],
        ):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate trust mapping")
        names = (self.person_claim, self.client_claim, self.tenant_claim, self.groups_claim)
        if len(set(names)) != 4 or set(names) & {
            "iss",
            "sub",
            "aud",
            "exp",
            "iat",
            "nbf",
            "auth_time",
        }:
            raise ValueError("Overlapping claim names")
        if any(p.tenant_id not in {m.tenant_id for m in self.tenants} for p in self.parents):
            raise ValueError("Parent tenant must have an explicit signed tenant mapping")
        if self.max_active_children > self.max_total_children:
            raise ValueError("Active limit exceeds total limit")
        return self

    def permits(self, parent: str, identity: Identity, client: str) -> bool:
        return any(
            (p.parent, p.agent_id, p.tenant_id, p.client_id)
            == (parent, identity.agent_id, identity.tenant_id, client)
            for p in self.parents
        )


class TrustConfig(Contract):
    version: Literal[1] = 1
    profiles: Annotated[tuple[IssuerProfile, ...], Field(max_length=8)] = ()

    @model_validator(mode="after")
    def bounded(self) -> Self:
        for values in ([p.profile_id for p in self.profiles], [p.issuer for p in self.profiles]):
            if len(set(values)) != len(values):
                raise ValueError("Duplicate issuer profile")
        if len(self.model_dump_json().encode()) > MAX_TRUST_BYTES:
            raise ValueError("Public trust exceeds 64 KiB")
        return self


@dataclass(frozen=True)
class TrustSnapshot:
    generation: int
    config: TrustConfig

    def profile(self, profile_id: str) -> IssuerProfile:
        for profile in self.config.profiles:
            if profile.profile_id == profile_id and profile.enabled:
                return profile
        raise CredentialInvalid

    def assert_current(self, db: sqlite3.Connection) -> None:
        if load_trust(db).generation != self.generation:
            raise CredentialInvalid


def migrate(db: sqlite3.Connection) -> None:
    for sql in (
        "CREATE TABLE IF NOT EXISTS issuer_schema (version INTEGER PRIMARY KEY CHECK(version=1))",
        "INSERT OR IGNORE INTO issuer_schema VALUES (1)",
        "CREATE TABLE IF NOT EXISTS issuer_trust (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL, config TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS issuer_assertion_order (subject_id TEXT PRIMARY KEY REFERENCES human_subjects(subject_id), assertion_iat INTEGER NOT NULL, authority_digest TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS issuer_admission (parent_digest TEXT PRIMARY KEY REFERENCES credentials(digest), day INTEGER NOT NULL, count INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS issuer_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, kind TEXT NOT NULL, generation INTEGER NOT NULL, parent_digest TEXT, child_digest TEXT, subject_id TEXT)",
    ):
        db.execute(sql)


def load_trust(db: sqlite3.Connection) -> TrustSnapshot:
    row = db.execute("SELECT generation,config FROM issuer_trust WHERE id=1").fetchone()
    if row is None:
        return TrustSnapshot(0, TrustConfig())
    return TrustSnapshot(row[0], TrustConfig.model_validate_json(row[1]))


def import_trust(
    store: Store, config: TrustConfig, expected_generation: int, clock: Callable[[], float]
) -> int:
    config = TrustConfig.model_validate_json(config.model_dump_json())
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        old = load_trust(db)
        if old.generation != expected_generation:
            raise ValueError("Trust generation conflict")
        from agentgate.policy import Policy

        row = db.execute("SELECT policy FROM active_controls WHERE id=1").fetchone()
        if row is None:
            raise ValueError("Active policy required before importing issuer trust")
        policy = Policy.model_validate_json(row[0])
        approved = {p.role_id for p in policy.delegation.profiles} if policy.delegation else set()
        if any(
            not set(group.roles).issubset(approved)
            for p in config.profiles
            if p.enabled
            for group in p.groups
        ):
            raise ValueError("Issuer groups must map to existing approved role profiles")
        generation = old.generation + 1
        db.execute(
            "INSERT INTO issuer_trust VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET generation=excluded.generation,config=excluded.config",
            (generation, config.model_dump_json()),
        )
        db.execute(
            "INSERT INTO issuer_events(timestamp,kind,generation) VALUES (?,'trust_imported',?)",
            (clock(), generation),
        )
        db.execute("COMMIT")
    return generation


def check_binding(
    db: sqlite3.Connection, binding: IssuerBinding, human: IssuerHumanSubject, identity: Identity
) -> None:
    trust = load_trust(db)
    profile = trust.profile(binding.issuer_profile)
    if (
        trust.generation != binding.trust_generation
        or human.issuer_profile != binding.issuer_profile
        or binding.client_claim != profile.client_claim
        or not profile.permits(binding.parent, identity, binding.client_id)
        or human.tenant_id not in {m.tenant_id for m in profile.tenants}
        or binding.deadline
        != min(
            binding.assertion_expires,
            binding.assertion_iat + profile.max_assertion_age,
            binding.assertion_auth_time + profile.max_auth_age,
        )
        or binding.expires > binding.deadline
        or binding.expires > binding.issued + profile.child_lifetime
    ):
        raise CredentialInvalid


def strict_json(raw: bytes) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JWT JSON member")
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError("Nonfinite JWT JSON number")

    result = json.loads(
        raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject_constant
    )
    pending: list[tuple[object, int]] = [(result, 1)]
    while pending:
        item, depth = pending.pop()
        if depth > 4:
            raise ValueError("JWT JSON nesting exceeds bound")
        if isinstance(item, dict):
            if len(item) > 32:
                raise ValueError("JWT claim object exceeds bound")
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list):
            if len(item) > 32:
                raise ValueError("JWT claim array exceeds bound")
            pending.extend((value, depth + 1) for value in item)
        elif isinstance(item, str) and len(item.encode("utf-8")) > 512:
            raise ValueError("JWT claim string exceeds bound")
    if not isinstance(result, dict):
        raise ValueError("JWT JSON must be an object")
    return result


def token_parts(token: str) -> tuple[dict[str, object], dict[str, object]]:
    try:
        return _token_parts(token)
    except (ValueError, UnicodeError, RecursionError, TypeError) as error:
        raise CredentialInvalid from error


def _token_parts(token: str) -> tuple[dict[str, object], dict[str, object]]:
    if len(token.encode("utf-8")) > MAX_TOKEN_BYTES or not re.fullmatch(
        r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token
    ):
        raise CredentialInvalid
    segments = token.split(".")
    header, claims = (
        strict_json(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        for part in segments[:2]
    )
    if len(header) != 3 or set(header) != {"alg", "typ", "kid"}:
        raise CredentialInvalid
    if header["alg"] != "RS256" or header["typ"] != "at+jwt":
        raise CredentialInvalid
    return header, claims
