# One-command application installation and lifecycle

Source doc: .ai/specs/full-stack-delivery.md
Issue: #13 (E03-S01)
Engine: om-auto-create-pr (steps: 7, --loop: no)

## Goal and scope

Install and operate the complete loopback Laya Sec Layer from a clean macOS/Linux
checkout without Node, cloud keys or paid calls. Preserve authoritative state and
credentials, and never signal shared Ollama or unrelated listeners/processes.

## Implementation Plan

### Phase 1: Owned lifecycle
1.1 Build private state, locked installation and CLI.
1.2 Implement supervisor-owned processes, bounded readiness, status/logs/doctor.
1.3 Exercise real subprocess failures, ownership, offline restart and preservation.

### Phase 2: Integrated application
2.1 Adapt to integrated main runtime, packaged UI, model/tool/operator contracts.
2.2 Prepare and test a clean local install, authenticated HTTP/UI and offline restart.

### Phase 3: Delivery
3.1 Document getting started, migration, model manifests and limits; review and validate.
3.2 Publish evidence and ready PR after gates pass; never merge.

## Risks and non-goals

Runtime dependencies #6/#19/#20 land through root integration, never author-branch
merges here. Default semantic checks remain explicitly off; optional runtimes and
assets are isolated, with no concurrent heavyweight evaluation. Tests with local
HTTP/process fixtures are lifecycle evidence, not real-model quality evidence.
No Cezar dependency, labels, extra agents, OS sandbox guarantee or shared daemon
ownership. Existing 8000/4001/11434 listeners remain untouched. Use 8080/4000.
Credential expiry renewal needs an explicit operator-controlled new authority
without reviving revoked rows or resetting root accounting; coordinate its hook.

## Progress

PR: #22

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Owned lifecycle
- [x] 1.1 Build private state, locked installation and CLI.
- [x] 1.2 Implement supervisor-owned processes, bounded readiness, status/logs/doctor.
- [x] 1.3 Exercise real subprocess failures, ownership, offline restart and preservation.

### Phase 2: Integrated application
- [x] 2.1 Adapt to integrated main runtime, packaged UI, model/tool/operator contracts.
- [x] 2.2 Prepare and test a clean local install, authenticated HTTP/UI and offline restart.

### Phase 3: Delivery
- [ ] 3.1 Document getting started, migration, model manifests and limits; review and validate.
- [ ] 3.2 Publish evidence and ready PR after gates pass; never merge.

2026-10-03: 15 lifecycle tests, Ruff and strict mypy pass. Fresh provisioning uses
24-hour all-four-operation credentials; existing state is never reprovisioned.
Root owns semantic-call quota #26 and final browser QA; launcher preserves all
private data files and uses the normal semantic worker CLI. Runtime clean install
is still pending tools integration on main; dependencies were fixtures in install
unit tests, while provisioning/migration and subprocess/HTTP effects were real.

2026-10-03 integration: merged main PR24 and PR19 into this branch, preserving
runtime author history. c5b918e passed make validate (448 tests), then a genuine
clean install at a private temporary directory served gateway8080/proxy4002.
Port4000 was occupied and correctly refused. Operator session/static assets,
document allow/cross-tenant denial, scoped memory, approval-to-once-only local
outbox, MCP initialization/discovery and local model discovery passed over HTTP.
Warm prepared restart with UV_OFFLINE=true took5.4s; authority, audit, budgets,
outbox and configuration matched exactly. Owned services were stopped afterward;
shared8000/4000/4001/11434/Cezar4322 listeners were still present. No inference run.

Independent root review reproduced source-only wheel cache reuse at the same
package version. Added an actual offline uv/wheel regression: failed against old
installer by observing stale installed JS, then passed with --reinstall-package
agentgate on the changed-install path. Unchanged fingerprint still skips all
preparation. Root owns PR31 collector/telemetry/lifespan/CLI/QA integration.
