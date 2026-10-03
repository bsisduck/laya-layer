# Operator control plane contract (E01-S01)

Integration contract for model/tool/frontend owners. This story owns `admin.py`,
`control_plane.py`, and document snapshot enforcement. ModelPolicy, model routes,
model budgets, new tools, approvals, and frontend remain separate work. Preserve
`policy.models` and `chat.completions` audit operation when combining branches.

## Service hooks

- `service.policy` returns the current immutable `Policy`. Read once for a decision;
  do not repeatedly read it during an in-flight action. Assignment is retained for
  legacy static services/tests only; live services activate via `service.controls`.
- `service.current_controls() -> ControlSnapshot` reads one coherent durable
  policy/feed/generation. A service without attached controls returns its static
  policy and an empty feed (generation 0).
- `snapshot.policy`, `.feed`, `.generation` are immutable. `snapshot.feed.version`
  identifies feed evidence. Capture at admission and recheck before side effects.
- `snapshot.inspect(stage, text, *, artifacts=()) -> None` is the mandatory reusable
  screening callback. Stages: `model_input`, `tool_action`, `tool_result`,
  `model_output`, `artifact_intake`. It raises `ThreatBlocked` with bounded
  `indicator_ids` (never matched content); malformed/oversized input raises
  `ValueError`. Fail closed on either. Text is limited to 262144 UTF-8 bytes;
  structured caller payloads must be normalized before passing them here.
- `snapshot.assert_current(connection)` (also `ControlPlane.assert_current(connection, snapshot)`) runs inside the same SQLite
  `BEGIN IMMEDIATE` transaction as reservation/intent. `ControlsChanged` requires
  bounded retry of the whole decision with a fresh snapshot, before dispatch.
  `Store.dispatch_intent(..., before_dispatch=callback)` provides this hook for
  documents. Models should use it inside their existing reservation transaction.
- After durable dispatch, keep that snapshot for output screening, response and
  audit versions. An update cannot undo an already-dispatched side effect. Release
  only after output screening and durable outcome audit. Never convert a callback
  failure into allow, and never use feed matching to grant permissions.

## Feed JSON

`{schema_version:1, feed_id:"local", revision:2, indicators:[...]}`; at most 128
unique indicators, 64 KiB serialized document. Each indicator has `id`, `kind`,
`value`, `stages` (defaults to all five). Kinds: `literal_text` (case-sensitive
substring, at most 512 characters; no regex), `blocked_domain` (canonical lowercase
ASCII domain, exact or subdomain match), `blocked_sha256` (64 lowercase hex),
`blocked_source` (canonical absolute HTTP(S) URL, no credentials/query/fragment).
Domain tokens recognize hostnames in URLs, email and plain text; this is a bounded
lexical control, not arbitrary encoded content or network destination validation.
Sources compare canonical URLs exactly; callers must still enforce destination
allowlists. Digests compare hex tokens or trusted artifact metadata.

`ArtifactMetadata(sha256, source, serialization)` supports `safetensors`, `json`,
`pickle`, `joblib`, `torch_pickle`. The last three always deny. This metadata
inspection never reads files, fetches URLs, imports code or deserializes weights.
It is an intake-policy demonstration, not proof that a checkpoint is safe.

## Activation and storage

`ControlPlane(store).initialize(policy)` adds isolated control/session tables in
schema-2 state, seeds once, and preserves existing durable controls on restart.
`activate_policy(policy, expected_version)` and `activate_feed(feed, expected_version)`
validate before a SQLite atomic update+activation event. ID remains stable and
revision must strictly increase. Stale expected versions/replay return conflicts.
Policy and feed share a generation so neither update can be missed at dispatch.
Invalid/rejected updates retain last good controls. Old binaries cannot enforce
live updates: stop serving before rollback; export remains compatible.

## HTTP and bootstrap

The routes below are frozen for the authenticated router. Integration entry point:
`attach_admin_routes(app, service, *, origin, tools=None)`. Only small optional app/CLI
hooks belong in this branch; root resolves those hooks on integration.

## Frozen frontend API (2026-10-03)

All `/admin/*` responses use `Cache-Control: no-store`. Errors are JSON
`{"detail":"safe explanation"}`. 401 means missing/invalid operator session;
403 means origin/CSRF denial; 409 stale activation; 422 invalid data; 503 unavailable.
No bearer authorization on admin endpoints. Agent tokens fail login. The configured
origin/Host is exact; HTTP is allowed only on loopback, otherwise HTTPS is required.

### Session

- POST `/admin/session`: JSON `{"token":"<operator.token contents>"}` plus exact
  `Origin`. Returns `{"authenticated":true,"expires_at":<Unix seconds>,"csrf_token":"…"}`.
  Sets `agentgate_operator` cookie, Path=/admin, HttpOnly, SameSite=Strict, lifetime
  900 seconds, Secure on HTTPS. A new login invalidates the previous cookie session.
