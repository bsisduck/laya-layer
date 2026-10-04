# Local HR workspace (hr-local-v1)

The main console flow is synthetic HR. Automatic local-console operator sessions
remain a trusted-computer mode, not corporate IAM or four-eyes verification.
Ordinary credential mode and Playground remain available. No ranking, hiring
choice, SMTP, merge or payment adapter is implemented.

The authenticated `/admin/hr` facade delegates to the normal ActionService,
ModelService and exact-action approval implementation. It never executes fixture
resources itself. All writes inherit operator Origin, cookie and CSRF checks.
Reads/preview/page visits do not issue credentials or activate controls.

`GET /admin/hr/setup-preview` computes a bounded delta from active controls;
`POST /admin/hr/setup` accepts only its generation and digest. The delta preserves
semantic settings, worker question configuration, feed, all budgets/counters and
unrelated grants. Only dedicated document/mail role allowlists, reviewed relational
grants and the exact require-delegation rule are added. Incompatible domain/class
controls or conflicting/revoked records require operator reconciliation. No model
provider is enabled by setup. Activation precedes fixed parent/person provisioning;
a failed second transaction leaves HR inert and explicitly retryable.

The parent is fixed to tenant-a / hr-demo-account / hr-assistant / hr-demo-run,
role hr-assistant and documents.read/mail.send/chat.completions. Parent secrets are
derived privately from the audit key and a dedicated durable epoch. Only explicit
expired-parent renewal advances that epoch, retaining accounting identity. The
local-demo employee is hr-local-employee, HR-BP, department HR. Setup cannot revive
or overwrite a conflicting/revoked employee or parent.

Human document grants include candidate, CV and private HR notes; agent grants
include candidate, CV and Finance record. Their intersection is candidate/CV only.
All four additive resources are internal server-owned synthetic records. Global
policy, model/domain controls, semantic inspection and budgets remain mandatory.
Dev and Finance profiles have empty grants; their catalog adapters remain proposals.

`POST /admin/hr/bind` deliberately issues a core local-v1 child for at most 300s.
A random handle selects a process-private secret bound to the current operator
session, parent digest/epoch and subject revision. At most 16 unexpired children
and 16 proposals per binding are accepted. Expired child rows are removed only
on deliberate binding, while durable approvals/audit remain. Session loss, restart,
expiry and parent/subject changes cannot reconstruct a child or transfer proposals.
`POST /end` deliberately revokes the child; new proposals need fresh keys.
The browser receives no child/parent bearer, uses no browser storage and never
replays a mutation on session recovery. Handles alone are not authority.

`POST /read` and `/summary` accept only a handle and one registered HR resource.
Every summary performs a fresh authorized inspected release, then supplies its
content in the correlated untrusted tool role to an actual configured provider.
The source controls, child binding and read authority are checked on every model
admission and inside the reservation transaction; control changes stop the request
without provider dispatch or retry of stale data. Unavailable, denied or malformed
provider/semantic results produce actual failures, never substitute summaries.
CV injection outcomes come from the active inspection pipeline, not scenario IDs.
No semantic worker can legitimately yield an injection-protection claim from a fixture.

`POST /propose` accepts bounded recipient/subject/body and a proposal key. The
binding namespaces that key; changing a payload with the same key conflicts.
Consent is still the core immutable snapshot/fingerprint. Existing `/admin/approvals`
shows exact payload, requester/accounting identity, expiry and approver separately.
Approval has zero outbox effect; `/admin/hr/resume` accepts only the binding's own
stored action ID, revalidates core authority and writes one local outbox row.
Replay retains one row. A new binding cannot resume an earlier binding's action.

New routes/table (`hr_parent`) are additive; local HumanSubject/DelegatedBinding v1
serialization, REST/MCP/action/export schemas and existing accounting keys remain
unchanged. Stop serving before code rollback; back up the complete private state.
Rollback retains the additive table, durable approvals/audit and tightened active
policy; it does not restore revoked credentials or replay actions. Reconcile the
HR policy deliberately if removing the workspace. Never run mixed gateway code
against one authoritative SQLite state.

Deterministic provider/semantic fixtures prove control behavior and effects only.
Real semantic/provider smoke belongs to coordinated post-integration observation;
retain false positives and frozen poor measurements. See the full standalone spec
in `.ai/specs/2026-10-04-hr-workflow.md` for the authoritative acceptance contract.

Executable deterministic checks: `uv run --extra mcp pytest tests/test_hr_workflow.py`
and `node --test tests/frontend/contracts.mjs`. Installed browser evidence:
`python3 tests/frontend/hr_flow.py` (the existing separate Playwright tooling is
required). This script installs this checkout into its owned QA state, checks the
real product startup and DB effects, stops that supervisor, then invokes the same
installed CLI/wheel against a labelled HTTP provider fixture. It restores active
policy at a newer revision and stops its processes in finally. Each run preserves
the checkout's prior stopped QA data, uses fresh private test data, retains the
test's audit/effect state privately, then restores the prior QA data. Product
budgets and live counters are never reset for a rerun. No shared generation or
semantic workers are invoked. Generated evidence stays ignored.
