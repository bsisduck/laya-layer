# Explicit operator credential renewal

Source doc: .ai/specs/full-stack-delivery.md
Status: complete

## Goal and scope

Let an operator explicitly renew expired agent/playground authority without
resetting spend, reviving revoked credentials, or carrying old approval authority
into a new credential. This follow-on coordinates with installer PR22 and model
PR6; it does not edit either branch, add UI, merge, or run inference.

## Implementation plan

1. Freeze trusted renewal and secret-free operator API contracts; publish draft.
2. Implement atomic replacement/epoch state and bounded operator routes; test
   expiry, revocation, replay, concurrency, scope/budget retention and no secret
   release. Keep existing playground epoch zero derivation compatible.
3. Run full validation and author review; publish exact evidence and ready PR.

## Risks

Renewal must never issue stronger authority or reset tenant/root accounting.
Approval records remain bound to the previous digest; a new credential starts a
new proposal. The installer owns durable private-file replacement/recovery for
agent tokens; this module never returns an agent token to a browser.

## Progress

PR: #24

### Phase 1: Contract

- [x] 1.1 Freeze and publish renewal contract

### Phase 2: Implementation

- [x] 2.1 Implement atomic credential replacement and operator routes
- [x] 2.2 Exercise authorization, concurrency, restart and accounting boundaries

### Phase 3: Evidence

- [x] 3.1 Validate, review and publish ready PR

## Validation and author review

`make validate` PASS: 334 tests, Ruff lint/format, strict mypy (21 files), source
and wheel. 133 focused renewal/admin/model tests passed before commit. Four
additional isolated approval/executor cases passed against exact PR19 4d08fe6
plus this helper; zero old-authority outbox effects and one newly approved effect.
Model PR6 additions retained; no tools/model implementation edits. The published
plan branch integrated newer main normally to retain shared history, not force-push.

Author review (`om-code-review`): no unresolved blocker/major. Additive schema and
re-exported playground helper preserve epoch-zero and public contracts; explicit
replacement locks/validates/retires/issues/audits together, never mutates budgets.
Installer private-file publication/recovery is outside the database helper's
transaction. Independent review is still required before release under SDLC.md;
author review is not an independent or human/GitHub approval. No UI, heavy
inference, labels, other agents, PR merge or model branch edits by this task.
