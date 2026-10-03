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

E01-S01 adds the separately authenticated `/admin/*` contract documented in
`docs/control-plane-contract.md`. `attach_admin_routes` is reusable; `create_app`
accepts optional keyword `admin_origin`. `agentgate init-operator` bootstraps a
private, non-overwritable operator credential; `serve --admin-origin` configures the
exact browser origin (default loopback). Sessions and agent credentials are separate.

Live controls add `active_controls`, `control_events`, `operator_credentials`, and
`operator_sessions` tables without changing schema-2 document/budget tables. First
admin attachment seeds policy from the supplied configuration; later starts retain
the last activated policy/feed. After initialization, edit through validation and
CAS activation rather than changing the startup policy file. Keep the gateway
stopped while backing up/restoring authoritative state. Old binaries can still
read schema-2 audit/export, but must not serve after live controls have been enabled:
they do not enforce durable snapshots. Rollback requires stopping serving and
explicitly restoring a reviewed static policy; never silently revert permissions.

AuditEvent adds nullable `feed_version`; old records remain readable. Document
responses retain their shape and add denial reasons `THREAT_FEED_BLOCKED` and
`CONTROLS_CHANGED` (409 if repeated activations prevent a stable dispatch). Export
schema 1 remains unchanged and does not include the new feed field. Admin timeline
adds feed evidence separately. No remote delivery, model inference, or new tools
are implied by these contracts.

Production semantic workers now require a private, persistent per-installation
call ledger (`semantic-quota.sqlite3`). The default is 1000 admissions per UTC day,
configurable with `semantic-worker --daily-calls`; retain the ledger during restart.
Worker exhaustion adds HTTP429 and gateway reason `SEMANTIC_BUDGET_EXCEEDED`.
The optional internal Supervisor quota parameter preserves fixture/evaluation
construction; the shipped production command always configures it. Operator
overview adds measured `budgets.semantic` or an explicit unavailable status.
See `docs/semantic-call-quota.md` for conservative accounting and cap changes.

E04-S01 adds the offline `scripts/semantic_evaluate.py run|compare` CLI and
version-1 frozen corpus/protocol/minimized report described in
`docs/semantic-evaluation.md`. It imports the unchanged content-role-v1 engine.
No production endpoint, question, policy, auth or storage contract changes.
New evaluation versions must preserve earlier labels/provenance; generated
reports are ignored and output files are never overwritten.
