# E01-S03 scoped tools, exact approvals and MCP

Source doc: .ai/specs/full-stack-delivery.md
Issue: #10
Engine: om-auto-create-pr (steps: 6, --loop: no)

## Goal and scope
Deliver tenant-scoped memory queries, exact one-use mail approval with a transactional
local outbox, and official-SDK MCP access through the same authority as REST.
Fix tool root accounting to tenant+root while preserving historical spend and reservations.

## Non-goals and integration
No real email, arbitrary remote tools, operator authentication/frontend, model facade,
real Laya/Ollama evaluation, subagents or merge. PR17 owns operator controls and PR6
owns models. Expose additive callable approval/list/outbox hooks and document final
integration with their policy snapshots/feed hooks. Labels stay disabled.

## Implementation Plan
### Phase 1: Durable authority
1.1 Preserve legacy root spend while sharing tenant/root counters across principals.
1.2 Implement strict tools, immutable approvals, idempotency and atomic local outbox.
### Phase 2: Adapters and verification
2.1 Add REST retrieve/resume and operator callable hooks with contract docs.
2.2 Add authenticated official-SDK MCP with filtered discovery and bound sessions.
2.3 Exercise denied side effects, races, restarts, mutation, expiry and MCP wire flows.
2.4 Run make validate, author om-code-review, publish evidence and ready PR.

## Risks and decisions
Approval payloads are restricted local state, never audit previews. All dispatch
checks run again under the SQLite write transaction; mail effect, outcome and
consumption commit together. No exactly-once claim for arbitrary external systems.
Existing root counters are migrated transactionally with all spend and unresolved
reservations retained. High-risk independent review remains required before release.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Durable authority
- [x] 1.1 Preserve legacy root spend while sharing tenant/root counters across principals.
- [ ] 1.2 Implement strict tools, immutable approvals, idempotency and atomic local outbox.

### Phase 2: Adapters and verification
- [ ] 2.1 Add REST retrieve/resume and operator callable hooks with contract docs.
- [ ] 2.2 Add authenticated official-SDK MCP with filtered discovery and bound sessions.
- [ ] 2.3 Exercise denied side effects, races, restarts, mutation, expiry and MCP wire flows.
- [ ] 2.4 Run make validate, author om-code-review, publish evidence and ready PR.
