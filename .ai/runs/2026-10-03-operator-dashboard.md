# Operator dashboard execution plan

Source doc: .ai/specs/full-stack-delivery.md
Issue: #11 — E02-S01
Engine: om-auto-create-pr (steps: 6, --loop: no)

## Goal

Deliver a packaged, accessible operator dashboard using authenticated admin APIs,
with honest unavailable states and evidence from static, component and live UI tests.

## Scope

Own `src/agentgate/web/`, `web_routes.py`, frontend tests/docs, and a minimal
`app.py` attachment. Preserve service, policy and admin ownership. No Node runtime,
CDNs, model inference, backend placeholders, additional agents, or merges.
Design: ink rail, ivory dense work panels, safety-orange actions, typographic hierarchy.

## Implementation plan

1. Package the static shell and restrictive response headers; test routing/package assets.
2. Implement session lifecycle, overview/timeline, and accessible navigation.
3. Implement playground, policy/feed CAS editing, approvals/outbox and export consumers.
4. Freeze API integration against control-plane/tools contracts and verify error states.
5. Run complete validation, browser keyboard/mobile checks, and OM code review.
6. Publish verified ready PR and evidence with precise remaining integration limits.

## Risks

Control-plane PR17 and model/tool stories are concurrent. Never call a missing route
successful. Live backend E2E depends on their integration; disclose any remaining gap.
No auth/enforcement authority lives in JavaScript. Privileged data uses text nodes.

## Progress

PR: #20

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Packaged application

- [x] 1.1 Package static shell and verify routing — cc74e71
- [x] 1.2 Implement session and observation views — f6b0227
- [x] 1.3 Implement operator actions and editors — f6b0227

### Phase 2: Verify and publish

- [x] 2.1 Freeze API integration and test failure states — cd02f05
- [x] 2.2 Validate, browser-test and review — cd02f05; make validate 174 passed; real PR17 browser + mocked consumer suites passed
- [x] 2.3 Publish ready PR and evidence — PR #20; author review and evidence posted; independent integration/release review remains root-owned
