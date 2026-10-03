# Operator control plane execution plan

Source doc: .ai/specs/full-stack-delivery.md
Spec PR: #2 (merged)
Engine: om-auto-create-pr (steps: 5, --loop: no)

## Goal and scope

Implement E01-S01: separate operator sessions, durable atomic policy/feed updates,
mandatory document enforcement and reusable inspection hooks for model/tool owners,
and bounded operator reporting/playground APIs. Preserve document and export contracts.
Use this Cezar worktree on fresh origin/main. User authorizes commits, push, draft
and ready PR; no merge, labels, subagents, frontend, model routes or new tools.
Issue #8 appeared after initial lookup; PR #17 implements it and references #2.

## Implementation Plan

### Phase 1: Durable controls

1.1 Publish stable snapshot/inspection contract; implement bounded feed validation,
SQLite compare-and-swap policy/feed activation, durable activation audit and tests.
1.2 Bind document admission/dispatch/output to immutable snapshots; atomically
recheck active generation before intent; prove denial through executor assertions.

### Phase 2: Operator APIs

2.1 Implement reusable admin router, separate hashed operator credentials,
short-lived HttpOnly SameSite Strict sessions, exact configured origin/host and
CSRF checks, bounded reporting/export/playground; add private no-overwrite bootstrap.
2.2 Exercise authenticated APIs, expiry/logout replay, parser limits, activation
races, restart persistence and truthful metrics; document routes and compatibility.

### Phase 3: Verify and publish

3.1 Run make validate, review against om-code-review and CODE_REVIEW.md, fix findings,
push ready PR with exact deterministic/API evidence and inference exclusions.

## Risks and decisions

- Keep snapshots per action, revalidate before durable dispatch; output uses the
  dispatched snapshot so reload cannot mix versions. SQLite generation check and
  dispatch intent share a transaction across processes.
- Add isolated control-plane tables, retaining schema-2 document/export storage.
  Old binaries must not serve live activated policy; document rollback restriction.
- Explicit configured origin protects login too; local HTTP permitted only for
  loopback. No browser-stored bearer token. Sessions persist only hashed secrets.
- Feed is bounded typed JSON, literal/domain/digest/source matching only; no regex,
  downloads, pickle or executable deserialization. Model integration remains with
  its owner; callback tests cannot stand in for real inference.
- Auth is high risk: author review/evidence here; independent release review remains
  required by SDLC. Minimal app/CLI attachment hooks may need integration resolution.

## Progress

PR: #17
Issue: #8

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Durable controls

- [x] 1.1 Publish stable snapshot/inspection contract and durable validated controls — ca11d2f
- [x] 1.2 Enforce feed and snapshot safety in document actions — f9dd6d7

### Phase 2: Operator APIs

- [x] 2.1 Implement authenticated APIs and private operator bootstrap — 387e7e6
- [x] 2.2 Verify boundary behavior and document compatibility — a16aa0b

### Phase 3: Verify and publish

- [x] 3.1 Validate, review, and publish ready PR


## Evidence and remaining integration scope

At a16aa0b, `make validate` passed all workflow/config/lock checks, Ruff,
strict mypy (15 source files), pytest (246 tests), source and wheel build.
Both GitHub validate checks passed. Tests include real loopback CLI/HTTP startup,
operator bootstrap/login, document execution, activation/denial, export, restart,
and logout. Auth/CAS race/replay/denial assertions use deterministic fixtures.

Author `om-code-review` pass found and fixed malformed non-ASCII CSRF handling,
static snapshot hook compatibility, and retained playground credential binding.
No unresolved blocker/major; the FastAPI coroutine generic and trusted tools
Protocol cast are narrowly scoped typing limitations, documented in PR review.
Independent high-risk release review remains with root; no merge performed.

Per later coordination, memory/mail playground request adapters and stable private
24-hour demo credential plumbing are included. Actual tools, approvals and MCP
come from PR19; model execution/status comes from PR6; frontend/browser QA comes
from PR20. No Laya/Ollama inference ran here. Export schema 1 is unchanged.
Labels remain disabled. No agents spawned, new issues duplicated, or merges made.
