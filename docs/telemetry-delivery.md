# Durable telemetry delivery (local contract lab)

`agentgate-telemetry` delivers the existing version-1 minimized JSONL projection
to the runnable **Laya local HTTP contract collector v1**. This is a compatible
consumer of that projection, **not Splunk HEC, Elasticsearch, OpenSearch, or a
bank deployment**. ECS and HEC file export remain unchanged. No vendor endpoint
or bank was contacted. Delivery is asynchronous and does not authorize actions.

## Run locally

Python 3.12 on macOS/Linux; run `make setup` once. Keep credentials and runtime
state outside the checkout, private to the trusted gateway operator. Agent
processes must not have filesystem access to these files. Native same-user
processes are not sandboxed by this lab.

```sh
umask 077
mkdir -p "$HOME/.local/state/laya-telemetry-lab"
uv run --locked python - <<'PY'
import os, secrets
from pathlib import Path
p = Path.home() / '.local/state/laya-telemetry-lab/collector.token'
with open(p, 'x', opener=lambda n, f: os.open(n, f, 0o600)) as stream:
    stream.write(secrets.token_urlsafe(32))
PY
```

The exclusive create refuses to overwrite an existing credential. The token
must be an operator-owned regular file with no group/other permissions, containing
32–256 URL-safe ASCII characters. It is read per attempt/request, permitting file
rotation; do not put its value in JSON, command arguments, logs or Git.

Create private `sender.json` alongside it (origin has **no trailing slash**):

```json
{
  "origin": "http://127.0.0.1:8095",
  "tenant": "tenant-a",
  "batch_events": 100,
  "batch_bytes": 262144,
  "timeout_seconds": 5.0,
  "retry_initial_seconds": 1.0,
  "retry_max_seconds": 60.0,
  "poll_seconds": 1.0,
  "backlog_high_watermark": 10000
}
```

`tenant` is required; explicit `null` selects only unattributed audit events.
There is no all-tenants option. The sender reads credential-owned audit identity,
not request-body identity. Collector scope is configured independently and bound
to its database. A scope mismatch rejects the whole batch.

Start the collector in one terminal:

```sh
uv run --locked agentgate-telemetry collector \
  --database "$HOME/.local/state/laya-telemetry-lab/collector.sqlite3" \
  --token-file "$HOME/.local/state/laya-telemetry-lab/collector.token" \
  --tenant tenant-a --port 8095
```

Use `--unattributed` instead of `--tenant` for a null-tenant collector. It binds
only `127.0.0.1`, disables access logs, and exposes non-sensitive liveness at
`GET /health/live`. Default collector capacity is 100,000 unique rows;
`--max-rows` accepts 1–1,000,000. Exhaustion rolls back the entire batch with 507.
It never evicts evidence. Inspect committed rows through the private SQLite
`received(event_id, record, received_at)` table; `received_at` is the insertion
wall-clock timestamp, sampled before transaction commit. There is no public
query or admin endpoint on this collector.

Given a gateway source database (initialize/use the existing document demo), run:

```sh
uv run --locked agentgate-telemetry send \
  --source .agentgate/agentgate.sqlite3 \
  --config "$HOME/.local/state/laya-telemetry-lab/sender.json" \
  --token-file "$HOME/.local/state/laya-telemetry-lab/collector.token"
uv run --locked agentgate-telemetry status \
  --source .agentgate/agentgate.sqlite3 \
  --config "$HOME/.local/state/laya-telemetry-lab/sender.json"
```

`send` processes at most one bounded source page/attempt and prints status. A
retained failure/backoff exits 1; success can still have remaining source lag.
Add `--daemon` to poll/retry continuously. SIGINT/SIGTERM requests a graceful
stop after the bounded current attempt; restart resumes the durable batch.
Supervisor restart is needed for local state/config errors that terminate the
process. No automatic installation, service registration, or gateway startup
hook is implied.

## Delivery contract and recovery