- GET `/admin/session`: same JSON as login; no renewal or sliding expiry.
- DELETE `/admin/session`: returns `{"authenticated":false}` and revokes/deletes cookie.
- Every write after login requires `Origin` and `X-CSRF-Token` from login/introspection.
  Browser fetch sends cookies; keep CSRF in memory and never persist the operator
  token. GET requires a valid cookie and rejects a supplied foreign Origin.

### Policy and feed

- GET `/admin/policy`: `{"policy":<Policy JSON>,"version":"<policy_id>:<revision>"}`.
- POST `/admin/policy/validate`: `{"policy":<Policy JSON>}` ->
  `{"valid":true,"version":"…"}`. Invalid returns 422, leaves current untouched.
- POST `/admin/policy/activate`: `{"policy":<Policy JSON>,"expected_version":"…"}`
  -> same shape as GET. Stable policy ID, strictly increasing integer revision.
- GET `/admin/feed`: `{"feed":<ThreatFeed JSON>,"version":"local:1",
  "indicator_count":0,"refresh":"operator-managed"}`.
- POST `/admin/feed`: `{"feed":<ThreatFeed JSON>,"expected_version":"local:1"}`
  -> same shape as GET. Stable feed ID and strictly increasing revision. Both feeds
  and policies reject duplicate keys, unknown fields, nonfinite numbers, oversized
  bodies, stale versions and replay. Feed schema/kinds are specified above.

### Overview and events

GET `/admin/overview` returns:

```json
{
  "policy_version":"test:1", "feed_version":"local:1",
  "controls":{"authentication":true,"document_authorization":true,
    "redact_emails":true,"semantic_required":false,"semantic_mode":"enforce",
    "threat_feed_indicators":0},
  "counts":{"allow":0,"redact":0,"deny":0,"pending":null},
  "count_window":{"status":"measured","audit_rows":0,"limit":1000,
    "scope":"latest audit rows; terminal events only"},
  "budgets":{"status":"measured","tool_counters":[],"limit":1000,"model":null},
  "services":{"gateway":"ready","semantic":"not_configured"},
  "latency":{"status":"unknown","reason":"Gateway latency is not recorded"},
  "coverage":{"enforced":["documents.read"],
    "not_implemented":["models","memory","mail","approvals","mcp"],
    "real_model_evaluation":"not_run","pending_approvals":"unknown"}
}
```

Values above illustrate an empty database, not demo telemetry. `counts` measures
terminal audit events in the latest 1000 rows; pending is unknown until approval
integration. `tool_counters` retains `scope`, `scope_key`, `reserved`, `spent`.
Semantic service values are `not_configured`, `ready`, `unavailable`. Integration
owners update coverage for genuinely attached capabilities; no fabricated metrics.

GET `/admin/events?limit=100` -> `{"events":[...],"control_events":[...]}`, newest
first, each array bounded to 1–1000. `events` uses audit export schema 1's allowlist
plus nullable `feed_version`: event_id, sequence, timestamp (ISO UTC), event_type,
action_id, trace_id, tenant_id, principal_id, root_run_id, operation, decision,
reason_codes, policy_version, executed, semantic_status. `control_events` has
sequence, timestamp (Unix seconds), kind (`policy_activated`/`feed_activated`),
version and generation. No full prompts, results, credentials or payload digests.

### Playground

POST `/admin/playground`: `{"mode":"document","document_id":"tenant-a-notes"}`.
Returns existing `ActionResponse`: status (`completed`/`denied`/`error`), action_id,
trace_id, decision (`allow`/`redact`/`deny`), reason_codes, policy_version, executed,
optional result (`document_id`, `content`). A denial uses its actual HTTP 4xx/5xx
status with that action body, not a fabricated success. Tenant/roles/principal are
never accepted from the body. Fixed server-owned tenant-a analyst demo scope/root.
Known fixtures: tenant-a-notes (allow), tenant-a-contact (redact), tenant-a-leak
(output deny), tenant-a-secret (pre-read deny), tenant-b-notes (tenant deny).
Document execution is implemented here. Memory/mail adapters forward these exact
additional discriminated shapes to `service.execute` when real `service.tools` is
attached (otherwise 503):

- `{"mode":"memory","query":"…","limit":10}` (limit optional, 1–10).
- `{"mode":"mail","recipient":"analyst@demo.internal","subject":"…","body":"…",
  "idempotency_key":"stable-key"}`. The canonical operation is `mail.send`; the
  payload is unchanged except removing mode. After approval, repeat this same
  body/key to execute through the tool owner. No new resume mode.

`response_status(result)` maps pending/approved to 202, expired to 410, denied to
403, consumed/completed to 200; gate errors retain their own status. ActionResponse
is returned directly, preserving tool-owned approval_id/action_state/expires_at.
Model playground remains with the model owner; no model executor is added here.

