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
