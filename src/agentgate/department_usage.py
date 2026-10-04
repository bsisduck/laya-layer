"""Versioned per-attempt evidence and bounded, snapshot-coherent operator reports.

No budget-account sums, identity issuance, inferred usage, or retrospective attribution.
"""

import sqlite3
from typing import Annotated

from pydantic import ConfigDict, Field

from agentgate.contracts import Contract, Identifier
from agentgate.storage import StorageUnavailable, Store

MAX_PERIOD = 31 * 86400
MAX_ATTEMPTS = 10000
MAX_DEPARTMENTS = 64
MAX_PROVENANCE = 16
SCHEMA = """
CREATE TABLE IF NOT EXISTS model_usage_schema (version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO model_usage_schema VALUES(1);
CREATE TABLE IF NOT EXISTS model_attribution (
    action_id TEXT PRIMARY KEY REFERENCES model_attempts(action_id),
    version INTEGER NOT NULL CHECK(version=1),
    accounting_principal TEXT NOT NULL,
    attribution TEXT
);
CREATE TABLE IF NOT EXISTS model_settlement (
    action_id TEXT PRIMARY KEY REFERENCES model_attempts(action_id),
    version INTEGER NOT NULL CHECK(version=1),
    input_tokens INTEGER NOT NULL CHECK(input_tokens>=0),
    output_tokens INTEGER NOT NULL CHECK(output_tokens>=0),
    simulated_micro_usd TEXT NOT NULL CHECK(length(simulated_micro_usd) BETWEEN 1 AND 32 AND simulated_micro_usd NOT GLOB '*[^0-9]*'),
    over_bound INTEGER NOT NULL CHECK(over_bound IN (0,1))
);
"""


class TrustedAttribution(Contract):
    """Allowlisted consumer of authority-owned data, including newer issuers.

    Extra authority fields (bindings, roles, raw issuer claims) are never retained.
    This accepts evidence only; it cannot resolve or grant authority.
    """

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True, allow_inf_nan=False)
    version: Annotated[int, Field(ge=1, le=2147483647)]
    human_subject: Identifier
    department: Identifier
    provenance: Identifier
    subject_revision: Annotated[int, Field(ge=1, le=2147483647)]
    issuer_id: Identifier | None = None
    trust_version: Annotated[int, Field(ge=1, le=2147483647)] | None = None


def migrate(db: sqlite3.Connection) -> None:
    for statement in SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)
    if [r[0] for r in db.execute("SELECT version FROM model_usage_schema")] != [1]:
        raise StorageUnavailable


def capture(db: sqlite3.Connection, action_id: str, owner: str, authority: object) -> None:
    value = (
        None
        if authority is None
        else TrustedAttribution.model_validate(authority).model_dump_json(exclude_none=True)
    )
    db.execute("INSERT INTO model_attribution VALUES (?,1,?,?)", (action_id, owner, value))


def empty_totals() -> dict[str, int]:
    return dict.fromkeys(
        (
            "attempts",
            "dispatch_intent",
            "uncertain",
            "settled",
            "attributed",
            "unassigned",
            "historical_attribution_unavailable",
            "known_usage_attempts",
            "unknown_usage_attempts",
            "historical_usage_unavailable",
            "known_input_tokens",
            "known_output_tokens",
            "known_simulated_micro_usd",
            "outstanding_calls",
            "outstanding_input_tokens",
            "outstanding_output_tokens",
            "outstanding_simulated_micro_usd",
            "over_bound_attempts",
            "zero_tariff_attempts",
        ),
        0,
    )


def wire_totals(totals: dict[str, int]) -> dict[str, int | str]:
    # Money can exceed int64 / Number's exact range. Never hand it to JSON as Number.
    return {k: str(v) if "micro_usd" in k else v for k, v in totals.items()}


