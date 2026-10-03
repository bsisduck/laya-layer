"""Durable control snapshots and bounded, data-only threat inspection.

No feed value is a regular expression, import path, command, or download target.
"""

import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, model_validator

from agentgate.contracts import Contract, Identifier
from agentgate.policy import Policy
from agentgate.storage import StorageUnavailable, Store

Stage = Literal["model_input", "tool_action", "tool_result", "model_output", "artifact_intake"]
STAGES: tuple[Stage, ...] = (
    "model_input",
    "tool_action",
    "tool_result",
    "model_output",
    "artifact_intake",
)
MAX_CONTROL_BYTES = 65536
MAX_INSPECTION_BYTES = 262144
DOMAIN_TOKEN = re.compile(r"(?<![\w-])(?:[\w-]+\.)+[\w-]+\.?", re.UNICODE)
URL_TOKEN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
DIGEST_TOKEN = re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])")


def canonical_domain(value: str) -> str:
    value = value.rstrip(".").encode("idna").decode("ascii").lower()
    if len(value) > 253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in value.split(".")
    ):
        raise ValueError("Invalid domain")
    return value


def canonical_source(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(c.isspace() or ord(c) < 32 for c in value)
        or "\\" in value
        or "%" in value
    ):
        raise ValueError("Source must be an absolute HTTP(S) URL without credentials or query")
    host = canonical_domain(parsed.hostname)
    port = parsed.port
    authority = (
        host if port in (None, 443 if parsed.scheme == "https" else 80) else f"{host}:{port}"
    )
    return urlunsplit((parsed.scheme, authority, parsed.path or "/", "", ""))


class Indicator(Contract):
    id: Identifier
    kind: Literal["literal_text", "blocked_domain", "blocked_sha256", "blocked_source"]
    value: Annotated[str, Field(min_length=1, max_length=512)]
    stages: Annotated[tuple[Stage, ...], Field(min_length=1, max_length=5)] = STAGES

    @model_validator(mode="after")
    def validate_matcher(self) -> "Indicator":
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("Duplicate stage")
        if self.kind == "blocked_domain" and canonical_domain(self.value) != self.value:
            raise ValueError("Domain must be canonical lowercase ASCII without a trailing dot")
        if self.kind == "blocked_sha256" and not re.fullmatch(r"[a-f0-9]{64}", self.value):
            raise ValueError("Digest must be lowercase SHA-256")
        if self.kind == "blocked_source" and canonical_source(self.value) != self.value:
            raise ValueError("Source must be canonical")
        if self.kind == "literal_text" and not self.value.strip():
            raise ValueError("Empty literal")
        return self


class ThreatFeed(Contract):
    schema_version: Literal[1] = 1
    feed_id: Identifier = "local"
    revision: Annotated[int, Field(ge=1, le=2147483647)] = 1
    indicators: Annotated[tuple[Indicator, ...], Field(max_length=128)] = ()

    @model_validator(mode="after")
    def unique_indicators(self) -> "ThreatFeed":
        if len({indicator.id for indicator in self.indicators}) != len(self.indicators):
            raise ValueError("Duplicate indicator ID")
        if len(self.model_dump_json().encode()) > MAX_CONTROL_BYTES:
            raise ValueError("Feed exceeds 64 KiB")
        return self

    @property
    def version(self) -> str:
        return f"{self.feed_id}:{self.revision}"


class ArtifactMetadata(Contract):
    """Metadata only: passing this object never opens or deserializes an artifact."""

    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    source: Annotated[str, Field(max_length=512)]
    serialization: Literal["safetensors", "json", "pickle", "joblib", "torch_pickle"]

    @model_validator(mode="after")
    def valid_source(self) -> "ArtifactMetadata":
        canonical_source(self.source)
        return self


class ThreatBlocked(Exception):
    """Only bounded indicator IDs, never matched content, leave the inspector."""

    def __init__(self, indicator_ids: tuple[str, ...]) -> None:
        self.indicator_ids = indicator_ids
        super().__init__("Threat feed denied content")


@dataclass(frozen=True)
class ControlSnapshot:
    policy: Policy
    feed: ThreatFeed
    generation: int = 0

    def assert_current(self, connection: sqlite3.Connection) -> None:
        ControlPlane.assert_current(connection, self)

    def inspect(
        self, stage: Stage, text: str, *, artifacts: tuple[ArtifactMetadata, ...] = ()
    ) -> None:
        """Mandatory pre-dispatch / pre-release callback; raises on match or invalid input."""
        if stage not in STAGES or len(artifacts) > 16:
            raise ValueError("Invalid inspection request")
        if len(text.encode("utf-8")) > MAX_INSPECTION_BYTES:
            raise ValueError("Inspection input exceeds limit")
        hits: list[str] = []
        domains: set[str] = set()
        sources: set[str] = set()
        digests = {value.lower() for value in DIGEST_TOKEN.findall(text)}
        for token in DOMAIN_TOKEN.findall(text):
            try:
                domains.add(canonical_domain(token))
            except (ValueError, UnicodeError):
                continue
        for token in URL_TOKEN.findall(text):
            try:
                sources.add(canonical_source(token.rstrip(".,);]}")))
            except (ValueError, UnicodeError):
                continue
        for artifact in artifacts:
            # Revalidate even model_copy/model_construct values at this boundary.
            artifact = ArtifactMetadata.model_validate_json(artifact.model_dump_json())
            source = canonical_source(artifact.source)
            sources.add(source)
            domains.add(canonical_domain(urlsplit(source).hostname or ""))
            digests.add(artifact.sha256)
            if artifact.serialization in ("pickle", "joblib", "torch_pickle"):
                hits.append("unsafe-serialization")
        for indicator in self.feed.indicators:
            if stage not in indicator.stages:
                continue
            if (
                (indicator.kind == "literal_text" and indicator.value in text)
                or (indicator.kind == "blocked_sha256" and indicator.value in digests)
                or (indicator.kind == "blocked_source" and indicator.value in sources)
                or (
                    indicator.kind == "blocked_domain"
                    and any(
                        domain == indicator.value or domain.endswith("." + indicator.value)
                        for domain in domains
                    )
                )
            ):
                hits.append(indicator.id)
        if hits:
            raise ThreatBlocked(tuple(dict.fromkeys(hits)))


