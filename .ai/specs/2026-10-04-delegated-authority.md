# Transactionally bound human and agent authority

This implements the local authority core of the expanded user request, after
independent design review87777afc. JWT issuer exchange is a separate consumer of
this core. Tool catalog and login-free console are independent active tasks; do
not duplicate them. Read this entire contract and relevant existing transactions.

## Verified compatibility baseline

Existing Identity serialization is embedded in immutable tool_actions and their
fingerprints. Do NOT add default/null fields to Identity or rewrite its serialization.
Keep legacy stored actions, consumed acknowledgments, credentials and accounting
semantics working. New delegated binding belongs in an additive versioned sidecar,
keyed by exact credential digest, not user-selected request headers. No arbitrary
on-behalf-of fields at REST/MCP/model boundaries. Public ActionResponse shape stays.

Existing principal_id remains the immutable ACCOUNTING principal of the issuing
agent credential; root and tenant remain unchanged. Human requester is separate
trusted attribution, never silently substituted into the budget account. This
prevents fresh employee assertions from creating fresh principal-day budgets.
Document the distinction explicitly; the UI must name the actual human requester
from attribution and the accounting owner separately.

## Persisted trusted authority

Add bounded versioned tables for:
- human subjects: stable subject ID, trusted provenance kind (`local_demo` initially;
  future verified issuer+subject), tenant, approved role IDs, department, revision,
  revocation and optional assertion deadline. No raw token or personal document.
- exact child binding: child credential digest, exact parent digest, subject ID,
  subject revision, issuance policy/trust version, immutable issuance grant ceiling,
  assertion deadline, expiry and binding digest/version. One hop only. Child
  creation and binding insertion are atomic. Missing/corrupt sidecar fails closed.

Provide a trusted local CLI/in-process provisioning command for these records,
explicitly labelled local demo / operator provisioned, not IAM/OIDC verified.
Secrets go only to newly created private 0600 files, never stdout/arguments/logs.
Retain source subject and parent revocation paths. Provisioning an existing subject
must be explicit CAS update or refuse overwrite; department/provenance comes from
trusted configuration, not agent request data. A missing table in a delegated
installation must fail readiness, not silently serve children as legacy credentials.

A child can never outlive its parent or assertion and has a short maximum lifetime
(e.g.300seconds; choose and document exact value). No delegation from another child.
Reject a delegated token in existing legacy renewal helpers, before persisting a
replacement file/token. Fresh exchange/provisioning is required. Parent renewal
revokes old parent and thereby immediately invalidates its children; do not transfer
approvals or silently rebind them to the replacement parent.

## Relational grants and intersection

Optional policy delegation block preserves all legacy defaults. An explicit
require-delegation rule covers the selected tenant/agent/operations, so omitting
child attribution cannot bypass the shipped HR profile. Unknown roles and empty
mappings grant nothing.

Resolve each side's role profiles to OPERATION-SCOPED relational grants:
- documents.read: allowed server-registered resource IDs AND confidentiality classes;
- memory.query: allowed server-owned entry IDs/namespaces AND classes;
- mail.send: allowed recipient domains and existing exact input/approval rules;
- chat.completions: permitted model aliases.

Unions within human roles and within agent roles must preserve each grant's resource
and class relationship. Do not flatten independent resource/class sets into an
unintended Cartesian product. Effective predicate is (any human grant matches) AND
(any agent grant matches) AND issuance ceiling AND parent operations/roles AND
current global policy/tenant constraints. Explicit bounded wildcard authority may
be supported only if administrator-owned; empty never means unrestricted. Prefer
finite supported-operation rules over a generic policy language. Bound grant/profile
counts and validation; no dynamic eval/regex/code in policy.

Apply intersection to discovery and actual calls in REST/MCP/model/direct clients,
including undiscovered direct calls. Check document metadata before executor read;
filter memory in SQL before reading content. Same-tenant HR-versus-Finance isolation
is required, not merely tenant separation. A role change or policy expansion never
widens a child beyond its issuance ceiling; narrowing/revocation takes effect now.

