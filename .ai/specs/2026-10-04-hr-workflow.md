# HR employee workflow through the actual control layer

## Outcome

Make HR the main demonstration in the current Laya console: a synthetic candidate
record, a bounded employee/agent identity, an allowed read, an optional actual model
summary, blocked access outside authority, and exact review before one local message
effect. This is a consumer of accepted catalog, delegated-authority and local-console
capabilities. Do not build a parallel permission engine or weaken semantic policy.

The user requested the whole local app without a login screen. Keep local automatic
operator sessions and normal credential mode intact. The story must identify local
operator-provisioned employee records as local demo, never corporate IAM verification.
JWT exchange may be demonstrated separately once delivered; it is not a prerequisite
for offline local HR. No candidate ranking, hiring/rejection decision or real email.

## Data and authority

Use bounded synthetic server-owned fixtures with stable IDs/classifications: one
authorized HR candidate, an untrusted CV carrying a benign test injection, and an
out-of-scope same-tenant resource. Clearly identify synthetic data. Do not accept
arbitrary paths, arbitrary external URLs or browser-supplied data classifications.

Provide a documented reviewed HR policy preset using the delegated core's relational
grants and require-delegation rule. HR-BP human and hr-assistant agent grants should
be demonstrably different yet overlap for the allowed read. Include Dev and Finance
role examples to prove same-tenant separation, without executable GitLab/payment
adapters. Their examples remain non-executable catalog proposals.

Use server-owned parent credentials with stable accounting principal/root and a
short-lived core-issued child. Store no bearer credential in browser fields, HTML,
URLs, browser storage, logs or screenshots. An explicit operator action can start a
local scenario session; it must not silently extend expired parent authority, restore
revoked subjects, widen policy, reset budgets or transfer pending approvals. Expired
children require a deliberate new scenario binding with clear old-approval invalidity.
Use bounded private server state and cleanup of expired records; avoid unbounded
credential growth from page visits. Parent renewal uses existing explicit controls.

New installations may seed reviewed local demo fixtures/configuration once. Existing
installations retain active live policy and state. If HR policy is not configured,
show an actionable setup state with preview and explicit CAS activation, or provide
a documented operator CLI setup that preserves existing controls. Never overwrite
active_controls with a startup file. Any setup/issuance mutation is admin-session and
CSRF protected and audited; no automatic mutation on GET or page load.

## Actual actions and interface

Add an HR workspace or clearly primary preset flow. Show human requester/provenance,
agent, department, accounting owner, expiry and effective permissions separately.
Use normal readable UI copy, with technical binding details behind Inspect controls.
Preserve existing cream/forest visual design, navigation, keyboard/focus behavior,
loading/error/empty states and mobile layout. Do not require a sequence of manual
terminal commands for each demonstration action.

All reads, memory, model calls and approval resumes must use the normal REST/MCP/core
enforcement implementation with the delegated credential. An admin facade cannot
execute resources directly or substitute the operator's broader authority. Model
summary uses only previously authorized released data, preserving untrusted-content
provenance. Offer actual model invocation deliberately and report unavailable/denied
states honestly. Never manufacture a plausible summary if the provider or semantic
inspection failed. Keep existing bad semantic measurements visible.

For the CV injection, show the actual decision and audit trace. Deterministic known
fixture outcomes are test evidence; real semantic efficacy requires a separately
identified real-worker observation. Do not hardcode denial by scenario ID to claim
injection protection. A blocked out-of-scope read/destructive operation must show
zero executor/provider/outbox effects; do not render a fake completed bank action.

A proposed candidate-related message requires deliberate exact approval showing
recipient/content/requester/agent/effect/risk/expiry. Approval alone has no outbox
effect. Exact resume sends one message to the existing local fixture outbox; replay
does not send twice. Distinguish requester from local-console approver and never
call this four-eyes IAM. Recipient/content changes or authority/policy changes
invalidate prior consent. A session recovery must never replay an action.

Link the real resulting action/trace to audit, catalog and department usage evidence.
One sentence each explains future Dev (reviewed merge through an adapter) and Finance
(payment policy plus approval through an adapter). Their implementation status must
be visible without cluttering the employee flow with engineering checklists.

