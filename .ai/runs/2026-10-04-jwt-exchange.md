# Pinned person-token exchange

Source doc: .ai/specs/2026-10-04-jwt-exchange.md

Goal: exchange a configured issuer person access token for a short-lived child of an existing permitted agent credential, using the shared persisted resolver.

Scope: versioned issuer records, bounded pinned RS256 trust/CAS, exact parent/client/tenant mappings, atomic refresh/admission/issuance/audit, additive HTTP and private CLI, generated-key tests and installed adapter QA. Preserve local v1 bytes and consent, accounting and old approvals.

Risks: authority and trust races, assertion ordering, rollback, bounded growth and unchanged refresh consent. Root independently reviews high-risk changes. First push/draft PR held until root supplies final integration base; no author merge. No department views, HR, deck or real model inference.

## Implementation Plan

1. Establish versioned records/shared decoders and trust generation contract.
2. Implement verification, atomic exchange, HTTP/CLI and limits.
3. Prove unit/functional/wire/concurrency/rollback/compatibility behavior.
4. Run installed owned adapter QA and full gate; review and report ready head.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Contracts and implementation

- [ ] 1.1 Establish shared issuer contracts without changing local v1 bytes
- [ ] 1.2 Implement bounded pinned verification and atomic exchange

### Phase 2: Evidence and handoff

- [ ] 2.1 Verify generated-key behavior, concurrency, rollback and compatibility
- [ ] 2.2 Verify installed adapters, full gate and code review
- [ ] 2.3 Report ready local head and await final integration base before publication
