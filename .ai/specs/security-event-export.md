# Security event export

Provide a local operator command that exports existing audit evidence for Laya
Sec Layer integrations. This implements a reporting foundation for the supplied
AI Control Layer brief, not a live bank or vendor integration.

- Preserve the existing `audit` command and storage schema.
- Read an existing database in SQLite read-only mode. Never provision or migrate
  state from an export command.
- Require an explicit tenant, or a separate unattributed-event selection. This
  command is privileged by host filesystem access; the selector is not a new
  authentication boundary. No public HTTP endpoint is added.
- Project an explicit allowlist into canonical JSONL, ECS-oriented JSONL, or
  Splunk HEC envelopes. Omit payload digests, raw semantic dictionaries, prompts,
  document contents, credentials, and request arguments.
- Preserve stable event/action/trace IDs, event order, policy version, decision,
  execution status, and coarse semantic status. Never infer threat confidence or
  cost from classifier scores. Dispatch intent is not an executed action.
- Scan at most 1,000 records per page. Pin the snapshot upper sequence, support
  resumable scans, and advance over other tenants without exporting their data.
  Validate and serialize the entire page before writing stdout. Metadata goes to
  stderr only after successful output; failures do not issue a usable checkpoint.
- No network calls, delivery acknowledgments, persistent shipper cursor, metrics
  server, finding generation, or claim of vendor certification in this slice.

Acceptance: real gateway-generated allowed/redacted/blocked records, tenant and
unattributed separation, all three formats, duplicate-safe stable IDs, bounded
pagination including empty filtered pages, concurrent-append snapshot behavior,
read-only/no-create behavior, malformed/oversized data failure without partial
stdout, and compatibility with existing schema-1 audit records. Run `make validate`.
