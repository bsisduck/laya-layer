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
- [ ] 2.1 Adapt to integrated main runtime, packaged UI, model/tool/operator contracts.
- [ ] 2.2 Prepare and test a clean local install, authenticated HTTP/UI and offline restart.

### Phase 3: Delivery
- [ ] 3.1 Document getting started, migration, model manifests and limits; review and validate.
- [ ] 3.2 Publish evidence and ready PR after gates pass; never merge.

2026-10-03: 15 lifecycle tests, Ruff and strict mypy pass. Fresh provisioning uses
24-hour all-four-operation credentials; existing state is never reprovisioned.
Root owns semantic-call quota #26 and final browser QA; launcher preserves all
private data files and uses the normal semantic worker CLI. Runtime clean install
is still pending tools integration on main; dependencies were fixtures in install
unit tests, while provisioning/migration and subprocess/HTTP effects were real.
