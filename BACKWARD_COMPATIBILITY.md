# Contract status

AgentGate is unreleased. Its first implemented contracts are documented in
`docs/document-slice.md`: REST action execution and health endpoints, strict
document arguments, the partial policy schema, minimized audit events, local CLI,
and SQLite schema version 2. Other architecture examples remain proposals.
`agentgate migrate` upgrades schema 1 additively, preserving credentials and audit.
See `docs/budgets.md` for backup/rollback limits. Old code cannot use schema 2.
The optional `tool_budgets` policy block preserves old defaults when omitted;
the shipped demo opts in with policy revision 2. HTTP 429/BUDGET_EXCEEDED is an
additive denial reason. Existing response and audit field shapes are unchanged.

Semantic worker routes now expose the `content-role-v1` contract. Optional
`semantic_mode` defaults to enforce. `semantic_required` requires a configured,
ready worker; the default demo still disables it. Audit events add nullable
`semantic` evidence and new status values while existing rows remain readable.
No database migration is needed for the additive serialized audit field.

`audit-export` is an additive local operator command. It reads schema-1 and
schema-2 audit rows, uses a version-1 allowlisted export record and retains the
existing `audit` command unchanged. ECS-oriented and HEC-envelope formats share
that projection. Cursor metadata is emitted on stderr; it records local scan
progress, not downstream delivery. See `docs/audit-export.md` for scope and
snapshot semantics. No public HTTP endpoint or storage migration is added.

The current operational contracts are `make setup`, `make validate`, `make doctor`,
`make harness`, Python lint/type/test/build commands, local demo commands, and the
upstream configuration formats under `.ai/`. Keep their
documentation and callers consistent when changing them. Preserve the original
architecture document and record consequential design changes explicitly.

When implementing additional runtime surfaces, add their status here and establish contract
tests for HTTP/MCP schemas, canonical operation aliases, semantic-worker messages,
policy versions, approval payload binding, budget units, audit events, and SDK calls.
For a used contract, incompatible changes require a consumer update, migration or
versioning plan as appropriate, and tests. Never silently change identity,
authorization, or accounting semantics to preserve apparent compatibility.
