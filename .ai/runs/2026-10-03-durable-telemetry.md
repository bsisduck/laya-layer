# Durable telemetry delivery — E02-S02

Source doc: .ai/specs/full-stack-delivery.md
Issue: #12
Engine: om-auto-create-pr (steps: 5, --loop: no)
Base: origin/main at 33660d6; existing isolated Cezar worktree reused.

## Goal and scope

Deliver minimized tenant-scoped audit events to one authenticated local HTTP
contract collector with durable at-least-once progress, bounded pending batches,
exclusive sender ownership, visible backlog and measured performance.

Use the existing version-1 JSONL projection. A private sidecar retains one bounded
pending batch and a contiguous source cursor; source audit remains authoritative.
A failed or ambiguous acknowledgment cannot advance the cursor. Event IDs dedupe
collector replay. Fixed operator origin, secret-file credentials, no redirects or
client URLs, bounded parsing/timeouts and persisted exponential backoff.

Backpressure reports an operator threshold on retained source lag; it never drops
old evidence. This additive worker does not impose a gateway admission rule or
claim bounded retention for the existing audit database. Document the status hook
for root/control-plane integration and make this limit explicit.

## Non-goals and risks

No admin.py/UI ownership, model/tools implementation, real-model evaluation,
bank/external collector contact, vendor certification or merge. No new agents.
Source schema may lag PR6/17/19; remain additive and fail safely on unsupported
records, with the required root integration stated. Local filesystem and OS user
are trusted. Independent high-risk review remains a release requirement.

## Implementation plan

1. Implement versioned delivery contract, durable state, ownership, bounded
   transport/retries and focused failure tests.
2. Implement runnable loopback collector and CLI once/daemon/status commands.
3. Exercise live HTTP, zero/one rows, restart/crash/partial/duplicate cases and
   privacy; measure gateway overhead and source-to-collector delay.
4. Document contracts, root hook, operating limits and reproducible evidence.
5. Run full make validate and OM code review, fix findings, push ready PR and
   verify CI. Labels disabled; no merge.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Sender

- [ ] 1.1 Implement durable bounded sender and contract tests

### Phase 2: Collector and operator commands

- [ ] 2.1 Add contract collector and CLI lifecycle

### Phase 3: Evidence and handoff

- [ ] 3.1 Verify live HTTP recovery, privacy and measured performance
- [ ] 3.2 Document contracts and root integration
- [ ] 3.3 Complete validation, code review and ready PR
