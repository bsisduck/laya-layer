# Approved tool catalog execution plan

Source doc: .ai/specs/2026-10-04-tool-catalog.md

## Goal and scope

Bind trusted, immutable tool metadata and explainable local risk to the three
implemented executors, exact approvals, MCP discovery and the operator catalog.
Deliver a validated draft PR against main; independent root review precedes any
merge. Issue #36 taxonomy and #37 local console are independent. No identity,
authentication, login-mode, model, worker or Cezar configuration changes.

## Implementation plan

1. Define strict versioned metadata, deterministic risk, registry binding and
   enforcement disposition; unit and approval-upgrade/replay tests.
2. Add authenticated bounded admin catalog, generated MCP annotations and
   accessible UI with missing/error/empty states; functional and wire tests.
3. Document contracts and migration limits; run make validate and JS checks,
   review with om-code-review, rebuild an owned installed QA app, exercise the
   browser and integration boundaries, and always tear down owned services.
4. Publish the tested head as one draft PR with exact evidence and limitations.

## Risks

Catalog changes invalidate pending approvals without changing consumed snapshots
or spend. Risk cannot grant authority. Future examples are unavailable and never
enter executable discovery. All observations distinguish fixture enforcement from
real inference; no new inference evaluation is performed.

## Progress

PR: #41
Issue: #38

> Convention: `- [ ]` pending, `- [x]` done. Append commit SHA when a step lands.

### Phase 1: Trusted authority

- [x] 1.1 Implement metadata, risk, registry and approval/replay evidence — fcac351

### Phase 2: Catalog surfaces

- [x] 2.1 Implement protected API, MCP hints, UI and functional/wire tests — dda23a8

### Phase 3: Verification

- [x] 3.1 Complete docs, full validation, review and installed browser QA — 556de79

### Phase 4: Draft delivery

- [x] 4.1 Publish draft PR and report exact head, evidence and limits — PR #41

## Delivery evidence

Runtime head 556de794fda60c5fcd11a82ba42d58be22946db3: retained pinned Hermes
`make validate` passed 714 tests without skips; lint, strict mypy and packaging
passed. JS: 9 passed. Acceptance: 140 deterministic control observations; not
semantic successes. Rebuilt installed credential-mode browser catalog/REST/SQLite,
approval/replay/outbox and baseline taxonomy QA passed; mocked consumer states are
reported separately. Wheel hashes matched source; owned services stopped in finally.
Artifacts remain ignored in `.ai/qa/artifacts_catalog/` and `reports/generated/`.

Root independently reviewed/tested 743c869 (712 tests, installed and mocked browser
suites; no blocker/major found). Delta 556de79 makes the fixed idempotency/closed-world
MCP hints explicit immutable registry fields, with two rejection tests, documentation
and a screenshot scroll adjustment. No scores, permissions or executor behavior changed.
The delivery head adds only this progress record; exact final-head validation and
CI results are recorded on the draft PR. No author merge or self-approval; root
owns final delta review and integration. Real inference, bank/GitLab/SMTP connections
and explicit local-console mode are outside this task's evidence.
