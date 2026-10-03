"""Version-1 local contract lab protocol, not a vendor ingestion protocol."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from agentgate.app import reject_constant, unique_object
from agentgate.contracts import Contract, Identifier

MAX_BATCH_BYTES = 262144
MAX_ACK_BYTES = 32768
MAX_EVENTS = 100
Text = Annotated[str, Field(min_length=1, max_length=128)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ProtocolVersion = Annotated[int, Field(ge=1, le=1)]


def decode_json(body: bytes) -> object:
    return json.loads(body, object_pairs_hook=unique_object, parse_constant=reject_constant)


class TelemetryConfig(Contract):
    origin: Annotated[str, Field(max_length=256)]
    tenant: Identifier | None  # Required: explicit null selects unattributed events.
    batch_events: Annotated[int, Field(ge=1, le=MAX_EVENTS)] = 100
    batch_bytes: Annotated[int, Field(ge=4096, le=MAX_BATCH_BYTES)] = MAX_BATCH_BYTES
    timeout_seconds: Annotated[float, Field(ge=0.05, le=30)] = 5.0
    retry_initial_seconds: Annotated[float, Field(ge=0.05, le=60)] = 1.0
    retry_max_seconds: Annotated[float, Field(ge=0.05, le=3600)] = 60.0
    poll_seconds: Annotated[float, Field(ge=0.05, le=60)] = 1.0
    backlog_high_watermark: Annotated[int, Field(ge=1, le=1000000)] = 10000

    @field_validator("origin")
    @classmethod
    def fixed_origin(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.path
            or url.query
            or url.fragment
            or not re.fullmatch(r"https?://[a-zA-Z0-9.-]+(?::[0-9]{1,5})?", value)
            or (url.port is not None and not 1 <= url.port <= 65535)
            or (url.scheme == "http" and url.hostname != "127.0.0.1")
        ):
            raise ValueError("Expected HTTPS origin or literal loopback HTTP origin")
        return value

    @model_validator(mode="after")
    def retry_order(self) -> TelemetryConfig:
        if self.retry_max_seconds < self.retry_initial_seconds:
            raise ValueError("Retry maximum must cover initial delay")
        return self


class ProjectedEvent(Contract):
    schema_version: ProtocolVersion
    event_id: Text
    sequence: Annotated[int, Field(ge=1, le=2**63 - 1)]
    timestamp: Annotated[str, Field(min_length=20, max_length=40)]
    event_type: Text
    action_id: Text
    trace_id: Text
    tenant_id: Identifier | None
    principal_id: Text | None
    root_run_id: Text | None
    operation: Text | None
    decision: Literal["allow", "redact", "deny", "require_approval"]
    reason_codes: Annotated[list[Text], Field(max_length=32)]
    policy_version: Text
    executed: bool
    semantic_status: Text

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        if not value.endswith("Z") or datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError("Expected UTC timestamp")
        return value


class Batch(Contract):
    version: ProtocolVersion = 1
    batch_id: Digest
    events: Annotated[list[ProjectedEvent], Field(min_length=1, max_length=MAX_EVENTS)]

    @model_validator(mode="after")
    def integrity(self) -> Batch:
        ids = [event.event_id for event in self.events]
        sequences = [event.sequence for event in self.events]
        if (
            len(set(ids)) != len(ids)
            or sequences != sorted(set(sequences))
            or self.batch_id != batch_digest(self.events)
        ):
            raise ValueError("Invalid batch identity or order")
        return self


def batch_digest(events: list[ProjectedEvent]) -> str:
    body = json.dumps(
        [e.model_dump(mode="json") for e in events], sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(body.encode()).hexdigest()


class Acknowledgment(Contract):
    version: ProtocolVersion
    batch_id: Digest
    accepted_event_ids: Annotated[list[Text], Field(min_length=1, max_length=MAX_EVENTS)]


def read_config(path: Path) -> TelemetryConfig:
    with path.open("rb") as stream:
        body = stream.read(16385)
    if len(body) > 16384:
        raise ValueError("Config too large")
    return TelemetryConfig.model_validate(decode_json(body))


def read_token(path: Path) -> str:
    # Read from an operator-owned private file, never from config, argv or audit.
    with path.open("rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 257
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ValueError("Collector credential must be private")
        value = stream.read(257).strip()
    if re.fullmatch(rb"[a-zA-Z0-9_-]{32,256}", value) is None:
        raise ValueError("Invalid collector credential")
    return value.decode("ascii")
