"""Read-only, bounded operator exports; no remote delivery or acknowledgment."""

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import JsonValue, ValidationError

from agentgate.contracts import AuditEvent
from agentgate.storage import StorageUnavailable

ExportFormat = Literal["jsonl", "ecs", "splunk-hec"]
MAX_SEQUENCE = 2**63 - 1
MAX_EVENT_BYTES = 65536


@dataclass(frozen=True)
class ExportPage:
    lines: tuple[str, ...]
    next_after_sequence: int
    through_sequence: int
    scanned: int

    def metadata(self) -> dict[str, int | bool]:
        return {
            "next_after_sequence": self.next_after_sequence,
            "through_sequence": self.through_sequence,
            "scanned": self.scanned,
            "exported": len(self.lines),
            "has_more": self.next_after_sequence < self.through_sequence,
        }


def format_event(event: AuditEvent, sequence: int, format: ExportFormat) -> dict[str, JsonValue]:
    # A projection, not model_dump(): future audit fields must not leak by default.
    timestamp = datetime.fromtimestamp(event.timestamp, UTC).isoformat().replace("+00:00", "Z")
    record: dict[str, JsonValue] = {
        "schema_version": 1,
        "event_id": event.event_id,
        "sequence": sequence,
        "timestamp": timestamp,
        "event_type": event.event_type,
        "action_id": event.action_id,
        "trace_id": event.trace_id,
        "tenant_id": event.tenant_id,
        "principal_id": event.principal_id,
        "root_run_id": event.root_run_id,
        "operation": event.operation,
        "decision": event.decision,
        "reason_codes": [reason.value for reason in event.reason_codes],
        "policy_version": event.policy_version,
        "executed": event.executed,
        "semantic_status": event.semantic_status,
    }
    if format == "jsonl":
        return record
    if format == "splunk-hec":
        return {
            "time": event.timestamp,
            "source": "laya-sec-layer",
            "sourcetype": "laya:security",
            "event": record,
        }
    if format != "ecs":
        raise ValueError("Unsupported export format")
    # Outcome describes the requested action, not whether a guardrail worked.
    if event.event_type == "dispatch_intent":
        event_type, outcome = "start", "unknown"
    elif event.event_type == "execution_failed":
        event_type, outcome = "error", "unknown"
    elif event.decision == "require_approval":
        event_type, outcome = "info", "unknown"
    elif event.decision == "deny":
        event_type, outcome = "denied", "failure"
    else:
        event_type, outcome = "allowed", "success"
    result: dict[str, JsonValue] = {
        "@timestamp": timestamp,
        "service": {"name": "laya-sec-layer"},
        "event": {
            "kind": "event",
            "category": ["api"],
            "type": [event_type],
            "action": event.operation or "request",
            "outcome": outcome,
            "id": event.event_id,
            "sequence": sequence,
            "dataset": "laya.security",
            "reason": ",".join(event.reason_codes),
        },
        "laya": record,
    }
    if event.principal_id is not None:
        result["user"] = {"id": event.principal_id}
    return result


def export_page(
    path: Path,
    *,
    tenant: str | None,
    format: ExportFormat = "jsonl",
    after_sequence: int = 0,
    through_sequence: int | None = None,
    limit: int = 100,
    require_contiguous: bool = False,
) -> ExportPage:
    if (
        type(limit) is not int
        or not 1 <= limit <= 1000
        or type(after_sequence) is not int
        or not 0 <= after_sequence <= MAX_SEQUENCE
        or (
            through_sequence is not None
            and (type(through_sequence) is not int or not 0 <= through_sequence <= MAX_SEQUENCE)
        )
        or (tenant is not None and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}", tenant) is None)
        or format not in ("jsonl", "ecs", "splunk-hec")
    ):
        raise ValueError("Invalid export selection")
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA user_version").fetchone()[0] not in (1, 2):
            raise StorageUnavailable
        maximum = connection.execute(
            "SELECT coalesce(max(sequence), 0) FROM audit_events"
        ).fetchone()[0]
        through = maximum if through_sequence is None else through_sequence
        if not after_sequence <= through <= maximum:
            raise ValueError("Cursor does not belong to this snapshot")
        # Bound scanned rows, not just matches: an absent tenant cannot force an
        # unbounded scan. SQL avoids returning an oversized body to Python.
        rows = connection.execute(
            "SELECT sequence, event_id, CASE WHEN length(CAST(event AS BLOB)) <= ? "
            "THEN event ELSE NULL END FROM audit_events "
            "WHERE sequence > ? AND sequence <= ? ORDER BY sequence LIMIT ?",
            (MAX_EVENT_BYTES, after_sequence, through, limit),
        ).fetchall()
        if require_contiguous and (
            any(row[0] != after_sequence + index + 1 for index, row in enumerate(rows))
            or (len(rows) < limit and after_sequence + len(rows) != through)
        ):
            raise StorageUnavailable
        lines = []
        for sequence, event_id, body in rows:
            if body is None:
                raise StorageUnavailable
            event = AuditEvent.model_validate_json(body)
            if event.event_id != event_id:
                raise StorageUnavailable
            if event.tenant_id == tenant:
                lines.append(json.dumps(format_event(event, sequence, format), allow_nan=False))
        next_sequence = rows[-1][0] if len(rows) == limit else through
        return ExportPage(tuple(lines), next_sequence, through, len(rows))
    except (sqlite3.Error, ValidationError, OverflowError, OSError) as error:
        raise StorageUnavailable from error
    finally:
        if connection is not None:
            connection.close()