## One resolver and dispatch boundary

Implement one trusted authority resolver used by all boundaries. It distinguishes
immutable stored Identity from derived current effective grants. Resolve for early
validation/discovery, then revalidate parent+child+human record, deadlines/revocation,
revision, issuance ceiling, current grants and active control generation INSIDE each
existing BEGIN IMMEDIATE transaction before reservation/intent/effect. Required call
sites: document Store.reserve_dispatch, scoped-tool reservation/read and mail
approval decision/resume/consume, and ModelLedger.reserve. Ensure the same exact
resource/model/recipient being dispatched was authorized.

Define committed durable dispatch intent/reservation as the revocation boundary:
a later revocation cannot recall a provider call already dispatched or un-read a
performed read; output inspection and accounting still apply. Tests should pause
BEFORE transaction revalidation and revoke/change authority, then assert zero effect.
Do not claim cancellation of work after committed dispatch. Audit/store failures
must fail closed before protected work; all partial writes roll back.

## Approval and audit

New delegated approval fingerprint includes a VERSIONED authority binding (human,
agent/parent, subject revision, issuance ceiling, current scoped grants, metadata,
policy/registry and expiry) in addition to exact existing payload/credential/root
binding. Legacy actions keep byte-compatible ownership/fingerprint serialization.
Current grants are rechecked on proposal, human decision and resume; a changed
human/agent authority invalidates prior consent, even if action payload is unchanged.
Approval never executes implicitly and cannot override denial. Preserve exact one
local outbox effect, replay and mutated-idempotency-key conflict behavior.

Add optional versioned audit attribution without changing export-v1 keys or old
AuditEvent readability: accounting principal, human subject, agent, delegation ID /
provenance, subject revision and trusted department. Avoid raw JWT/groups/tokens.
If adding workflow linkage, accept it only from server-owned bounded workflow
records; root_run_id groups work but is NOT proof of causal parentage. Do not invent
causal graphs. Approval attribution must distinguish current credential-mode local
operator and explicit local-console mode; neither is a verified corporate person.
Record a separate approval actor/mode in real decision audit, never claim requester's
identity is the approver. Stable nullable extensions need documented compatibility.

Department reporting is NOT solved by joining aggregate budget accounts to labels.
If implementing it in this increment, persist trusted department/provenance when
reserving each model attempt and exact actual token/cost/call values when settling,
in the SAME transactions. Count each action once; unknown/uncertain usage and reserved
bounds remain separate. Old unattributed records are unassigned. Simulated tariffs
remain simulated, never invoices. Otherwise expose attribution now and leave the
actual resource-view consumer to the following HR/evidence task, explicitly noted.

## Required tests and completion

Tests at unit, functional, integration and installed E2E layers are explicitly
requested. Include asymmetric broad-agent/narrow-human and inverse; same-tenant
forbidden records; per-grant class/resource correlation; no public override;
model alias denial; discovery/direct-call parity; parent/child/human expiry and
revocation; narrowed and expanded policy vs issuance ceiling; race before dispatch;
child-of-child rejection; legacy and delegated renewal; old pending/consumed action
compatibility after migration/restart; changed delegation invalidates approval;
replay exactly one effect; rollback under audit/store failure; shared root AND
principal accounting across newly minted children. Actual REST/MCP/model adapters
and SQLite transactions, with zero forbidden executor/provider/outbox effects.

Installed owned QA must exercise a real server-issued local binding through gateway
and browser/operator exact approval flow. Do not substitute a mocked endpoint or
claim fixture tokens are corporate IAM. No need heavy inference. Run make validate
and relevant JS; use private worktree QA with rebuilt wheel and teardown finally.
One focused issue/branch/draft PR after overlap check; frequent working commits,
Open Mercato skills, root independent high-risk review/gate/QA and green CI before
merge. No primary state/shared Ollama modifications by author. No generated logs,
secrets, runtime files or reports committed. Include migration/rollback docs.