One internal credential is deterministically derived with a domain-separated HMAC
from the private audit key and registered once for the fixed demo principal/root.
Its initial lifetime is 24 hours (greater than the tool owner's maximum 1-hour
approval TTL). It persists through retry/process restart and is never deleted after
pending/approved output, exposed to the browser, renewed on expiry, or unrevoked.
Expiry/revocation denies later proposals/retries. For a fresh demo after expiry,
initialize a new private demo state explicitly; do not silently reset credentials
or budget counters. A pending approval can still expire earlier if its credential
expires; the tool authority must revalidate both.

### Tools integration reserved routes

The tools owner supplies `service.tools` with tenant-required bounded
`list_approvals`, `decide`, `outbox` hooks. The admin adapter calls those real
hooks only when installed. Supply `tools=` at attachment or `service.tools`;
these are forwarding adapters, not an approval implementation. Contract:

- GET `/admin/approvals?tenant_id=tenant-a&limit=100` (limit 1–100) -> `{"approvals":[...]}`.
- POST `/admin/approvals/{id}/decision`: JSON
  `{"tenant_id":"tenant-a","fingerprint":"<64 lowercase SHA-256 hex>","approve":true}` -> decision result
  from the tools hook. Adapter fixes `actor="operator"` (never body-selected).
- GET `/admin/outbox?tenant_id=tenant-a&limit=100` (limit 1–100) -> `{"messages":[...]}`.

Missing hooks return 503 with a safe explicit unavailable detail, never a fake
empty list or approved result. Tool owner's frozen list row contains action_id, tenant_id, principal_id,
root_run_id, operation, exact stored payload (recipient/subject/body/idempotency_key),
payload_digest, fingerprint, policy_digest, registry_digest, policy_version,
created_at, expires_at, state, reason, decided_by. Display exact payload and submit
its fingerprint; there is no separate detail route. A successful decision returns
ActionResponse directly and never executes: approved/require_approval, executed=false,
action_state=approved, approval_id=action_id. The tool authority owns stale/replay
handling. Outbox rows contain action_id, recipient, created_at, delivery_state=fixture;
this is a local test effect, never a claim of SMTP delivery. This global local operator can select a tenant; agent
credentials cannot use this boundary. No approval bypass or execution is added here.

### Export

GET `/admin/audit/export?tenant=tenant-a&format=jsonl&limit=100`, or
`unattributed=true` instead of tenant (exactly one required). Optional
`after_sequence=0`, `through_sequence=<snapshot high-water>`; limit 1–1000;
formats `jsonl`, `ecs`, `splunk-hec`. Returns an NDJSON attachment, unchanged export
schema 1. `X-AgentGate-Cursor` is JSON containing next_after_sequence,
through_sequence, scanned, exported, has_more. Continue with the returned high-water
and cursor to stay in the same snapshot. An empty page can still advance scan
progress. This is a local download, not downstream delivery acknowledgment.


## Local startup and limits

From a stopped checkout: `make setup`, `agentgate init-demo`, then
`agentgate init-operator` in the same `--state-dir` (default `.agentgate`). The latter
creates `operator.token` with mode 0600 in a private directory, stores only its hash
in a separate table, prints no secret and refuses existing files/credentials. Then
`agentgate serve` attaches admin routes at `http://127.0.0.1:8000`; change the exact
origin with `--admin-origin`. A frontend must use that exact host, not interchange
localhost and 127.0.0.1. Existing agent routes remain usable via `create_app(service)`
without admin attachment. Root combines `models=` with the optional `admin_origin=`
keyword; this branch does not create or route ModelService.

No browser UI is supplied by E01-S01. Use the frontend story for login/display.
The operator has global local administrative authority, not enterprise tenant RBAC.
At most 32 unexpired sessions are retained; login rotates the supplied old session,
expiry/logout invalidates replay, and expired rows are pruned at login. A host
administrator remains trusted. Loopback HTTP cannot promise transport encryption;
use HTTPS for remote access. Never expose this demo through wildcard CORS or
untrusted reverse-proxy forwarded headers.

The CSRF design uses exact configured origins plus a session-bound header and
SameSite cookies, following the relevant
[OWASP guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
Literal/domain feeds are deterministic matching, not semantic evaluation or a
universal attack detector. No Laya/Ollama inference is run by this story's tests.


## Integration handoff

The model/tools owner combines the additive `models` and `scoped_tools` Policy
blocks with this branch's persisted Policy serialization. Preserve tool-owned
`Context.policy`, `inspect_text` and audit operation enums (documents.read,
memory.query, mail.send, chat.completions) alongside `Context.controls`. This
branch never removes those additions from the other branches. Resolve small
`app.py`/`cli.py` hooks with named keywords; preserve `response_status` from the
tools story when combining adapters. Static generation-0 snapshots make
`assert_current` a no-op; live snapshots verify the generation inside the
caller's reservation/intent transaction. Real model/tool integration validation
belongs to the integrating branch, not this story's callback/forwarding fixtures.
