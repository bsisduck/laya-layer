# Explicit operator credential renewal

Source doc: .ai/specs/full-stack-delivery.md
Status: in-progress

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
- [ ] 2.2 Exercise authorization, concurrency, restart and accounting boundaries

### Phase 3: Evidence

- [ ] 3.1 Validate, review and publish ready PR
