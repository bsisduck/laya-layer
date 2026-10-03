# Security event export

`agentgate audit-export` is an implemented **local operator** interface. It reads
existing schema-1 or schema-2 SQLite audit state without migrating it and produces
one bounded page. It performs no network delivery. It does not change the existing
`agentgate audit` output or gateway authorization.

```sh
uv run --locked agentgate audit-export --tenant tenant-a --format jsonl
uv run --locked agentgate audit-export --tenant tenant-a --format ecs
uv run --locked agentgate audit-export --tenant tenant-a --format splunk-hec
uv run --locked agentgate audit-export --unattributed --format jsonl
```

Use `--state-dir <directory>` before `audit-export` for another local state
directory. Either `--tenant` or `--unattributed` is required. Unauthenticated
requests have no verified tenant; they are not assigned to a tenant from the
request body. Host filesystem access is the privilege boundary: these selectors
are filters for a trusted operator, not authorization for an untrusted tenant.
Do not expose this command as a public endpoint or give agent processes the DB.

## Formats and privacy

- `jsonl`: one projected record per line with export `schema_version: 1`, stable
  event/action/trace IDs, sequence, UTC timestamp, tenant/principal/root, operation,
  decision/reasons, policy version, execution flag and coarse semantic status.
- `ecs`: the same record under `laya`, plus ECS-oriented timestamp, event and user
  fields. It is a documented field mapping, not certified compatibility with a
  particular Elastic integration package. No `ecs.version` is asserted yet.
- `splunk-hec`: structured canonical record in an HEC `event` envelope with epoch
  `time`, `source: laya-sec-layer`, and `sourcetype: laya:security`. It does not
  contain an endpoint, credential, or index override.

Only explicitly projected fields are exported. Payload digests, raw semantic
labels/scores, prompts, document contents, request arguments and credentials are
excluded. Tenant and principal identifiers remain operationally sensitive; keep
files and collector access restricted. For file export, set `umask 077` and write
stdout into an ignored private runtime directory. Export does not anonymize IDs.

ECS outcomes describe the requested action: terminal allow/redact is `success`,
denial is `failure`, and dispatch intent or uncertain execution is `unknown`.
`laya.decision` describes the control decision. A denied result with
`laya.executed: true` was withheld after execution. Count terminal events for
action totals; including `dispatch_intent` double-counts successful calls.
No severity, threat confidence, cost, full latency, AI-agent identity, or W3C trace
compatibility is inferred from evidence the current event schema does not have.

## Pagination and delivery boundary

Stdout contains records only. After stdout flush succeeds, stderr contains a JSON
checkpoint with `next_after_sequence`, `through_sequence`, `scanned`, `exported`
and `has_more`. Errors exit nonzero with a generic diagnostic, not a checkpoint.
The entire page is validated and serialized before any records are emitted.

The first page captures the largest committed sequence in a read transaction.
Continue with `--after-sequence <next_after_sequence>` and the same
`--through-sequence <through_sequence>` until `has_more` is false. Newer events
belong to a subsequent export. `--limit` bounds **scanned rows**, from 1 to 1,000
(default 100), so a page can contain zero matching events and still have more
work. Stored event bodies above 64 KiB or invalid rows fail the page.

Keep checkpoints bound to the same database, tenant selection and consumer.
They are not portable across a restored/replaced database. This command does not
persist a cursor or certify downstream receipt. After a pipe failure, replay the
page using stable event IDs; a future shipper must advance its durable checkpoint
only after the required downstream acknowledgment. No exactly-once claim is made.

The current tests exercise the gateway, persisted audit, projection and CLI.
No Splunk, Elastic, OpenSearch, Kafka or bank endpoint was contacted by this
exporter. The [integration design](enterprise-integrations.md) lists the remaining
transport and acceptance work.