class ControlsChanged(Exception):
    pass


class ControlConflict(Exception):
    pass


class ControlPlane:
    def __init__(self, store: Store, clock: Callable[[], float] = time.time) -> None:
        self.store = store
        self.clock = clock

    def initialize(self, policy: Policy) -> None:
        policy = self.validate_policy(policy)
        with self.store.connection() as connection:
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS active_controls (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    generation INTEGER NOT NULL,
                    policy TEXT NOT NULL,
                    feed TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS control_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    kind TEXT NOT NULL,
                    version TEXT NOT NULL,
                    generation INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operator_credentials (
                    id INTEGER PRIMARY KEY CHECK(id = 1), digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operator_sessions (
                    digest TEXT PRIMARY KEY, operator_digest TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operator_session_expiry ON operator_sessions(expires_at);
            """)
            connection.execute(
                "INSERT OR IGNORE INTO active_controls VALUES (1, 1, ?, ?)",
                (policy.model_dump_json(), ThreatFeed().model_dump_json()),
            )
            connection.execute("COMMIT")
        self.snapshot()  # Existing invalid state fails closed; never silently replace it.

    @staticmethod
    def validate_policy(policy: Policy) -> Policy:
        encoded = policy.model_dump_json()
        if len(encoded.encode()) > MAX_CONTROL_BYTES:
            raise ValueError("Policy exceeds 64 KiB")
        return Policy.model_validate_json(encoded)

    def snapshot(self) -> ControlSnapshot:
        with self.store.connection() as connection:
            row = connection.execute("SELECT * FROM active_controls WHERE id=1").fetchone()
            if row is None:
                raise StorageUnavailable
            return ControlSnapshot(
                Policy.model_validate_json(row["policy"]),
                ThreatFeed.model_validate_json(row["feed"]),
                row["generation"],
            )

    @staticmethod
    def assert_current(connection: sqlite3.Connection, snapshot: ControlSnapshot) -> None:
        row = connection.execute("SELECT generation FROM active_controls WHERE id=1").fetchone()
        if row is None:
            raise StorageUnavailable
        if row[0] != snapshot.generation:
            raise ControlsChanged

    def activate_policy(self, policy: Policy, expected_version: str) -> ControlSnapshot:
        return self._activate(self.validate_policy(policy), expected_version)

    def activate_feed(self, feed: ThreatFeed, expected_version: str) -> ControlSnapshot:
        return self._activate(
            ThreatFeed.model_validate_json(feed.model_dump_json()), expected_version
        )

    def _activate(self, value: Policy | ThreatFeed, expected: str) -> ControlSnapshot:
        policy_update = isinstance(value, Policy)
        with self.store.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM active_controls WHERE id=1").fetchone()
            if row is None:
                raise StorageUnavailable
            policy = Policy.model_validate_json(row["policy"])
            feed = ThreatFeed.model_validate_json(row["feed"])
            current = policy if policy_update else feed
            if current.version != expected or value.revision <= current.revision:
                raise ControlConflict
            if isinstance(value, Policy):
                if value.policy_id != policy.policy_id:
                    raise ControlConflict
                policy = value
            else:
                if value.feed_id != feed.feed_id:
                    raise ControlConflict
                feed = value
            generation = row["generation"] + 1
            connection.execute(
                "UPDATE active_controls SET policy=?, feed=?, generation=? WHERE id=1",
                (policy.model_dump_json(), feed.model_dump_json(), generation),
            )
            connection.execute(
                "INSERT INTO control_events(timestamp, kind, version, generation) VALUES (?, ?, ?, ?)",
                (
                    self.clock(),
                    "policy_activated" if policy_update else "feed_activated",
                    value.version,
                    generation,
                ),
            )
            connection.execute("COMMIT")
        return ControlSnapshot(policy, feed, generation)

    def events(self, limit: int = 100) -> list[dict[str, object]]:
        if not 1 <= limit <= 1000:
            raise ValueError("Invalid limit")
        with self.store.connection() as connection:
            rows = connection.execute(
                "SELECT sequence, timestamp, kind, version, generation FROM control_events "
                "ORDER BY sequence DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
