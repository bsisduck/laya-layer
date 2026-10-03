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
- `ControlPlane.assert_current(connection, snapshot)` runs inside the same SQLite
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

The exact routes, session protocol and error shapes will be finalized here with
the authenticated router implementation. Integration entry point:
`attach_admin_routes(app, service, *, origin, ...)`. Only small optional app/CLI
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
This branch implements document mode only. Other modes remain visibly unavailable
until their owning story attaches a real implementation. Do not synthesize responses.

### Tools integration reserved routes

The tools owner supplies `service.tools` with tenant-required bounded
`list_approvals`, `decide`, `outbox` hooks. The admin adapter will call those real
hooks only when installed. Contract:

- GET `/admin/approvals?tenant_id=tenant-a&limit=100` -> `{"approvals":[...]}`.
- POST `/admin/approvals/{id}/decision`: JSON
  `{"tenant_id":"tenant-a","fingerprint":"…","approve":true}` -> decision result
  from the tools hook. Adapter fixes `actor="operator"` (never body-selected).
- GET `/admin/outbox?tenant_id=tenant-a&limit=100` -> `{"messages":[...]}`.

Missing hooks return 503 with a safe explicit unavailable detail, never a fake
empty list or approved result. Tool owner defines immutable approval item and
outbox metadata fields. This global local operator can select a tenant; agent
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
