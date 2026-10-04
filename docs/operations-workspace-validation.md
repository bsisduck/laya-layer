# Operations workspace validation — issue #56

Runtime commits: `b4310c4` (operations/HR/navigation/inbox layout), `6fc3777`
(comparable catalog, immediate workflow links, responsive focus and regressions).
Consumer follow-up: `6a93b0b` (usage/standards/ledger routes and missing-data-only
authority bootstrap). Follow-up `c8c0e17` adds only the mobile breakpoint guard
and its regression; the rest of runtime remains at `6fc3777`.
Base: fresh `origin/main` `60328b9` (merged #54). No backend enforcement, schema,
auth, policy, provider or Cezar configuration changes. Default page is Operations;
existing route hashes/queries and explicit `#hr` are retained.

## Evidence

Installed product QA uses the owned, non-editable wheel at
`.runtime/qa-install/runtime/gateway/.../site-packages/agentgate`, with readiness
through `.ai/scripts/test-env-up.sh --local-console`. QA owns loopback port 60032;
primary 8080 and shared Ollama 11434 are untouched. Initial bootstrap preceded
`hr_flow.py`. The HR runner preserves the prior stopped database and retains its
separate evidence ledger rather than resetting populated data.

| Check | Measured result | Local evidence |
|---|---|---|
| JavaScript contracts | 22 passed, 0 failed/skipped | `/tmp/issue56-contracts-final.log` |
| Initial workspace consumers at `6fc3777` | 5 scenario groups passed: default/count scopes, partial errors/loading/stale response, exact approval disclosure, mobile focus/menu, query/Back/dirty cancellation | `.ai/qa/artifacts_workspace/result.json` |
| HR components | Passed desktop simultaneous actions, compact toolbar, mobile order; existing negative/withheld/validation/expiry assertions retained | `.ai/qa/artifacts_hr_components56/` |
| Browser components | Passed mocked catalog/approval/401/503/XSS/loading/empty/idempotency consumers | `/tmp/issue56-browser-components.log` |
| Local-console installed E2E | Passed REST/MCP/SQLite effects, expiry/no mutation retry, controls/export/mobile; no inference | `.ai/qa/artifacts_local_console56/result.json` |
| HR installed E2E at `6fc3777` | Passed: one outbox row, replay still one; negative grants, expiry, no retry; 2 labelled provider-fixture calls, failed output withheld | `.ai/qa/artifacts_hr/result.json` |
| Credential-console installed E2E | Passed catalog/forbidden zero effects, document/memory/approval/replay/renewal/CAS/feed/export/session/390/768/1440px | `/tmp/issue56-browser-installed.log`, `.ai/qa/artifacts_browser56/` |
| Threat-control installed E2E | 9 scenarios passed; actual durable denial/no outbox, unknown filters, old payload/error/loading/mobile | `.ai/qa/artifacts_threat_ladder56/result.json` |
| Authority installed E2E | Passed local child REST/read/model denials, exact approval, one outbox effect, replay/mutation/revocation and separate human/accounting/approver | `.ai/qa/artifacts_authority/local-console/result.json`, `/tmp/issue56-authority.log` |
| Department usage installed E2E | 7 persisted fixture attempts; 5 known/2 unknown; exact simulated total `9999990000000000692` micro-USD, rollback/freeze/denied effects and mobile tables pass | `.ai/qa/artifacts_department/`, `/tmp/issue56-department.log` |

Artifacts/logs are ignored and remain local. The local-console report predates the
refinement commit but tested the same runtime bytes; installed HR evidence names
the committed head. The earlier follow-ups adapt existing usage/authority consumers
and document default-route behavior. The independent-QA follow-up below fixes the
subsequently reproduced navigation race. No assertion on denied execution, side effects,
exact payload, withholding, expiry or replay was removed.

## Visual comparison

First milestone was captured and inspected before the full gate. Reviewer baseline:
`/tmp/laya-operations-before/` (1440×900, 390×844); original HR failure also at
`/tmp/laya-ux-live/hr-1440.png` and `hr-390.png`. First milestone:
`/tmp/laya-operations-milestone56/`; configured HR desktop 1927→1034px and mobile
2327→1496px, with source and draft actions together at 1440×900.

Refined route matrix: `/tmp/laya-operations-final56/` contains all 13 routes at
both widths (26 distinct captures; 34 read-only render visits including repeated
utility checks), with 0 overflow, page errors or protected writes. Policy/feed,
playground/export, timeline and dedicated evidence/usage views were captured
and included in the route checks; key desktop/mobile views were visually inspected after the global stylesheet replacement. Key images:

- `hr-workbench-1440-viewport.png`, `hr-workbench-390.png`, `hr-active-1440-viewport.png`
  and `approval-populated-1440.png` / `approval-populated-390.png` in the milestone directory.
- `overview-1440-viewport.png`, `catalog-1440-viewport.png`, and mobile equivalents
  in the final directory. All three implemented tools fit the desktop first viewport. Desktop catalog height
  is 2277→949px; fresh Operations was 4436→1072px (populated refined capture 1024px).
- `.ai/qa/artifacts_workspace/overview-summary-error-1440.png`,
  `overview-activity-error-1440.png`, `approval-expanded-1440.png` / `390.png`, `menu-390.png`.
- `.ai/qa/artifacts_hr/exact-review.png`, `fixture-summary.png`, `hr-1440.png` / `hr-390.png`.

White text on the darker orange `#c54d1b` measures 4.72:1 contrast; mobile action,
menu, navigation and disclosure targets are at least 44px.

Root independently accepted the refined catalog/overview/active HR screenshots and
reviewed runtime `6fc3777` with no major/blocker findings reported. Root measured
static assets 106849→113852 bytes (+7003), concatenated gzip 30547→32415 bytes;
no new dependency, CDN asset or network integration. Author checks are not an
independent QA approval; required independent review/QA remains before merge.

## Limits and resolved test diagnostics

Mocked presentation tests and HTTP provider fixtures are deterministic evidence,
not classifier evaluation. Real semantic inference was not run. Standard/v2/enforce
has known HR false positives (#51); actual denial/withheld output remains visible.
The no-semantic owned HR fixture allowed its CV test; that is not efficacy evidence.
Synthetic sources, local outbox and simulated tariffs are not hiring decisions,
SMTP, commercial billing guarantees, production readiness or compliance certification.

| Initial check | Cause / owner | Resolution |
|---|---|---|
| First route probe | Product syntax error in initial HR status rendering; Agent | Corrected before first successful milestone; 18 then expanded route renders pass |
| Workspace unknown-state assertion | Test locator matched semantic and delivery unknown states; Agent/QA | Assert exact two reported unknown pills; all 5 scenario groups pass |
| First local-console invocation | Missing required descriptor argument; Agent/QA | Reran existing CLI with descriptor; installed flow passes |

## Independent QA follow-up — PR #57

Independent installed QA at `8a42425` failed twice after browser Back →
1440→390px resize → Open navigation → Policy studio. Author runs of the
unchanged script returned PASS then FAIL on owned port 60032, reproducing the
missing Navigation menu. Logs: `/tmp/laya-navigation-race57-original-1.log` and
`/tmp/laya-navigation-race57-original-2.log`.

| Failure | Evidence and cause | Fix / owner |
|---|---|---|
| Drawer disappears or Policy stays on Overview | Buffered URL/focus/native-event trace: Back hashchange completed; opener click at +11.7ms; queued media callback at +15.9ms sees the open dialog and focused Policy link, then closes it and moves focus to workspace | Product race; `c8c0e17` keeps the newly opened drawer at current mobile width; desktop still clears modal/inert state |
| Immediate final URL assertion after dirty-editor Cancel | First fixed run reaches Policy but fails the immediate URL read; failure screenshot retains edited revision 2. Separate confirmation trace records `false` and final `#policy` | QA synchronization; await actual confirm event and restored URL, assert exact prompt, retained draft, focus and closed drawer |

The new regression holds an actual native media callback, opens the drawer, then
releases the callback. It fails on the old runtime after release, and passes with
the two-line guard. The original Back/resize/open/Policy sequence remains
unchanged; no retries or timeout increases were added. No HR negative,
idempotency, expiry, withholding or mutation assertions changed.

At `c8c0e172c6eada753721ddb193393fbe5b76e658`:

- 6 workspace scenario groups passed in two separate complete runs, including the
  held-native-callback regression and original keyboard/Back sequence.
- 22 JavaScript contracts passed, 0 failed/skipped.
- Actual installed local-console REST/MCP/SQLite E2E passed, including exact
  approval/replay, expiry/no mutation retry and session recovery; no inference.
  The installed `app.js` SHA256 matches committed source bytes.

Evidence root: `/tmp/laya-navigation-race57/`. Event/focus/URL ordering is in
`buffered/events.json` and `resize-event-excerpt.json`; the failed old-runtime
regression is `regression-before/failure.png`. Passing screenshots were captured
and visually inspected at `fixed-2/menu-delayed-resize-390.png`; cancellation
retention is visible in `regression-after/failure.png`. Results are in
`fixed-1/result.json`, `fixed-2/result.json`, `local-console/results.json` and
`installed-asset.json`. Command logs are `/tmp/laya-navigation-race57-fixed-1.log`,
`-fixed-2.log`, `-contracts.log`, and `-local-console.log` with the same prefix.

This is author fix/QA evidence. Root's independent follow-up gate and affected
browser QA remain required before merge; PR #57 stays draft.

## Full gate and teardown

At code/test head `6a93b0b`, `make validate` passed with
`AGENTGATE_HERMES_SOURCE` pointing at the manifest-pinned local Hermes source:

| Gate | Result |
|---|---|
| Workflow/Cezar artifacts and lock consistency | PASS |
| Ruff lint / format | PASS · 124 files formatted |
| Strict mypy | PASS · 58 source files |
| Pytest | PASS · 1005 passed, 0 failed/skipped, 136.38s |
| Source distribution and wheel | PASS |

Follow-up gate at `c8c0e172c6eada753721ddb193393fbe5b76e658` also passed:
**1005 pytest passed, 0 failed/skipped, 140.89s**, workflow/lock checks,
Ruff lint/format (124 files), strict mypy (58 source files), sdist and wheel.
All pinned Hermes tests ran with the same explicit source variable.
Log: `/tmp/laya-navigation-race57-validate.log`. Owned QA was stopped before this
serial gate; its descriptor still reports `status: stopped`. Author review of the
follow-up found no blocker/major; independent follow-up review/QA remains required.

Exact log: `/tmp/issue56-validate.log`. All four source-gated pinned Hermes tests
ran locally. The existing GitHub workflow omits that optional source variable;
CI may report those checks skipped and must be read separately from this local run.
Author `om-code-review` found no remaining blocker/major against the configured
gate, compatibility contract and retained consequential browser assertions. This
is an author-side check, not independent approval or merge permission.

Owned QA descriptor reports `status: stopped`; authority and department runners
stopped their installation in `finally`. No guessed PID/port kills, primary 8080
changes, shared Ollama 11434 changes, model inference or model evaluation occurred.
Publication is a draft PR for #56; merge remains outside this task.
