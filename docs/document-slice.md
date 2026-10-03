# Document enforcement slice

This is the first implemented portion of the architecture, not the complete MVP.
The gateway is Python 3.12/FastAPI with a framework-independent policy/execution
service and SQLite credential/audit storage. All documents are synthetic fixtures.

## HTTP contract

`POST /v1/actions/execute` accepts `Authorization: Bearer <scoped credential>` and
`Content-Type: application/json`:

```json
{"operation":"documents.read","arguments":{"document_id":"tenant-a-notes"}}
```

Successful responses contain `status`, `action_id`, `trace_id`, `decision`,
`reason_codes`, `policy_version`, `executed`, and a `result` containing document ID
and permitted content. Denials/errors omit `result`. `X-Request-ID` matches the
server-generated trace ID; action responses use `Cache-Control: no-store`.

| Status | Meaning |
|---|---|
| 200 | Read executed and permitted result released, possibly redacted. |
| 401 | Credential missing, invalid, expired, or revoked. |
| 403 | Operation/resource denied, or executed output withheld by a control. |
| 408 | Request body deadline exceeded or client disconnected while sending. |
| 413 | Body exceeds configured byte limit, including chunked input. |
| 415 | Unsupported content type or content encoding. |
| 422 | Malformed, duplicate-key, excessively nested, or unsupported request fields. |
| 503 | Required semantic capability, storage, or executor unavailable/invalid. |

`executed` describes whether the executor was invoked. A post-execution output
block or failed outcome audit returns `executed: true` with no result. A failed
dispatch-intent write returns `executed: false`. A persisted intent followed by
a process crash can remain unresolved; it is not proof of successful execution.

`GET /health/live` returns only liveness. `/health/ready` requires writable SQLite
and no unavailable required semantic dependency. It certifies this document slice
only. Other architecture routes, including MCP/admin/model paths, are absent.

## Enforced boundaries

1. A random, expiring credential maps to a server-owned principal, tenant, agent,
   roles, operation scope, and root run. There is no public credential issuer.
2. Credential authentication precedes body parsing. Supplied identity fields,
   identity override headers, and query parameters are rejected.
3. Requests have a byte/depth/body-time limit, reject unknown fields, duplicate
   JSON keys and nonfinite values, and never echo validation input on failure.
4. Only canonical `documents.read` exists. `documents_read` is not a REST alias.
5. Agent operation scope, principal role, same-tenant metadata, and permitted
   classification must all allow access before the fixture executor is invoked.
   Unknown, cross-tenant and classified resources have the same denial reason.
6. Credential identity/expiry/revocation is rechecked in the SQLite transaction
   that commits dispatch intent. This is the dispatch authorization boundary;
   revocation after it cannot undo a read already admitted.
7. Output is bounded, synthetic secret markers are blocked, supported email
   addresses are redacted, and size is checked again after transformation.
8. The outcome must be durably audited before releasing content. A storage
   failure fails closed, including withholding a result already read.

Audit records contain allowlisted fields, credential-owned identity, correlation,
policy version, reason codes, and a domain-separated HMAC of bounded request bytes.
They contain no raw request/document, bearer token, or arbitrary operation name.
Credential digests use SHA-256 over 256-bit random tokens; the audit HMAC key is
separate. Events are append-only through the application API, not tamperproof
against a host administrator. SQLite uses WAL, FULL synchronization, and bounded
lock waits. Schema version 1 is new; there is no prior database migration.

## Policy and local operation

`config/policy.yaml` implements an explicitly partial schema: `schema_version`,
`policy_id`, `revision`, `ingress`, `documents_read`, `output`, and
`semantic_required`, `semantic_mode`, and optional `tool_budgets`. Unknown fields,
duplicate keys, aliases and oversized policy
files are rejected. The full architecture example cannot yet be loaded verbatim.
Policy is immutable for a running service; activation/reload endpoints do not exist.

Initialization creates a private state directory (0700), audit key and client
credential (0600), and SQLite file (0600). A credential lasts one hour; a new demo
session uses a fresh state directory. The operator-side CLI can inspect minimized
audit records; there is no unauthenticated audit HTTP endpoint.

## Coverage limits

Atomic document call budgets were added in [the budget slice](budgets.md).
No inference/provider budgets, rate quotas, approvals, mail/memory tools, external effects, policy
reload, threat feeds, MCP sessions, or model proxy is implemented.
Optional real standard/CoreML document-result checks are documented in
[semantic workers](semantic-workers.md).
`semantic_required: true` blocks readiness/dispatch when the configured worker is
unavailable instead of treating a stub as
real inference. The separately run Laya loading spike does not enable enforcement.

The executor performs a bounded in-memory fixture lookup; external workers will
require their own timeout/isolation boundary. Repeated reads are safe but are not
deduplicated and create new audit pairs. Do not extend this executor to writes
without reservations, stored action state, and idempotency.

The demo assumes trusted host processes. A process sharing the host user's file
permissions can access local state; the development harness is not a sandbox.
The synthetic marker scanner and email pattern are illustrative controls, not
universal DLP. Real classifier accuracy and prompt-injection resistance are unproven.
