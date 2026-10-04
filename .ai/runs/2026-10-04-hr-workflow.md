# HR workflow implementation

Source doc: .ai/specs/2026-10-04-hr-workflow.md

Implement the primary synthetic HR flow using accepted local-v1 authority, normal core enforcement, exact approvals and local outbox. Base ea23c8d; publication held for root integration base. No JWT, reporting/deck, adapters, Cezar changes or heavy inference. Root owns independent review and integration.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append commit SHA when a step lands.

### Phase 1: Contract and facade

- [ ] 1.1 Preserve complete authoritative spec and tracker scope
- [ ] 1.2 Add reviewed active-policy delta, fixed provisioning and deliberate renewal
- [ ] 1.3 Add bounded session-bound child handles and enforced reads/summary/proposal/resume
- [ ] 1.4 Verify rollback, lifecycle, denial effects and local-v1 compatibility

### Phase 2: Product and evidence

- [ ] 2.1 Make HR primary in existing accessible console and preserve playground
- [ ] 2.2 Run frontend contracts and owned installed browser E2E with DB evidence
- [ ] 2.3 Run configured gate, review, document limits and report ready local head
- [ ] 2.4 Rebase to root final base and publish one draft PR only after release of hold
