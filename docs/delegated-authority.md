# Local delegated authority v1

This is a trusted operator-provisioned **local demo**, not corporate IAM, OIDC or
JWT exchange. Public clients cannot assert a human, department, tenant or agent.
JWT verification/exchange is a subsequent consumer. Department per-attempt resource
settlement/reporting is also subsequent: the audit attribution here is ready for
that consumer; aggregate budget accounts are not a department usage report.

`Identity` serialization remains unchanged. `principal_id` is the issuing agent's
immutable **accounting owner**. The human requester is separate trusted attribution.
Children copy the parent's exact Identity, tenant, agent, principal and root, so
fresh humans/children never reset principal-day or root budgets. Root grouping is
not proof of causal workflow parentage; no causal graph is claimed.

## Policy and provisioning

The optional `delegation` block defaults to legacy behavior. The opt-in
`config/delegated-policy.yaml` requires a delegated credential for the demo reader
and installed demo client across documents, memory, mail and model operations.
Its synthetic HR profile permits notes but excludes other same-tenant resources.
Do not turn it off to bypass HR checks. Agent roles still satisfy existing global
operation/class/domain/model rules. Delegation role profiles need not have the same
names as human roles: authority is the intersection of matching permissions.

Each role contributes bounded, operation-specific grants. A document/memory grant
pairs exact registered resource IDs with classes. Mail grants list domains; model
grants list aliases. A union preserves each pair; human AND agent AND both original
issuance grant sets must match. No wildcards, regex, dynamic policy code or empty-as-
unrestricted semantics. Maximum: 32 profiles, **64 aggregate grants**, 64 targets
per grant, four classes, 32 require rules and 32 human role IDs. Unknown roles grant
nothing. Memory predicates are parameterized SQL before any content search/read.
REST/MCP discovery and direct calls use the same authority. Global permissions
remain additional mandatory constraints.

Use the trusted local CLI with the gateway state directory, not an agent route:

```sh
agentgate --state-dir /private/demo provision-local-human --record-file /private/human.json
agentgate --state-dir /private/demo delegate-local --parent-token-file /private/demo/client.token \
  --subject employee-demo --output-token-file /private/child.token \
  --policy config/delegated-policy.yaml
```

The record file is bounded JSON, e.g. `{"subject_id":"employee-demo",
"tenant_id":"tenant-a","roles":["local-hr"],"department":"HR","revision":1}`.
Provenance is `local_demo` only. Initial provision refuses overwrite; a later record
requires `--expected-revision N` and revision N+1. Tenant/provenance are immutable.
Role, department, deadline or revocation changes invalidate every prior child by
subject revision. Set `revoked:true` with CAS to revoke the human. Parent/child
revocation uses `revoke-local-credential --token-file /private/demo/client.token`.
Tokens are generated internally, stored only in newly created 0600 files, and never
printed or accepted as command-line values. On a live installation issuance uses
active persisted controls inside the transaction, regardless of `--policy`.

Child creation and exact digest-keyed binding insertion are atomic. Maximum child
lifetime is **300 seconds**, further capped by the parent and optional assertion
deadline. Only a legacy parent can issue; no child-of-child delegation. Legacy
renewal rejects delegated credentials before writing a replacement. Parent renewal
revokes the old parent; children and approvals are never rebound. Provision a fresh
child for the new parent and propose a new exact approval.

## Dispatch, approvals and attribution

One resolver derives current authority independently of immutable Identity. Early
validation/discovery is followed by parent, child, human, revision, deadlines,
issuance ceiling and current grants revalidation **inside BEGIN IMMEDIATE**, with
active control-generation checks before document intent, memory intent/read,
model reservation and mail proposal/decision/resume/consume. The exact document
metadata, memory predicate, model alias or recipient domain is authorized.

A committed durable intent/reservation defines the revocation boundary. Subsequent
revocation cannot recall an already dispatched provider call or un-read an allowed
read. Output inspection and accounting still apply. Pre-intent races fail closed;
audit/store failures roll back partial state and prevent protected dispatch.

Delegated mail fingerprints add an authority-v1 binding containing the exact parent,
child, human revision/provenance/department, issuance policy/ceiling, expiry,
current relational grants and recipient-domain metadata, alongside the unchanged
payload/credential/root/policy/registry fingerprint. An immutable `action_authority`
sidecar retains that binding and attribution. Consent is checked at proposal,
operator decision and resume; any grant/policy change requires a new action/key.
Approval alone never delivers, and cannot override a hard denial. The local outbox
insert, audit, consumption and budget settlement remain one transaction. Consumed
replay returns the same acknowledgement without a new effect or spend.

AuditEvent adds nullable versioned `authority` and `approval_actor` extensions.
Authority records accounting principal, human subject, agent, delegation digest,
local-demo provenance, revision and trusted department. Approval actor records
`actor_id` plus `credential`, `local_console` or `trusted_local_hook` mode; none
claims a verified corporate person. Admin decisions use the trusted
server-owned `local_console` route setting to select credential or local-console
mode. Console sessions come from independently merged PR42; this authority core
only records their mode. Supplied public hooks retain the original explicit signature. Approvals UI labels
human requester and accounting owner separately. No raw tokens/groups/JWTs are
stored. Export-v1 keys remain unchanged and deliberately omit these extensions.

## Migration and rollback

Stop the gateway and back up the entire private installation/database before
`agentgate migrate` (the product installer already retains a stopped SQLite backup).
Schema-2 receives additive `credentials.authority_kind` (legacy default),
`authority_schema` v1, `human_subjects`, `delegated_bindings`, and `action_authority`.
Identity, tool_actions and their immutable snapshots are not rewritten. Existing
pending and consumed actions retain their original fingerprint bytes; the omitted
delegation field stays absent from legacy policy digest serialization. The frozen
`tests/fixtures/authority-legacy-v0.json` was generated by **unmodified e4a5929** and
checks migration/restart/resume using its old pending/consumed rows. The core-only
case explicitly retains its old registry digest; the integrated catalog case
requires reproposal for pending consent after the independent registry upgrade,
while consumed acknowledgements remain stable.

Missing authority tables or missing delegated bindings fail readiness; corrupt
bindings fail credential resolution. Keep old binaries stopped: they do not know
how to constrain delegated credentials. Roll back only by stopping the new binary
and restoring the matching pre-migration backup plus old binary; never downgrade
an authority-bearing live database or copy child credentials into legacy state.
Backups omit later audit, consent, outbox and budget changes; reconcile deliberately.

## Evidence scope

`tests/test_authority.py` covers unit grant/schema bounds, functional isolation and
public override rejection, and actual REST/official-SDK MCP/model/SQLite lifecycle,
revision/expiry/revocation, ceiling expansion/narrowing, live-control races,
pre-intent revocation, audit rollback, legacy renewal/migration/replay and unchanged
principal/root accounting. Model providers in pytest are declared deterministic
fixtures, not real-model evaluation. Installed browser E2E uses the rebuilt wheel,
server-issued local-demo records/bindings and real operator exact consent/outbox.
No heavyweight inference is required or claimed. Independent root high-risk review,
gate/QA and green CI are required before any merge; delivery is draft only.

To reproduce the owned installed flow from a prepared checkout:

```sh
uv run --locked --extra mcp --with playwright python tests/frontend/authority_flow.py
uv run --locked --extra mcp --with playwright python tests/frontend/authority_flow.py --local-console
```

It rebuilds the wheel through the repository QA helper and always tears down its
own installation in `finally`. The screenshot, result JSON and private credential
files remain under ignored `.ai/qa/artifacts_authority/`; do not publish that directory.
