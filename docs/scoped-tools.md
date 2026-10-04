# Scoped tools, exact approvals and MCP (E01-S03)

The [approved tool catalog](tool-catalog.md) binds reviewed effect/risk/adapter and
approval metadata into the registry, adds protected operator discovery and
generated MCP hints, and documents pending-approval reproposal during upgrades.

Implemented: credential-owned `documents.read`, `memory.query`, and `mail.send`
through the same service and REST/MCP adapters. Mail writes **only a local fixture
outbox**. No SMTP, remote MCP proxy, memory writes, operator authentication, model
routing, or universal semantic-safety claim is added by this slice. Tests use real
SQLite transactions and HTTP/MCP protocol calls, with fixture data; they are not
real Laya/Ollama evaluation.

## Run and migrate

`make setup` installs locked development dependencies including the optional MCP
extra; `make validate` includes MCP wire tests. For a standalone install use
`uv sync --locked --extra mcp`, then `agentgate init-demo` and
`agentgate serve --mcp`. The demo credential grants all three tools, expires in one
hour, and stays in the private `client.token` file. Two tenants' memory fixtures
are seeded; only credential-owned tenant rows can be queried.

For existing state: stop all gateway processes, back up the SQLite database with
SQLite's backup API (including committed WAL state), and run `agentgate migrate`.
The schema-2 database gains versioned `scoped_tool_schema`, `memory_entries`,
`tool_actions`, and `tool_outbox` tables and immutable-action triggers. Existing
credentials/audit/daily budgets remain. Root accounts `[tenant, principal, root]`
are summed into `[tenant, root]`; unresolved reservations are rewired and retain
capacity. Readiness rejects missing tables or legacy root keys. Repeating migration
is safe. Do not run mixed old/new binaries; old code cannot enforce shared roots or
new tools. Rollback means restoring a stopped pre-upgrade backup, never deleting
live spend or outbox rows. See [budget migration](budgets.md).

## REST contract

`GET /v1/tools` returns `{tools:[canonical names...]}` filtered by credential scope
and policy roles. Exact aliases `documents_read`, `memory_query`, and `mail_send`
are accepted, alongside dotted canonical names. Arbitrary prefixes are rejected.
All endpoints authenticate on every request and reject identity override headers
and query parameters. Existing document responses remain compatible.

`POST /v1/actions/execute`, with an agent bearer credential:

```json
{"operation":"memory.query","arguments":{"query":"Quarterly","limit":10}}
```

Returns only authorized tenant/classification rows as `result.entries`, each with
`entry_id` and inspected `content`. Query is a literal substring (no SQL wildcard
semantics); limit is 1–10, query 1–512 characters. Read intent/budget persist before
the query; inspected outcome audit persists before output release. Blocking output
still charges the performed read. There is no agent memory-write route.

```json
{"operation":"mail.send","arguments":{"recipient":"analyst@demo.internal","subject":"Review","body":"Exact content","idempotency_key":"mail-001"}}
```

Recipient must be an ASCII mailbox with an exact lowercase allowlisted domain.
No display names, lists, redirects, suffix matching, or recipient rewriting.
Subject is 1–200 characters, body 1–8192, key uses the Identifier contract.
Synthetic secrets and required unavailable/blocked semantics deny before effect.
Policy `scoped_tools` adds memory/mail roles, memory classifications, exact
`mail_domains` (default `demo.internal`) and `approval_ttl_seconds` (1–3600,
default 300). Approval is mandatory and cannot override a denial.

