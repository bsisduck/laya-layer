# Restricted agent clients (E03-S02)

Source doc: .ai/specs/full-stack-delivery.md
Issue: #14
Status: complete

## Goal

Run a genuine direct agent and pinned upstream NousResearch Hermes through the
existing gateway model and discovered scoped tools with bounded, correlated
model → tool → model cycles and reproducible effect/audit evidence.

## Scope

New isolated client modules, CLI entry points, private Hermes runtime preparation,
HTTP integration tests, reproducible smoke commands and source/version evidence.
Start from origin/main 094a4a8; consume PR19 contracts, then integrate fresh main
once root lands them. No duplicate gateway authority, credential issuance,
automatic renewal, spend reset, extra agents, merge, cloud/bank APIs or OS sandbox
claim. Agent subprocesses receive only their existing scoped gateway credential.
No operator or private upstream key is passed to either client.

## Implementation Plan

### Phase 1: Direct client

1.1 Implement discovery, strict bounded Chat Completions cycles, correlated REST/MCP
calls, explicit pending resume, sanitized failures and no automatic retry.
1.2 Test real HTTP success/denial/approval, identity/budget/output boundaries and
restart behavior against the integrated gateway contracts.

### Phase 2: Genuine restricted Hermes

2.1 Inspect and pin upstream source/runtime; implement private-home launcher using
upstream agent and MCP registry, with builtins, fallback/auxiliary models, memory
and delegation disabled; verify actual tool list and fail closed on mismatch.
2.2 Test profile isolation, active tool registry, failure/pending behavior and
compatibility with real upstream Hermes in its isolated environment.

### Phase 3: Evidence and delivery

3.1 After semantic evaluation completes, run actual local-model direct and Hermes
cycles sequentially; record minimized hashes/versions, trace/root/audit/effects,
fixture measurements and explicit limitations; publish user/demo documentation.
3.2 Run full make validate, OM author review/fixes, publish evidence and ready PR.
Independent high-risk release review remains maintainer-owned; no merge.

## Risks

Hermes may emit model fields unsupported by the strict gateway, use automatic
retries, or load native/auxiliary tools by default. Verify pinned source and
intercept only compatibility/restriction boundaries; never replace its agent loop
with a wrapper claiming to be Hermes. Native same-user file/network access remains
outside this profile's controls. No inference overlap with semantic evaluation.
Labels disabled. CLI/API task, no web UI changed.

## Progress

PR: #30

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Direct client

- [x] 1.1 Implement direct discovery and bounded correlated cycles — 016f159
- [x] 1.2 Test HTTP enforcement and pending resume — 06f8753

### Phase 2: Genuine restricted Hermes

- [x] 2.1 Pin upstream and implement restricted launcher — 724bc5b
- [x] 2.2 Test actual Hermes profile and registry — 724bc5b

### Phase 3: Evidence and delivery

- [x] 3.1 Run real local cycles and document evidence — f07add0
- [x] 3.2 Full validation, author review and ready PR — final evidence/review commit

## Final evidence

Integrated main4a1fe3d (including tools, renewal, telemetry, installer and explicit
semantic v2). No root lifecycle/UI/QA scripts changed. Real final code f07add0:
direct REST/MCP and genuine pinned Hermes each completed two model calls and one
scoped document read, exact call IDs and one server-owned root; semantic inspection
disabled. Five failed Hermes development proposals retained with zero effect.
Source/report hashes, cumulative17calls/5699tokens/6reads and commands are in
docs/restricted-agents.md. No renewal/reset or raw upstream credential in clients.

Final make validate:574 passed,10 explicit optional Hermes skips; Ruff,strict mypy
and source/wheel builds pass. Prepared upstream client suite:55 passed,including
all10 genuine Hermes fixture scenarios. Author review and fixed findings:
.ai/analysis/restricted-agent-clients-review.md. No blocking/major author finding;
independent release review remains maintainer-owned. Labels disabled; no merge.
