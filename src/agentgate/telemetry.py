"""Single-owner durable, bounded audit sender. Source audit is retained on failure."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from threading import Lock
from types import TracebackType
from typing import Annotated, BinaryIO, Literal

import httpx
from pydantic import Field

from agentgate.audit_export import export_page
from agentgate.contracts import Contract
from agentgate.storage import StorageUnavailable
from agentgate.telemetry_contract import (
    MAX_ACK_BYTES,
    Acknowledgment,
    Batch,
    ProjectedEvent,
    ProtocolVersion,
    TelemetryConfig,
    batch_digest,
    decode_json,
    read_token,
)

ErrorCode = Literal["delivery_failed", "source_invalid"]


class DeliveryState(Contract):
    version: ProtocolVersion = 1
    binding: str
    cursor: Annotated[int, Field(ge=0)] = 0
    anchor: str | None = None
    pending: Batch | None = None
    pending_through: Annotated[int, Field(ge=0)] = 0
    pending_anchor: str | None = None
    failures: Annotated[int, Field(ge=0, le=31)] = 0
    next_attempt_at: float = 0.0
    last_error: ErrorCode | None = None
    acknowledged_events: Annotated[int, Field(ge=0)] = 0
    last_delivery_ms: float | None = None
    last_event_age_ms: float | None = None
    updated_at: float = 0.0


class SenderBusy(Exception):
    pass


def state_path(source: Path) -> Path:
    return source.resolve().with_suffix(".telemetry.json")


def lock_source(source: Path) -> BinaryIO:
    stream = open(
        source.resolve().with_suffix(".telemetry.lock"),
        "a+b",
        opener=lambda name, flags: os.open(name, flags, 0o600),
    )
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        raise SenderBusy from None
    return stream


def binding(source: Path, config: TelemetryConfig) -> str:
    info = source.stat()
    identity = [str(source.resolve()), info.st_dev, info.st_ino, config.origin, config.tenant]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def load_state(source: Path, config: TelemetryConfig) -> DeliveryState:
    expected = binding(source, config)
    path = state_path(source)
    if not path.exists():
        return DeliveryState(binding=expected)
    with path.open("rb") as stream:
        body = stream.read(524289)
    if len(body) > 524288:
        raise ValueError("Invalid delivery state")
    state = DeliveryState.model_validate(decode_json(body))
    if state.binding != expected:
        raise ValueError("Source or destination binding changed")
    return state


def save_state(source: Path, state: DeliveryState) -> None:
    # Replace + fsync avoids exposing a partially written batch/cursor checkpoint.
    path = state_path(source)
    # A fixed scratch slot stays bounded even after repeated SIGKILLs; the source
    # ownership lock prevents concurrent writers. Never accumulate crash orphans.
    scratch = path.with_suffix(".tmp")
    try:
        with open(scratch, "wb", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(state.model_dump_json().encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(scratch, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        scratch.unlink(missing_ok=True)


def source_position(source: Path, state: DeliveryState) -> tuple[int, str | None]:
    connection = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    try:
        connection.execute("BEGIN")
        maximum = connection.execute(
            "SELECT coalesce(max(sequence), 0) FROM audit_events"
        ).fetchone()[0]
        through = state.pending_through if state.pending else state.cursor
        anchor = state.pending_anchor if state.pending else state.anchor
        if through > maximum:
            raise ValueError("Source was truncated")
        if through:
            row = connection.execute(
                "SELECT event_id FROM audit_events WHERE sequence=?", (through,)
            ).fetchone()
            if row is None or row[0] != anchor:
                raise ValueError("Source checkpoint mismatch")
        return maximum, anchor
    finally:
        connection.close()


async def post_batch(config: TelemetryConfig, token: str, batch: Batch) -> None:
    # Total deadline covers slow trickles; HTTPX's individual I/O timeouts also apply.
    async with asyncio.timeout(config.timeout_seconds):
        async with httpx.AsyncClient(
            timeout=config.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        ) as client:
            async with client.stream(
                "POST",
                config.origin + "/v1/events",
                content=batch.model_dump_json().encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                if (
                    response.status_code != 200
                    or response.headers.get("content-type", "").split(";", 1)[0]
                    != "application/json"
                    or response.headers.get("content-encoding", "identity") != "identity"
                ):
                    raise ValueError("Delivery not acknowledged")
                body = bytearray()
                async for chunk in response.aiter_raw():
                    if len(body) + len(chunk) > MAX_ACK_BYTES:
                        raise ValueError("Acknowledgment too large")
                    body.extend(chunk)
                ack = Acknowledgment.model_validate(decode_json(bytes(body)))
                if ack.batch_id != batch.batch_id or ack.accepted_event_ids != [
                    e.event_id for e in batch.events
                ]:
                    raise ValueError("Unknown or partial acknowledgment")


class Sender:
    def __init__(
        self,
        source: Path,
        config: TelemetryConfig,
        token_file: Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.source = source.resolve()
        self.config = config
        self.token_file = token_file
        self.clock = clock
        self._lock: BinaryIO | None = None
        self._iteration = Lock()

    def __enter__(self) -> Sender:
        self._lock = lock_source(self.source)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def stage(self, state: DeliveryState) -> DeliveryState:
        if self._lock is None:
            raise RuntimeError("Sender must own the source lock")
        source_position(self.source, state)
        if state.pending:
            if len(state.pending.model_dump_json().encode()) > self.config.batch_bytes:
                raise ValueError("Pending batch exceeds configured capacity")
            return state
        limit = self.config.batch_events
        while True:
            page = export_page(
                self.source,
                tenant=self.config.tenant,
                after_sequence=state.cursor,
                limit=limit,
                require_contiguous=True,
            )
            events = [ProjectedEvent.model_validate_json(line) for line in page.lines]
            pending = Batch(batch_id=batch_digest(events), events=events) if events else None
            if (
                pending is None
                or len(pending.model_dump_json().encode()) <= self.config.batch_bytes
            ):
                break
            if limit == 1:
                raise ValueError("Projected event exceeds batch capacity")
            limit = max(1, limit // 2)
        connection = sqlite3.connect(self.source.as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            row = connection.execute(
                "SELECT event_id FROM audit_events WHERE sequence=?", (page.next_after_sequence,)
            ).fetchone()
        finally:
            connection.close()
        anchor = row[0] if row else None
        if pending:
            state = state.model_copy(
                update={
                    "pending": pending,
                    "pending_through": page.next_after_sequence,
                    "pending_anchor": anchor,
                }
            )
        else:
            # These validated rows belong exclusively to other configured scopes.
            state = state.model_copy(update={"cursor": page.next_after_sequence, "anchor": anchor})
        save_state(self.source, state)
        return state

    async def once(self) -> DeliveryState:
        if not self._iteration.acquire(blocking=False):
            raise SenderBusy
        try:
            return await self._once()
        finally:
            self._iteration.release()

    async def _once(self) -> DeliveryState:
        if self._lock is None:
            raise RuntimeError("Sender must own the source lock")
        state = load_state(self.source, self.config)
        if self.clock() < state.next_attempt_at:
            return state
        started = time.monotonic()
        phase: ErrorCode = "source_invalid"
        try:
            state = self.stage(state)
            phase = "delivery_failed"
            if state.pending:
                await post_batch(self.config, read_token(self.token_file), state.pending)
                now = self.clock()
                age = max(
                    0.0,
                    (now - datetime.fromisoformat(state.pending.events[-1].timestamp).timestamp())
                    * 1000,
                )
                state = state.model_copy(
                    update={
                        "cursor": state.pending_through,
                        "anchor": state.pending_anchor,
                        "acknowledged_events": state.acknowledged_events
                        + len(state.pending.events),
                        "last_delivery_ms": (time.monotonic() - started) * 1000,
                        "last_event_age_ms": age,
                        "pending": None,
                        "pending_through": 0,
                        "pending_anchor": None,
                    }
                )
            state = state.model_copy(
                update={
                    "failures": 0,
                    "next_attempt_at": 0.0,
                    "last_error": None,
                    "updated_at": self.clock(),
                }
            )
        except (
            OSError,
            ValueError,
            sqlite3.Error,
            StorageUnavailable,
            httpx.HTTPError,
            TimeoutError,
            RecursionError,
        ):
            failures = min(31, state.failures + 1)
            delay = min(
                self.config.retry_max_seconds,
                self.config.retry_initial_seconds * 2 ** (failures - 1),
            )
            state = state.model_copy(
                update={
                    "failures": failures,
                    "next_attempt_at": self.clock() + delay,
                    "last_error": phase,
                    "updated_at": self.clock(),
                }
            )
        save_state(self.source, state)
        return state

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            state = await self.once()
            delay = max(self.config.poll_seconds, state.next_attempt_at - self.clock())
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass


def sender_running(source: Path) -> bool:
    try:
        stream = source.resolve().with_suffix(".telemetry.lock").open("rb")
    except FileNotFoundError:
        return False
    with stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def telemetry_status(source: Path, config: TelemetryConfig) -> dict[str, object]:
    """Read-only operator hook; caller MUST enforce admin auth. No credentials needed."""
    try:
        state = load_state(source, config)
        maximum, _ = source_position(source, state)
        lag = maximum - state.cursor
        return {
            "enabled": True,
            "sender_running": sender_running(source),
            "status": "backpressure"
            if lag >= config.backlog_high_watermark
            else "retrying"
            if state.last_error
            else "pending"
            if lag
            else "idle",
            "acknowledged_through_sequence": state.cursor,
            "acknowledged_events": state.acknowledged_events,
            "source_lag_sequences": lag,
            "backpressure": lag >= config.backlog_high_watermark,
            "backlog_high_watermark": config.backlog_high_watermark,
            "pending_events": len(state.pending.events) if state.pending else 0,
            "pending_bytes": len(state.pending.model_dump_json().encode()) if state.pending else 0,
            "last_error": state.last_error,
            "consecutive_failures": state.failures,
            "next_attempt_at": state.next_attempt_at,
            "updated_at": state.updated_at,
            "last_delivery_ms": state.last_delivery_ms,
            "last_event_age_ms": state.last_event_age_ms,
        }
    except (OSError, ValueError, sqlite3.Error, RecursionError):
        return {"enabled": True, "status": "unavailable", "backpressure": True}