An allowed proposal returns **202**, `status: pending_approval`,
`decision: require_approval`, `executed: false`, and `approval_id`, `action_id`,
`action_state`, `expires_at`. No outbox row or execution reservation exists yet.
`GET /v1/actions/{id}` retrieves the caller's state; `POST
/v1/actions/{id}/resume` accepts **only `{}`** and executes the stored snapshot.
Alternatively repeat the exact original execute call. Responses preserve fresh
trace correlation and the original action ID.

States: `pending` → `approved` → `consumed`, or terminal `denied` / `expired`.
Consumed actions return the same acknowledgement (`outbox_id`, `delivery_state:
fixture`), never another effect. `executed: true` describes the stored action, not
a new dispatch by that retry. Denied/expired responses are 403/410; malformed input
422, auth 401, wrong/unknown owner 404 (same owner, different credential 403),
changed payload under an existing key 409, exhausted budget 429, unavailable
ledger/audit/required semantics 503. Retry payload conflicts remain conflicts after
consumption; a new payload needs a new key and approval.

The fingerprint binds full identity (including agent/scopes), exact issuing
credential, tenant/root, canonical payload HMAC, complete policy digest, registry
schema/aliases/target version, control binding and expiry. The private database
stores the immutable action; SQLite triggers reject snapshot updates. Audits omit
mail content and recipients. Expiry, policy/registry changes, credential revocation,
current authorization, and budgets are checked again at dispatch. A new approval
requires a new action after invalidation.

Outbox insert, unique action key, intent, completion audit, budget settlement and
consumption commit atomically. Failure before commit rolls all of them back.
After a lost acknowledgement, retry reconciles from the committed action/outbox.
This is one local SQLite effect; it is not exactly-once delivery across an external
mail system. Pending approvals do not reserve execution capacity indefinitely.

## Callable operator hooks

The operator task owns authentication, same-origin writes and tenant grants. It
may call the following **trusted in-process** hooks after authorizing a sensitive
view/decision. They are never exposed to agent credentials by this slice:

```python
service.tools.list_approvals(tenant_id="tenant-a", limit=100)
service.tools.decide(
    tenant_id="tenant-a", action_id=action_id, fingerprint=displayed_fingerprint,
    approve=True, actor=authenticated_operator_id,
)
service.tools.outbox(tenant_id="tenant-a", limit=100)
```

Limits are 1–100. The approval list includes exact payload, identity references,
state, fingerprint, policy version and expiry for operator review. A stale or
wrong fingerprint cannot approve another action. `decide` returns ActionResponse,
revalidates active state/credentials/policy before approving, and records operator
identity in the action row. Repeating a terminal decision never resurrects it.
Outbox hooks expose bounded metadata (`action_id`, recipient, creation time,
`delivery_state`), scoped to the explicitly authorized tenant. Operators must not
expose these methods or their exact-content output to the agent API.

## Frozen operator HTTP and playground integration

These routes belong to PR17; the hooks above supply their real data. PR20 consumes:

- `GET /admin/approvals?tenant_id=tenant-a&limit=100` → `{approvals:[row]}`.
  Exact details are in each row; no separate detail endpoint is required. Row
  fields: `action_id`, `tenant_id`, `principal_id`, `root_run_id`, `operation`,
  `payload` (recipient/subject/body/idempotency_key), `payload_digest`, `fingerprint`,
  `policy_digest`, `registry_digest`, `policy_version`, `created_at`, `expires_at`,
  `state`, `reason`, `decided_by` (nullable).
- `POST /admin/approvals/{action_id}/decision` body
  `{tenant_id, fingerprint, approve: true|false}` → direct ActionResponse.
  Approval returns `status: approved`, `action_state: approved`,
  `decision: require_approval`, `executed: false`. It never implicitly resumes.
- `GET /admin/outbox?tenant_id=tenant-a&limit=100` → `{messages:[metadata]}`,
  using the outbox projection above. Both lists accept limits 1–100.
- `POST /admin/playground`: `{mode:"memory", query, limit?}` or
  `{mode:"mail", recipient, subject, body, idempotency_key}` → direct
  ActionResponse. Existing `{mode:"document", document_id}` is retained.
  Mail retries repeat the **exact** body and key after approval; changed arguments
  return 409. For an approval-pending playground action, the operator plane must
  retain a server-private, fixed-principal/root credential across requests, with
  sufficient lifetime for the approval TTL. Issuing/deleting a credential on every
  request cannot resume the credential-bound action. Root/PR17 own this plumbing.

The UI must not equate an approved decision with execution. Only a consumed action
response with `executed: true` and `result.outbox_id`, or an actual outbox row,
proves the local fixture effect. The response's `policy_version` identifies the
stored proposal; denial audit uses the current snapshot used to invalidate it.

## Live policy/feed integration with PR17

The tools automatically capture `context_controls(context)` (or `current_controls()`
for discovery without an action) when PR17's service methods are present. The
structural `LiveControlSnapshot` contract matches its immutable
`ControlSnapshot(policy, feed, generation)`. `snapshot.inspect(stage, text)` screens
`tool_action` and `tool_result`; `snapshot.assert_current(db)` delegates to
`ControlPlane.assert_current(db, snapshot)` **inside the same write transaction** as
reservation/intent/outbox. Generation enters the approval fingerprint, so feed or
policy activation invalidates a pending/approved action. Inspector/check failures
become sanitized fail-closed GateErrors. A live service lacking these methods or an
explicit provider fails closed.

An explicit `service.tools.snapshot_provider: Callable[[], ToolSnapshot]` remains
available for other embeddings and contract tests. Its fields are `policy`, stable
control-generation `binding`, `inspect(stage, text)`, and `assert_current(db)`; these
callbacks must reject changes or blocked content, never silently allow them.

Root integration after PR17/PR6 land: preserve `policy.models`, `chat.completions`
and all tool operation/event variants while combining the additive policy/audit/app
changes; keep `Context.controls` plus `Context.policy`, and the shared `inspect_text`
helper using the captured policy; wire operator hooks behind PR17 authorization.
The `chat.completions` audit operation is retained in this branch's expanded enum.
Static services capture configured policy and reject a changed snapshot. This
standalone branch has no live activation route. Root owns the full application
demo and independent security review before release.

## MCP wire contract

`agentgate serve --mcp` enables `/mcp` using the official Python SDK (`mcp` 2.3.0
in `uv.lock`). The SDK owns initialize, capabilities, RPC correlation and HTTP
sessions for the SDK's supported handshake revisions (2024-11-05 through
2025-11-25); stateless per-request-envelope revisions are explicitly rejected.
The adapter supplies authenticated SDK users bound to the exact run
credential; every HTTP request and tool dispatch checks current credentials.
Session IDs never substitute for bearer authentication. Tool discovery is filtered,
and calls return protocol-compliant text plus structured ActionResponse results.
Denied/error/expired results set `isError`; pending approval is a non-executed
structured tool result. Retry the same mail call after operator approval.

Only tools are advertised. Resources, prompts, sampling, tasks, arbitrary
upstreams and an `approve` method are not registered. Loopback host/origin checks,
body/depth/deadline bounds, duplicate-key rejection and 128-session/300-second idle
limits apply. This is a standalone loopback bearer deployment; enterprise OAuth,
public exposure and transparent remote proxying are outside this contract.
