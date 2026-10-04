# Local delegated authority core

Source doc: .ai/specs/2026-10-04-delegated-authority.md
Issue: https://github.com/bsisduck/laya-sec-agent/issues/40
Draft PR: https://github.com/bsisduck/laya-sec-agent/pull/43

Trusted local-demo human/child bindings and relational grants are enforced at the
existing transactional dispatch boundaries. Immutable Identity, prior consent and
accounting semantics are preserved. Child lifetime maximum is 300 seconds;
committed durable dispatch defines the revocation boundary. JWT exchange and
per-attempt department usage settlement/reporting remain subsequent consumers.

## Implementation Plan

1. Persist bounded local human records, exact one-hop binding/ceiling, additive migration/readiness and private provisioning.
2. Connect one resolver to REST/MCP/model discovery and transaction-bound protected dispatch; SQL-filter relational memory grants before content.
3. Bind delegated consent and trusted human/approval attribution; preserve legacy serialization, accounting and renewal contracts.
4. Verify actual adapters/storage/lifecycle, zero forbidden effects, races, rollback, migration/restart, replay and budgets.
5. Rebuild installed wheels and verify credential/local-console browser exact approval; retain ignored evidence and stop owned QA in finally.
6. Review, validate and deliver one draft PR. Root independently reviews/runs gate and QA before merge; no author merge.

## Progress

- [x] 1. Persist trusted authority and provisioning
- [x] 2. Enforce relational authority before protected dispatch
- [x] 3. Preserve and bind consent, audit and renewal
- [x] 4. Verify unit, functional and integration invariants
- [x] 5. Verify rebuilt installed browser E2Es and teardown
- [x] 6. Validate, review and publish draft #43

## Validation and integration

Rebased unpublished work onto merged catalog/console main
4e1743340ce71ef976f093479d1decfc49d81695. Owned admin decisions select actor_mode
from the actual trusted local_console closure; supplied explicit OperatorTools
hooks retain the original signature. Console/catalog implementations remain in
those independent PRs. Actor text accepts email/spaces without deriving permission.

Runtime core 5224485427c069e1cdef10254211d66362eb1401 passed make validate with the
retained pinned Hermes source: **855 tests, no skips**, lint/format, strict mypy,
source and wheel builds. Authority cases: **6 unit, 10 functional, 50 integration**;
focused authority/admin/catalog/console tests **222/222**; JS contracts **13/13**.
Frozen unmodified e4a5929 pending/consumed snapshots verify core compatibility;
the independent catalog registry upgrade intentionally requires pending reproposal.
Accepted maximum 64-grant issuance/reopen/query and all trusted actor modes pass.

Installed credential and local-console E2Es both imported rebuilt site-packages,
provisioned real private local bindings, verified exact operator approval, correct
mode and separate human/accounting attribution, one fixture outbox effect each,
replay/mutation/revocation and model denial with no provider attempt. Own QA51829
stopped in finally and policy restored. Primary8080/state, shared Ollama and other
QA were preserved. No inference or semantic evaluation ran. Evidence is retained
under ignored .ai/qa/artifacts_authority/{credential,local-console}/ plus integrated
logs; reproduction and migration/rollback are in docs/delegated-authority.md.

Public exact-head CI results and final delivery head are recorded on draft #43.
Independent root high-risk review/gate/QA remains required before any merge.
