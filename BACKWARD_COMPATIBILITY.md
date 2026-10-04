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

`agentgate-telemetry` adds local send/status/collector commands and the operator-only
`telemetry_status(source, config)` hook. Existing CLI/routes/config and audit
schemas are unchanged; `export_page(require_contiguous=False)` preserves default
file export behavior while the sender explicitly requires contiguous scans. A
private version-1 sidecar stores one bounded batch/cursor/retry state; the separate
contract collector owns its own version-1 receipt/scope database. No gateway
migration is required. Preserve source and sidecars together on normal restarts;
source relocation/replacement or tenant/destination changes require deliberate
operator reconciliation. See `docs/telemetry-delivery.md` for wire contracts,
restart/rollback limits and additive root integration for newer audit variants.

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

Scoped tools add optional `scoped_tools` policy defaults, memory/mail audit operation
and event variants, `require_approval`, and optional approval/state/expiry fields
on ActionResponse. Results can include structured memory rows; existing document
result fields are preserved. Exact underscored aliases are newly supported.
`docs/scoped-tools.md` specifies REST/MCP, trusted operator hooks and migration.
Schema 2 gains scoped-tool tables with their own version marker. Readiness requires
the additive migration and tenant+root accounting layout; old binaries must remain
stopped. Existing credentials keep their old scopes; only newly initialized demo
credentials include memory/mail. `make setup`/`make validate` install/use the locked
MCP extra for typechecking and wire tests; base package runtime remains optional.
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

The additive root `./laya` CLI manages a separately owned installation. Its
version-1 `installation.json` lives outside the checkout; unknown versions,
unsafe paths and unowned legacy state are refused. Existing `agentgate` and Make
commands are retained. Reinstallation preserves credentials/audit/budgets and
backs up the gateway database before running its additive migration; optional
worker quota state is retained. See [local lifecycle](docs/local-app.md) for
ports, exit status, expiry, update and rollback contracts.

Production semantic workers now require a private, persistent per-installation
call ledger (`semantic-quota.sqlite3`). The default is 1000 admissions per UTC day,
configurable with `semantic-worker --daily-calls`; retain the ledger during restart.
Worker exhaustion adds HTTP429 and gateway reason `SEMANTIC_BUDGET_EXCEEDED`.
The optional internal Supervisor quota parameter preserves fixture/evaluation
construction; the shipped production command always configures it. Operator
overview adds measured `budgets.semantic` or an explicit unavailable status.
See `docs/semantic-call-quota.md` for conservative accounting and cap changes.

Explicit operator credential renewal adds `operator_credential_epochs` and
`credential_renewals` without changing schema-2 credentials, budgets, approvals or
audit/export. Epoch zero retains the original tool/model playground HMAC tokens.
Only an explicit trusted operator action may replace expired non-revoked rows;
old rows remain revoked, identities/root spend are unchanged, and existing
approvals cannot transfer to the new token. New admin routes and trusted installer
hooks are documented in `docs/credential-renewal-contract.md`. Older binaries do
not understand renewed epochs; stop serving before rollback and preserve all
credential/epoch/history/budget tables. Do not reset state to recover expiry.

E04-S01 adds the offline `scripts/semantic_evaluate.py run|compare` CLI and
version-1 frozen corpus/protocol/minimized report described in
`docs/semantic-evaluation.md`. It imports the unchanged content-role-v1 engine.
No production endpoint, question, policy, auth or storage contract changes.
New evaluation versions must preserve earlier labels/provenance; generated
reports are ignored and output files are never overwritten.

Terminal audit events now prioritize the failing semantic stage. If output
classification fails after successful input classification, the terminal event
reports unavailable/invalid output and no stale semantic result; the input result
remains on dispatch_intent. Enforcement and settled usage are unchanged.

The additive `agentgate-artifacts` local operator CLI accepts bounded JSON metadata,
an exact approved registry and an active or supplied threat feed. Exit 0 means
metadata accepted, 2 means policy denial, and 1 means invalid input. JSON output
explicitly reports simulation and unverified/unexecuted artifact bytes. It adds no
agent tool authority or download path; see [artifact intake](docs/artifact-intake.md).

`content-role-v2` is an explicit optional two-choice question profile. All existing
production constructor/CLI and omitted request/capability versions default to v1.
New flags: `semantic-worker --question-set` and `serve --semantic-question-set`;
both sides must select the same version. V2 results have exactly two actual mapped
scores, `task_data` and `behavior_instruction`; v1 retains its three scores and
`unclear` abstention. Consumers must use the version to interpret score shape and
label meaning. Worker/client handshake and result mismatches fail closed, with no
new permissions, threshold, fallback or storage migration. See
`docs/semantic-question-v2.md`. Evaluation CLI adds `--version v1|v2`; historical
v1 reproduction requires the pinned PR23 checkout below, not a rewritten freeze.

The installed lifecycle adds a private local telemetry collector (default port
8095) and gateway-owned durable sender. Existing version-1 installation metadata
receives a non-colliding collector port and v1 question-set default during
configuration. `./laya install --question-set content-role-v2` explicitly binds
both semantic endpoints; switching the profile versions the live policy without
resetting credentials or usage. `--collector-port` is remembered alongside other
ports. The dashboard adds bounded process-local response timings and actual
local-lab delivery state; neither implies a vendor connection or classifier accuracy.

E03-S02 adds `agentgate-agent` and `agentgate-hermes`; no gateway/identity/schema
contract is changed. Direct pending-state files bind endpoint, credential digest,
model, transport and run limits; they are private client state, never authority.
Hermes support is deliberately pinned to source f97608f (0.21.5) and its MCP extra
lock; different versions fail closed until reviewed. REST/MCP aliases, upstream
adaptations, exit codes and explicit approval resumption are documented in
`docs/restricted-agents.md`. Native host access is outside the profile boundary.

Threat evidence adds protected `GET /admin/threat-taxonomy` and nullable-by-absence
version-1 `threat_context` on `/admin/events` only. Existing operator auth, origin,
CSRF and agent-credential rejection remain. Every current runtime level is unknown;
finite layer/OWASP associations are diagnostic and confer no permissions. Older
admin payloads render unknown in the UI. No migration, persisted AuditEvent field,
public REST/model/MCP body/reason/status/default, telemetry-v1 or export-v1 field
change occurs. Exact v1 projection keys and denied-boundary privacy are regression
tested. See `docs/threat-model.md` for version and association semantics.

Acceptance report schema 1 preserves its existing inventory/source/JUnit fields
and adds separately versioned `threat_evidence`. Legacy `--check`, `--markdown`
and `--run` commands remain supported. The strict sidecar now validates exact
48+54 references, original frozen corpus bytes and versioned axes; invalid metadata
fails the command. Actual collected parametrized node IDs and all execution phases
must reconcile; ambient PYTEST_ADDOPTS cannot narrow the gate. Readers that ignore
the additive object retain old fields. New consumers distinguish declaration,
execution and readiness; no semantic measurements are imported or recomputed.
