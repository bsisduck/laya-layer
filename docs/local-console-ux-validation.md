# Local console UX author validation (issue 53)

Runtime frozen at `88e5344a512fdb23a689be88d60ba7de66954845`, based on main
`671979e`. Scope and concrete interaction states are in the
[acceptance spec](../.ai/specs/2026-10-04-local-console-ux.md).
No backend policy, authentication, response, schema, budget or semantic controls
changed. This remains the cream/forest/orange vanilla JavaScript local console.
Root independent final-head review and installed QA are required before
merge/install; author review does not grant release approval.

## Commands and evidence

Run from this worktree. `BASE_URL` is read from this worktree's ignored
`.ai/qa/test-env.json`. For public reproduction, `PROJECT_ROOT` substitutes the
private primary-checkout prefix of the command actually executed. Its
`.runtime/dependencies/hermes-source` checkout was pinned to
`f97608f178d1ffeca59860195ab7da295f7c8e5f`. No public document includes private
installation paths, credentials or host settings.

| Command | Author result and boundary |
|---|---|
| `make setup` | PASS: development dependencies/locked gateway and MCP preparation only |
| `.ai/scripts/test-env-up.sh --local-console` | PASS: own non-editable installed wheel; unchanged warm invocation reused it (`TEST_ENV_REUSED=1`) |
| `node --test tests/frontend/contracts.mjs` | 21 PASS, zero skips: decision/release/unknown evidence, progress, known section routes and existing contracts |
| `python3 tests/frontend/hr_flow.py` | PASS at frozen runtime: actual installed HR tool/approval/accounting effects, with an explicitly labelled provider fixture; no real inference |
| `uv run --locked --extra mcp --with playwright python tests/frontend/local_console_check.py --descriptor .ai/qa/test-env.json --artifacts .ai/qa/artifacts_local_console_ux` | PASS: actual installed no-login startup, unchanged startup authority/control state, session/CSRF recovery without replay, catalog/denials, exact approval/outbox replay, local HTTP MCP and mobile shell; no inference |
| `python3 tests/frontend/hr_components.py --url "$BASE_URL" --artifacts .ai/qa/artifacts_hr_components` | PASS: mocked API presentation only; held-response source lock, release/withheld/error/unknown summary, validation with zero requests, keyboard, navigation reset and all expired/revoked dependent controls disabled |
| `uv run --locked --with playwright python tests/frontend/browser_components.py --url "$BASE_URL"` | PASS: mocked consumers only; section deep links/back, empty usage first with keyboard disclosure, loading/missing/empty/401/503, catalog/XSS, approvals and existing shell behavior |
| `AGENTGATE_HERMES_SOURCE="$PROJECT_ROOT/.runtime/dependencies/hermes-source" make validate` | PASS at frozen runtime: 1,005 tests, zero skips, 138.36 seconds; workflow/Cezar configuration, locked dependencies, Ruff lint/format, strict mypy (58 source files), source distribution and wheel build |
| `.ai/scripts/test-env-down.sh` | PASS: own processes stopped; other installations and shared inference untouched |

The configured command is `make validate`; the explicit
`AGENTGATE_HERMES_SOURCE` override enables the pinned-Hermes adapter tests rather
than accepting skipped adapter evidence. These are gateway and fixture/control
tests, not real-model evaluation. The owned environment was stopped before this
gate. Subsequent changes are evidence documentation only.

## Author review

Verdict: **approve** for this bounded change after author inspection and the
configured gate; independent root review and final-head QA remain required.
No unresolved blocker or major finding remains in the reviewed diff. Source
selection and result progress stay aligned during held responses and navigation;
unknown execution or missing output does not become success or non-dispatch.
Known inactive authority disables every dependent action with adjacent recovery.

The changed consumers are the HR workspace, overview sections, department empty
state and shared busy/disclosure presentation. Existing REST/MCP contracts,
immutable approval payloads, scoped authority and accounting remain unchanged.
Installed tests retain the actual denial, replay, reservation and outbox effect
assertions; mocked component tests cover presentation separately. No dependency
or route bootstrap import was added. Screenshots and keyboard checks cover the
changed layout and interactions; the single startup sample below does not prove
production performance.

## Installed HR observations

All original permission, payload-mismatch, expiry, recovery and side-effect
assertions remain. Invalid recipient/empty or whitespace-only subject/body
make zero proposal requests and focus the invalid field. Pending and approved
mail create zero outbox rows. Exact resume/replay retain one row; an explicitly
new draft has a different action and requires fresh consent. The labelled HTTP
provider receives two requests with source data in the tool role: one released
fixture summary and one invalid output withheld. SQLite records two attributed
HR model attempts and one known settlement; the uncertain attempt remains.
Ending/rebinding, restart, expiry during a read and operator recovery cannot
transfer approvals or replay mutations.

## Retained failures and visual review

The first installed run passed immutable conflict and outbox/replay assertions,
then pressed the new-draft key before its control had re-enabled after replay.
The test now explicitly waits for enabled state and focuses the control; the
focus, fresh action and zero-effect assertions remain. The second run passed
that path and the provider/accounting checks, then hit a strict locator error:
the expired-session explanation now deliberately appears beside lifecycle and
both dependent actions. Its unchanged visibility check is scoped to lifecycle
feedback. The final full HR rerun passed. Initial logs and screenshots are
retained separately in ignored/private artifacts; no timeout, effect count or
denial assertion was loosened. Early browser exploration also caught an array
rendered as text instead of progress elements; it was corrected before the
implementation commit and the component test now asserts three real list items.

Author inspected supplied before and actual installed after screenshots for HR,
overview, catalog and approvals at 1440px and 390px. Usage/standards have their
own section screenshots; HR E2E also captures exact review, fixture summary and
390/768px layouts. No page-level horizontal overflow was observed; wide evidence
tables retain their labelled keyboard-scroll regions. A single installed
no-login startup sample was 270 ms; this is a smoke observation, not a load or
latency guarantee or user-study result.

Private artifacts: `.ai/qa/artifacts_hr`, `.ai/qa/artifacts_hr_components`,
`.ai/qa/artifacts_local_console_ux`; before/after screenshots and command logs
are also retained outside version control. No binary artifact is committed.

## Limits

These passes separate fixture/control proof from actual semantic efficacy. No
standard/CoreML inference or real SMTP, corporate IAM, external SIEM or bank
integration was tested here. [Issue 51](https://github.com/bsisduck/laya-sec-agent/issues/51)
and [the failed real HR observation](hr-release-observation.md) remain unchanged.
See [production readiness beyond authentication](production-readiness.md).