def report(
    store: Store, tenant: str, start: int, end: int, departments: int = MAX_DEPARTMENTS
) -> dict[str, object]:
    if not 0 <= start < end <= 4102444800 or end - start > MAX_PERIOD:
        raise ValueError("Select a UTC period of at most 31 days")
    if not 1 <= departments <= MAX_DEPARTMENTS:
        raise ValueError("Select at most 64 department buckets")
    # Validate exact tenant identifiers even for non-HTTP trusted consumers.
    from pydantic import TypeAdapter

    TypeAdapter(Identifier).validate_python(tenant)
    with store.connection() as db:
        db.execute("BEGIN")
        if [r[0] for r in db.execute("SELECT version FROM model_usage_schema")] != [1]:
            raise StorageUnavailable
        rows = db.execute(
            "SELECT a.*, p.action_id AS attribution_id,p.attribution,"
            "s.input_tokens,s.output_tokens,s.simulated_micro_usd,s.over_bound "
            "FROM model_attempts a INDEXED BY model_attempt_period "
            "LEFT JOIN model_attribution p ON p.action_id=a.action_id "
            "LEFT JOIN model_settlement s ON s.action_id=a.action_id "
            "WHERE a.tenant_id=? AND a.created_at>=? AND a.created_at<? "
            "ORDER BY a.created_at,a.action_id LIMIT ?",
            (tenant, start, end, MAX_ATTEMPTS + 1),
        ).fetchall()
        db.execute("COMMIT")
    truncated_attempts = len(rows) > MAX_ATTEMPTS
    totals = empty_totals()
    buckets: dict[str | None, dict[str, int]] = {}
    provenance: dict[str | None, set[tuple[str, int, str | None, int | None]]] = {}
    for row in rows[:MAX_ATTEMPTS]:
        attr = (
            TrustedAttribution.model_validate_json(row["attribution"])
            if row["attribution"]
            else None
        )
        department = attr.department if attr else None
        bucket = buckets.setdefault(department, empty_totals())
        sources = provenance.setdefault(department, set())
        if attr:
            sources.add((attr.provenance, attr.version, attr.issuer_id, attr.trust_version))
        for item in (totals, bucket):
            item["attempts"] += 1
            item[
                {"dispatched": "dispatch_intent", "uncertain": "uncertain", "settled": "settled"}[
                    row["state"]
                ]
            ] += 1
            item[
                "attributed"
                if attr
                else "unassigned"
                if row["attribution_id"]
                else "historical_attribution_unavailable"
            ] += 1
            item["zero_tariff_attempts"] += int(row["input_tariff"] == row["output_tariff"] == 0)
            if row["input_tokens"] is not None:
                item["known_usage_attempts"] += 1
                item["known_input_tokens"] += row["input_tokens"]
                item["known_output_tokens"] += row["output_tokens"]
                item["known_simulated_micro_usd"] += int(row["simulated_micro_usd"])
                item["over_bound_attempts"] += row["over_bound"]
            else:
                item["unknown_usage_attempts"] += 1
                item["historical_usage_unavailable"] += int(row["state"] == "settled")
            if row["state"] != "settled":
                item["outstanding_calls"] += 1
                item["outstanding_input_tokens"] += row["input_bound"]
                item["outstanding_output_tokens"] += row["output_bound"]
                item["outstanding_simulated_micro_usd"] += (
                    row["input_bound"] * row["input_tariff"]
                    + row["output_bound"] * row["output_tariff"]
                )
    # Keep the unknown/unassigned bucket even when named departments are truncated.
    keys = ([None] if None in buckets else []) + sorted(k for k in buckets if k is not None)
    truncated_departments = len(keys) > departments
    truncated_provenance = any(len(v) > MAX_PROVENANCE for v in provenance.values())
    records = [
        {
            "department": key,
            "bucket": "department" if key is not None else "unknown_unassigned",
            "totals": wire_totals(buckets[key]),
            "provenance": [
                {"source": p, "authority_version": v, "issuer_id": i, "trust_version": t}
                for p, v, i, t in sorted(
                    provenance[key], key=lambda x: (x[0], x[1], x[2] or "", x[3] or 0)
                )[:MAX_PROVENANCE]
            ],
            "provenance_truncated": len(provenance[key]) > MAX_PROVENANCE,
        }
        for key in keys[:departments]
    ]
    return {
        "version": 1,
        "source": "model-attempt-evidence-v1",
        "tenant_id": tenant,
        "window": {
            "start": start,
            "end": end,
            "basis": "reservation_time_utc",
            "interval": "[start,end)",
        },
        "completeness": {
            "status": "truncated"
            if truncated_attempts or truncated_departments or truncated_provenance
            else "partial_evidence"
            if totals["unknown_usage_attempts"] or totals["historical_attribution_unavailable"]
            else "complete",
            "attempts_truncated": truncated_attempts,
            "departments_truncated": truncated_departments,
            "provenance_truncated": truncated_provenance,
            "attempt_limit": MAX_ATTEMPTS,
            "department_limit": departments,
            "totals_basis": "selected_attempts",
            "returned_department_attempts": sum(buckets[k]["attempts"] for k in keys[:departments]),
        },
        "totals": wire_totals(totals),
        "departments": records,
        "units": {
            "tokens": "provider_reported_actual",
            "money": "simulated_micro_usd",
            "dispatch_intent": "durable intent; provider receipt unconfirmed",
        },
        "gaps": [
            "Remote department export is unavailable; export-v1 is unchanged.",
            "Tool operation charges and semantic installation consumption are separate ledgers.",
            "Zero simulated tariff does not mean free enterprise AI or zero compute cost.",
        ],
    }