POST exactly `/v1/events` at the configured origin, with bearer authentication
and `Content-Type: application/json`. Configuration is a bounded 16 KiB JSON file;
unknown fields (including URLs per event, credentials, index overrides) reject.
HTTPS uses normal certificate verification. Plain HTTP is accepted only for the
literal `127.0.0.1`. Paths, query strings, userinfo and fragments are forbidden in
the origin. Proxy environment variables are ignored; redirects are never followed.
Only loopback HTTP was exercised here; production TLS deployment is unverified.

Request:

```text
{"version":1,"batch_id":"<sha256>","events":[<version-1 JSONL projection>, ...]}
```

The batch ID hashes the ordered projected events as sorted-key compact JSON.
The protocol requires 1–100 events, unique event IDs and increasing source
sequences. A batch body is at most 256 KiB (operator may lower to 4 KiB).
Source scans cover at most 100 rows; source event bodies are at most 64 KiB as in
file export. Oversize pages shrink; an individual invalid/oversize event blocks
progress rather than being discarded. No raw prompt, document, request argument,
payload digest or detailed semantic scores/labels enter the projection.
Operational tenant/principal identifiers remain sensitive.

Successful response, **only after durable commit**:

```text
{"version":1,"batch_id":"<same sha256>","accepted_event_ids":["<id1>","<id2>"]}
```

Require HTTP 200, JSON, no compression, integer version 1, the same batch ID and
**every ID in exactly the same order**. Unknown fields, error arrays (even with
200), missing/extra/duplicate IDs, duplicate JSON keys, partial acks, non-finite
values or invalid JSON fail the attempt. Responses are capped at 32 KiB. Default
5-second total request deadline covers slow streams, in addition to I/O timeouts;
configurable range 0.05–30 seconds. No response body/header or token is logged.

The collector transaction inserts each new `event_id`, accepts an identical
replay, and rejects a reused ID with different projected content. Scope conflict,
capacity or SQLite failure rolls back the batch. A lost response or process crash
can therefore replay a committed batch: **at-least-once delivery with collector
deduplication**, not an end-to-end exactly-once guarantee.

Beside `SOURCE.sqlite3`, the sender owns private `SOURCE.telemetry.json`,
`SOURCE.telemetry.lock` and at most one `SOURCE.telemetry.tmp` scratch file. The
checkpoint holds one bounded pending batch, source scan cursor/anchor, aggregate
counters and retry metadata. It is flushed, atomically replaced and its directory
fsynced. The batch is persisted **before** HTTP; cursor advancement is persisted
**after** an exact acknowledgment. Crash after receiver commit/before checkpoint
replays the same IDs. Failed local checkpoint writes cannot claim durable progress.
Process-kill recovery is tested; physical power-loss fault injection is not.

A nonblocking OS file lock excludes a second sender for the same canonical source;
one sender instance also rejects overlapping iterations. This is a single-host,
local-filesystem design, not a distributed lease. A crashed process releases the
lock. Do not delete/replace the lock file while a sender is running.

The checkpoint binds source path/device/inode, origin and tenant. Replacement,
relocation or destination/scope changes stop with unavailable status; they never
silently reuse a cursor. A missing checkpoint starts from zero (replay), not at
the latest event. Source rows must remain append-only and contiguous. Missing
sequences or checkpoint anchor mismatch block progress. Validated rows belonging
exclusively to other tenants may advance the scan cursor without network delivery;
`acknowledged_events` counts only actually acknowledged matching records.

Retries use capped exponential backoff, persisted across restart: initially 1s,
then 2s, 4s… up to 60s by default. Attempts remain single-flight; there is no
retry limit that drops the batch. Do not lower batch byte capacity below a retained
batch before draining it. Stop/back up source and sidecars together before moving
or restoring state. Preserve sidecars on normal restarts; deliberate checkpoint
removal means replay and reset local counters. Audit pruning/rotation and restoring
a different collector dataset need an operator reconciliation procedure.

## Capacity, status and root integration

