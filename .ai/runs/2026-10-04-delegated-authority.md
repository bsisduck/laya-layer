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

- [ ] 1. Persist trusted authority and provisioning
- [ ] 2. Enforce relational authority before protected dispatch
- [ ] 3. Preserve and bind consent, audit and renewal
- [ ] 4. Verify unit, functional and integration invariants
- [ ] 5. Verify rebuilt installed browser E2E and teardown
- [ ] 6. Validate, review and publish draft
