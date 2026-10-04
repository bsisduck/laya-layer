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

> Convention: `- [ ]` pending, `- [x]` done. Append commit SHA when a step lands.

### Phase 1: Trusted authority

- [x] 1.1 Implement metadata, risk, registry and approval/replay evidence — fcac351

### Phase 2: Catalog surfaces

- [x] 2.1 Implement protected API, MCP hints, UI and functional/wire tests — dda23a8

### Phase 3: Verification

- [ ] 3.1 Complete docs, full validation, review and installed browser QA

### Phase 4: Draft delivery

- [ ] 4.1 Publish draft PR and report exact head, evidence and limits
