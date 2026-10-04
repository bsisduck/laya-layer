# Local delegated authority core

Source doc: .ai/specs/2026-10-04-delegated-authority.md

Implement trusted local-demo human/child bindings and relational grants at existing transactional dispatch boundaries, preserving legacy identity/consent/accounting. User authorizes issue and validated draft PR; no merge. JWT exchange, catalog, console mode and department settlement/report consumer are excluded. Child lifetime maximum: 300 seconds. Committed durable dispatch is the revocation boundary.

## Implementation Plan

1. Persist bounded local human records, exact one-hop bindings, immutable ceiling, migration/readiness and private provisioning.
2. Connect one resolver to REST/MCP/model discovery and dispatch; SQL-filter relational memory grants.
3. Bind delegated approvals and trusted audit/UI attribution; preserve legacy serialization and renewal.
4. Exercise unit/functional/integration invariants against actual adapters/storage/lifecycle.
5. Rebuild installed wheel and verify browser exact approval with private server-issued child, retaining ignored evidence and tearing down owned QA.
6. Review diff, run make validate/JS gate, publish draft PR with exact evidence and limits; root independent review remains required.

## Progress

- [x] 1. Persist trusted authority and provisioning
- [x] 2. Enforce relational authority before protected dispatch
- [x] 3. Preserve and bind consent, audit and renewal
- [x] 4. Verify unit, functional and integration invariants
- [x] 5. Verify rebuilt installed browser E2E and teardown
- [ ] 6. Validate, review and publish draft

## Validation checkpoint

Source head dd5f6bf0621ee5464aa8cd800877ae7fa708fb15 on catalog main 13d4cc6:
`make validate` passed 769 tests plus lint, formatting, strict typing and packaging;
JS contracts passed 9/9. Installed rebuilt-wheel browser exact approval passed,
with one local outbox effect, no forbidden provider attempt and owned QA stopped
in `finally`. Authority suite: 6 unit, 10 functional, 37 integration cases. Evidence
is retained locally in ignored `.ai/qa/artifacts_authority/`. No real inference.

Independent console PR42 still uses its trusted route flag (no session mode).
On integration, owned `ScopedTools.decide` must receive `actor_mode=local_console`
for that flag; supplied public adapters retain their old explicit signature. This
branch provides the attribution contract and does not implement console sessions.

## Publication hold

User explicitly paused first push/PR until merged local-console main is supplied.
Authority remains unpublished. Local checkpoint 86ad7dc0102b99aa8c52222a85549321e78e69b4
passed `make validate` with the retained pinned Hermes source: **778 tests**, no
skips, all lint/type/build checks. Added accepted-max 64-grant issuance/reopen/SQL
query and real decision-audit actor-mode regressions; authority now has 6 unit,
10 functional and 46 integration cases; combined authority/admin gate passed 123.

After supplied base arrives: rebase, wire owned actor mode from console's trusted
route flag, preserve explicit supplied adapters, then repeat final full/JS gates
and installed browser QA before draft publication and exact-head CI monitoring.