## Proof

Unit/functional: finite fixture/setup validation, facade cannot assert grants or
leak tokens, bounded lifecycle, missing/revoked/expired authority, exact payloads.
Integration: real delegated docs/model/approval paths, both independently narrower
human/agent scopes, same-tenant denied resource before access, forged scenario IDs,
semantic unavailable/deny propagation, policy/subject change before resume, one
outbox row after exact approval and none on rejection/expiry/payload mismatch.
Preserve pre-existing ordinary playground and public response/export contracts.

Installed browser E2E: fresh local-console startup, HR setup/binding, allowed read,
scope denial, actual review/resume/replay with DB evidence, trace navigation, expiry
without automatic mutation replay, keyboard/mobile and unavailable/error states.
Use deterministic fixture providers only when explicitly labelled; separately run
one coordinated real provider/semantic smoke after integration and keep its observed
outcome, including a false positive. Never run concurrent heavyweight model workers.

Run make validate, applicable frontend contracts and owned installed QA; document
setup, persistence and limits. Publish one scoped draft PR, no merge. Root performs
independent review/QA and requires green CI before integration. Final presentation is
a separate consumer of the delivered behavior and measured evidence.
## Independent design review resolutions (authoritative)

Review 2b515b65 requires the following concrete consumer contracts:

- Use a bounded process-private map for short-lived child secrets. Each entry owns
  a random scenario handle, authenticated operator-session reference, exact parent
  epoch/digest, subject revision and expiry. Publish it only after core issuance
  commits. The browser handle selects server state; it does not grant authority.
  Enforce a small fixed entry cap and expiry cleanup. Restart/session loss/expiry
  requires deliberate rebinding and new proposal keys; no secret reconstruction,
  approval transfer, automatic renewal or replay. Retain durable audit/approval rows.
- Freeze the HR identity independently of the existing playground: tenant-a,
  principal `hr-demo-account`, agent `hr-assistant`, root `hr-demo-run`, role
  `hr-assistant`, operations documents.read/mail.send/chat.completions. Provision
  its parent once through a trusted local setup; later parent renewal is explicit
  and preserves accounting identity/root. Fixed subject `hr-local-employee` has
  local-demo provenance, HR-BP role and department HR. Never revive revoked records
  or overwrite an existing conflicting record during setup.
- Register additive synthetic internal resources `hr-candidate-001`,
  `hr-cv-injection-001`, `hr-private-notes` and `finance-record-001`. HR-BP allows
  the first three; hr-assistant allows the first two plus finance-record-001.
  Thus the intersection permits only the candidate/CV pair and demonstrates each
  side independently limiting authority. Finance/Dev examples grant no hidden HR
  access. The exact parent require-delegation rule covers all three HR operations.
  Global tenant/class/model/domain rules still apply; metadata never widens them.
- Setup previews a bounded delta to the ACTIVE policy and CAS-activates it. Preserve
  semantic_required, semantic_mode, question set, feed, budgets and unrelated grants.
  Do not reuse the semantic-off core sample wholesale. If the current model/domain
  controls cannot support the preset, show incompatibility instead of broadening
  those controls. First installation and upgrade follow the same authority rules.
  The reviewed delta may add the dedicated hr-assistant role to document/mail role
  allowlists; retain all existing entries and reject conflicting preset identities.
  Activate its require-delegation rules before publishing any parent or scenario
  execution capability. Do not give the parent an unrelated broad role merely to
  pass global authorization. Partial setup remains inert and explicitly retryable.
- Bind summary input to an actual authorized source release: source action/resource,
  current child binding and policy snapshot. Re-read through normal enforcement
  after binding or relevant policy changes (always re-reading is acceptable).
  Keep CV content in the untrusted tool/data role. Never use raw fixture content,
  browser-supplied text or a stale released cache to bypass a failed fresh read.
- Add tests for two operator sessions attempting each other's handles, map capacity,
  restart and expiry, issuance rollback, exact direct-parent denial, stale setup CAS,
  retained semantic/feed/budgets, and source authority changing before summary.
