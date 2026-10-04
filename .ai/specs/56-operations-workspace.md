# Operations workspace — implementation handoff

Intent: help local operators inspect current decisions and work through exact HR
approval without navigating a tutorial. The supplied baseline screenshots show
serial full-width HR cards; the draft is below the first desktop viewport.
A forest rail, warm canvas, white surfaces and restrained orange actions retain
brand identity while 28px headings and compact rows improve operational density.
This is a presentation change; no backend, policy, identity or schema changes.

## Behavior

- Empty/unknown hashes open Overview → Operations. Existing hashes, trace queries
  and overview usage/standards/controls queries remain reachable. Workspace,
  Controls and Utilities group local SVG navigation. The mobile menu traps focus,
  makes the workspace inert, closes on Escape/backdrop/navigation/resize, and
  returns focus to its opener or workspace as appropriate.
- Operations uses `/admin/overview` plus the latest eight `/admin/events` rows.
  Allowed/redacted/denied counts retain their bounded terminal-event window.
  Pending approvals are global unexpired DB records, with tenant-a inbox links
  labelled separately. Unknown state remains unknown; configured is not healthy.
  Usage, standards and threat evidence are dedicated sections. Service states,
  audit delivery and expandable controls/ledger/coverage remain available.
- HR has a session/context toolbar and Source & results / Draft & review panes.
  Main source and draft actions appear together at 1440×900; mobile orders session,
  source, draft. Synthetic data and local fixture outbox are labelled at source
  and proposal/review boundaries. Exact review and deliberate resume are unchanged.
- Approval inbox rows show subject, recipient, requester, expiry and state.
  `Review exact payload & authority` discloses the complete immutable payload,
  identity, digests and fingerprint before consent and decision controls.
  Catalog uses three comparable desktop tool cards (returned inventory count), each
  with one scope/risk/policy disclosure; unavailable examples remain.

## States and recovery

| State | Display | Operator action |
|---|---|---|
| Loading | Loading operator state… / busy actions | Wait; duplicate mutation disabled |
| Empty audit | No audit activity recorded… | Open HR or timeline |
| Summary error | Operations summary unavailable. Refresh to retry. | Refresh; recent activity can still render |
| Activity error | Recent activity unavailable. Refresh to retry. | Refresh; summary can still render |
| Inactive HR | No active HR session / inactive authority explanation | Explicit start, renewal or policy inspection |
| Source denied/withheld | Actual decision/reason/execution and audit trace | Review evidence; no substitute output |
| Missing summary | Summary unavailable | Inspect source or draft manually; no fabrication |
| Pending approval | Exact immutable review and explicit consent | Approve/reject; approval alone has no delivery effect |

The existing optional summary remains AI-assisted: only actually released provider
output renders, and operators compare it with the source. Deterministic forms and
manual drafting satisfy navigation/workspace needs; no new AI behavior is added.
Uncertainty prefers visible missing/withheld output over invented success.
Known standard/v2/enforce HR false positives (#51) remain actual denial evidence.

## Acceptance and validation

Desktop source/draft actions must be simultaneously visible. Keyboard menu tests
cover Tab/ShiftTab, Escape/backdrop, same route, focus, resize and browser Back.
Async overview partial errors must never invent counts or service health.
Existing HR negative, expiry, exact approval, replay, withholding, no-mutation-retry
and DB-side-effect assertions remain. Installed-wheel QA and mocked presentation
checks are distinct from real-model evaluation. Full gate: `make validate`, with
pinned Hermes source provided. Independent review/QA is required before merge.
See `docs/operations-workspace-validation.md` for measured results when complete.