The pending sender queue is **one bounded batch**; disk work uses one bounded
checkpoint and one scratch slot, and collector storage has a configured row cap.
The authoritative source audit database already grows independently of this
worker. Its retention is **not bounded by this PR**. No evidence is dropped when
the collector is unavailable, and this worker does not silently block the existing
gateway. `backlog_high_watermark` is a reporting threshold over global source
sequence lag, including rows from other scopes awaiting validation. Monitor disk
space and stop/throttle producers operationally if delivery cannot catch up.
An automatic gateway admission/retention policy belongs to root integration;
this status hook alone does not enforce backpressure on requests.

Callable operator hook (run in a threadpool from async admin handlers):

```python
from agentgate.telemetry import telemetry_status
from agentgate.telemetry_contract import read_config

status = telemetry_status(source_db_path, read_config(operator_config_path))
```

The caller **must enforce operator authorization first**; this helper is not an
HTTP endpoint or a tenant authorization layer. It performs bounded/read-only
state/source reads and a non-creating lock probe, needs no token, and emits no
origin, paths, IDs, event contents or arbitrary labels. Root can embed this object
in `/admin/overview` services/resources or add an authenticated status route.
No `admin.py`, UI or existing gateway route is modified here.

Normal result fields:

| Field | Meaning |
|---|---|
| `enabled`, `sender_running` | Hook configured; OS ownership currently held (not a health guarantee) |
| `status` | `idle`, `pending`, `retrying`, `backpressure`; no claim that an idle/stopped sender can connect |
| `acknowledged_through_sequence`, `acknowledged_events` | Durable scan checkpoint; separately the matching-event acknowledgment count |
| `source_lag_sequences`, `backlog_high_watermark`, `backpressure` | Global source lag and configured reporting threshold |
| `pending_events`, `pending_bytes` | Current retained batch bounds; source backlog is separate |
| `last_error`, `consecutive_failures`, `next_attempt_at` | Fixed `source_invalid`/`delivery_failed` codes, capped failure counter and epoch retry time |
| `updated_at` | Last persisted attempt completion, not an independent heartbeat |
| `last_delivery_ms` | Last successful batch stage+HTTP duration measured monotonically, excluding final local checkpoint fsync |
| `last_event_age_ms` | Latest event in that batch to collector ack, wall-clock difference clamped at zero |

On invalid/missing source or corrupt/mismatched checkpoint the safe result is
`{"enabled":true,"status":"unavailable","backpressure":true}`; other fields
are absent. Root should represent missing configuration as disabled and config
load errors as unavailable, not success. Report age/stopped state separately from
queue emptiness. Wall-clock adjustments affect retry schedules/event ages.

This branch starts at `33660d6` and reads source schemas 1/2 through the existing
exporter. PR6/17/19 add model/control/tool variants outside this branch. Root must
compose their source schema/version and `AuditEvent` extensions with the exporter,
then verify projection and receipt for each new variant. Unsupported rows fail
closed with `source_invalid`; this branch does not claim those paths delivered.

## Reproducible evidence

```sh
uv run --locked pytest tests/test_telemetry.py tests/test_telemetry_http.py tests/test_audit_export.py
uv run --locked python scripts/telemetry_benchmark.py --samples 100 --warmup 10
make validate
```

The HTTP suite launches actual TCP loopback servers on ephemeral ports and tears
down only processes it owns. CLI collector/daemon, graceful stop, killed sender
ownership and crash after collector commit are exercised. It asserts zero rows
for wrong auth/scope/oversize/capacity failures, one row after crash/replay of one
event, and exact correlation/privacy for gateway allow/redact/pre-dispatch-deny/
executed-but-withheld document outcomes. Partial-commit response injection proves
whole-batch replay fills the gap and deduplicates the already-received event.
These are deterministic controls and local HTTP integration tests; no semantic
model evaluation or third-party collector acceptance is claimed.

The benchmark runs the same synthetic document fixture directly, through the real
HTTP gateway with delivery disabled, and with a concurrent sender. It reports cold
first request separately, then warmed P50/P95, failures, source/collector row
counts, insertion timestamps, latest-event-to-ack times and per-batch duration.
Distribution differences are not paired causal estimates. Runs are sequential and
share the host; no universal latency guarantee follows. Source hashes and exact
sample/environment context are included in the JSON output. See the PR evidence
for measured results; generated benchmark reports are not committed.
