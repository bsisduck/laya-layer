"""Strict scoped-tool inputs, approved registry, and additive policy defaults."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, field_validator

from agentgate.contracts import Contract, DocumentArguments, Identifier


class MemoryArguments(Contract):
    query: Annotated[str, Field(min_length=1, max_length=512)]
    limit: Annotated[int, Field(ge=1, le=10)] = 10


class MailArguments(Contract):
    recipient: Annotated[
        str,
        Field(
            max_length=254,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$",
        ),
    ]
    subject: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[^\r\n\x00]*$")]
    body: Annotated[str, Field(min_length=1, max_length=8192)]
    idempotency_key: Identifier

    @field_validator("recipient", "subject", "body")
    @classmethod
    def valid_text(cls, value: str) -> str:
        try:
            value.encode("utf-8")
        except UnicodeError as error:
            raise ValueError("Invalid UTF-8 text") from error
        if "\x00" in value:
            raise ValueError("NUL is not mail text")
        return value


class ScopedToolPolicy(Contract):
    memory_roles: tuple[Identifier, ...] = ("analyst",)
    memory_classifications: tuple[Literal["public", "internal", "confidential"], ...] = (
        "public",
        "internal",
    )
    mail_roles: tuple[Identifier, ...] = ("analyst",)
    mail_domains: tuple[Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")], ...] = (
        "demo.internal",
    )
    approval_ttl_seconds: Annotated[int, Field(ge=1, le=3600)] = 300


# Exact aliases only. Neither prefixes nor client annotations confer authority.
ALIASES = {
    "documents.read": "documents.read",
    "documents_read": "documents.read",
    "memory.query": "memory.query",
    "memory_query": "memory.query",
    "mail.send": "mail.send",
    "mail_send": "mail.send",
}
INPUTS: dict[str, type[Contract]] = {
    "documents.read": DocumentArguments,
    "memory.query": MemoryArguments,
    "mail.send": MailArguments,
}
REGISTRY_DIGEST = hashlib.sha256(
    json.dumps(
        {
            "version": "scoped-tools-v1-local-outbox",
            "aliases": ALIASES,
            "schemas": {key: value.model_json_schema() for key, value in INPUTS.items()},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()

SCHEMA = """
CREATE TABLE IF NOT EXISTS scoped_tool_schema (version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO scoped_tool_schema VALUES (1);
CREATE TABLE IF NOT EXISTS memory_entries (
    tenant_id TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    classification TEXT NOT NULL CHECK(classification IN ('public','internal','confidential','secret')),
    content TEXT NOT NULL CHECK(length(content)<=8192),
    PRIMARY KEY(tenant_id, entry_id)
);
CREATE TABLE IF NOT EXISTS tool_actions (
    action_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    root_run_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    identity TEXT NOT NULL,
    credential_digest TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    policy_digest TEXT NOT NULL,
    registry_digest TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','approved','denied','expired','consumed')),
    reason TEXT NOT NULL,
    decided_by TEXT,
    UNIQUE(tenant_id, principal_id, root_run_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS tool_action_tenant ON tool_actions(tenant_id, created_at);
CREATE TRIGGER IF NOT EXISTS tool_action_immutable BEFORE UPDATE OF
    tenant_id, principal_id, root_run_id, idempotency_key, identity, credential_digest,
    payload, payload_digest, policy_digest, registry_digest, fingerprint,
    policy_version, expires_at, created_at ON tool_actions
BEGIN SELECT RAISE(ABORT, 'Immutable approved action'); END;
CREATE TABLE IF NOT EXISTS tool_outbox (
    action_id TEXT PRIMARY KEY REFERENCES tool_actions(action_id),
    tenant_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL,
    delivery_state TEXT NOT NULL DEFAULT 'fixture' CHECK(delivery_state='fixture')
);
CREATE INDEX IF NOT EXISTS tool_outbox_tenant ON tool_outbox(tenant_id, created_at);
"""
