# HR workflow implementation

Source doc: .ai/specs/2026-10-04-hr-workflow.md

Implement the primary synthetic HR flow using accepted local-v1 authority, normal core enforcement, exact approvals and local outbox. Final runtime base e015e66; root released the first-push hold. No JWT, reporting/deck, adapters, Cezar changes or heavy inference. Root owns independent review and integration.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append commit SHA when a step lands.

### Phase 1: Contract and facade

- [x] 1.1 Preserve complete authoritative spec and tracker scope
- [x] 1.2 Add reviewed active-policy delta, fixed provisioning and deliberate renewal
- [x] 1.3 Add bounded session-bound child handles and enforced reads/summary/proposal/resume
- [x] 1.4 Verify rollback, lifecycle, denial effects and local-v1 compatibility

### Phase 2: Product and evidence

- [x] 2.1 Make HR primary in existing accessible console and preserve playground
- [x] 2.2 Run frontend contracts and owned installed browser E2E with DB evidence
- [x] 2.3 Run configured gate, review, document limits and report ready local head
- [x] 2.4 Rebase to root final base and prepare the verified draft delivery

## Final integrated verification

Runtime head 34bf344 is based on accepted issuer/department main e015e66.
make validate passed 1,005 tests, strict mypy, lint/format and wheel/sdist;
18 Node contracts passed. Installed HR E2E proved actual authorized reads, both
scope denials, approval with zero outbox rows, exact resume/replay with one row,
session/restart/expiry boundaries, in-flight expiry/ended controls, keyboard/mobile,
and active-policy rollback with owned teardown. Its labelled HTTP provider fixture
recorded two HR-attributed attempts, one known settlement and the accepted usage
view link. No real inference was run.

Installed browser components passed with explicit overview and mocked APIs (UI
consumer evidence only). Installed local-console checks passed with initial HR
landing/protected-state equality, ordinary reads/mail/recovery and official-SDK
MCP denial. Root independently rebuilt and passed installed HR E2E at 34bf344;
root owns final release review/gate and coordinated real standard-v2 smoke.
The implementation remains local-v1 and retains issuer-v2 parsers and department
transactional attribution/settlement. Broad final product documentation is owned
separately; this task retains docs/hr-workflow.md as its local contract.

## Author review (independent release review still required)

No remaining blocker/major found in the HR diff from e015e66. Reviewed the repo
CODE_REVIEW/BACKWARD_COMPATIBILITY contracts and Open Mercato checklist. New facade
inputs are finite/bounded and inherit session/Origin/CSRF checks. Core execution,
authorization, consent and budgets own protected effects; the UI retains only a
session-bound handle. Source guards cover every model admission and reservation,
and policy changes cannot retry stale released data. The retained dispatch_event
callback refreshes department attribution after both transactional source and chat
authority checks. End expiry fails explicitly and rolls back its mutation.

Local HumanSubject/DelegatedBinding v1 bytes remain untouched. New facade/table and
trusted optional method arguments are additive; legacy fixtures retain their order.
Rollback/lifecycle failures have denied-effect evidence. Shared shell consumers
retain overview coverage while the real landing test asserts no hidden setup/bind.
The changed web assets add 15,781 raw / 5,085 gzip bytes, with no new JS/runtime
dependency; no server-rendered surface was changed. Coordinated real inference, independent root final release review/gate and
remote CI remain separate from this author verification.

| Check | Result | Evidence scope |
| --- | --- | --- |
| make validate (pinned Hermes source) | PASS | 1,005 tests, strict mypy, lint/format, lock/workflow and package build |
| Node frontend contracts | PASS | 18 contracts, including HR state and department consumers |
| Installed browser components | PASS | Mocked APIs; loading/errors/XSS/mobile and ordinary draft/approval UI only |
| Installed local-console checks | PASS | HR startup protected-state equality; actual ordinary scope/outbox/recovery/MCP effects |
| Installed HR E2E | PASS | Real core protected effects/rollback; labelled HTTP provider fixture, no inference |
