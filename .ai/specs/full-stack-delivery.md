# Laya Sec Layer — full-stack delivery specification

Status: authorized implementation scope, 2026-10-03. The user explicitly requests
the complete application, straightforward installation, tests, and Open Mercato /
Cezar generation and execution of tasks, commits and PRs. Proceed through the
backlog without another permission round for those project operations. Merge
working, reviewed changes through PRs; do not publish credentials or contact banks.

## Sources and users

The two supplied AI Control Layer PDFs and the existing
`AgentGate_Full_Project_Architecture.md` define the controls and judge scenarios.
Security operators need a visible, configurable enforcement boundary; developers
need standard model/tool interfaces; judges need repeatable positive/negative
tests and ad-hoc changes. This is the functional P0 in architecture §22.1, with
explicit measured limitations rather than universal security or bank certification.

## Decisions

- D01: Keep Python 3.12/FastAPI/SQLite and the existing document contracts. Serve
  a packaged HTML/CSS/ES-module web app from the gateway; no Node requirement for
  an installed product. Use a neutral ink/ivory/orange industrial operator UI.
- D02: Loopback standalone install on macOS/Linux. A container profile can isolate
  private upstreams. Host administrators remain trusted; the native demo cannot
  sandbox other processes belonging to the same OS user.
- D03: One real local generation model behind private authenticated LiteLLM.
  Model tag must pass an actual generation/tool-call spike before selection.
  No paid provider calls or cloud fallbacks. Financial reservations can be verified
  with a clearly labeled simulated-priced provider fixture; actual local cost is
  reported separately. No guarantee about a third-party invoice is made.
- D04: Model Chat Completions facade, REST and MCP share server-owned credentials,
  policy, persistent reservations and audit. Buffered SSE releases only inspected
  completed content. No arbitrary URLs, provider keys or metadata identity overrides.
- D05: Register documents.read, memory.query and mail.send. Mail writes to a local
  test outbox only and needs exact-action one-use approval plus idempotency.
- D06: Separate operator authentication from agent credentials. Short-lived operator
  sessions or an explicit operator bearer token; no secrets embedded in frontend
  assets. Require same-origin writes and server-side authorization on every admin
  route; persist policy/feed activation and retain last good state on rejection.
- D07: Deterministic controls remain mandatory. Semantic enforcement is configurable;
  required unavailable/incomplete analysis fails closed. Keep raw labels fixed in
  held-out evaluation and report false positives/abstention honestly. Native CoreML
  and standard Laya stay in isolated environments, never loaded concurrently for QA.
- D08: Initial telemetry delivery targets a local compatible lab endpoint. Bank
  connections, enterprise SSO and certified vendor support require their separate
  deployment inputs and are outside this locally installable P0.

## Contract for the full-stack UI

Static application at `/`, assets under `/static/`. Login accepts an operator
credential through POST `/admin/session`; GET/DELETE same path introspects/logs
out. No localStorage token persistence. API responses are JSON, error responses
carry a safe `detail`. Cookie mode uses HttpOnly SameSite=Strict and anti-CSRF
header for state-changing requests; localhost HTTP is disclosed as local-only.

Proposed API shape to freeze in the control-plane task before frontend integration:

- GET `/admin/overview`: `policy_version`, `controls`, `counts` (allow/redact/deny/
  pending), `budgets`, `services`, `latency`, `coverage` with measured/unknown status.
- GET `/admin/events?limit=100`: `{events:[...]}` minimized records, bounded limit.
- GET `/admin/policy`: `{policy:{...}, version:...}`.
- POST `/admin/policy/validate`: `{policy:{...}}` -> validation result.
- POST `/admin/policy/activate`: `{policy:{...}, expected_version:...}` -> new version.
- GET/POST `/admin/feed`: current metadata or validated data-only indicator feed.
- GET `/admin/approvals`: `{approvals:[...]}`; POST `/admin/approvals/{id}/decision`
  with immutable-action approval/rejection and current policy revalidation.
- GET `/admin/outbox`: `{messages:[...]}` test-outbox metadata, bounded.
- POST `/admin/playground`: authenticated operator creates a bounded demo action
  using a server-owned scoped demo principal, never body-supplied tenant/role.
  Modes `document`, `model`, `memory`, `mail`; responses expose decision, reasons,
  executed flag, result, trace and pending-approval ID as applicable.
- GET `/admin/audit/export`: operator-only bounded download using the implemented
  export projection. No raw prompts/credentials in the security timeline.

Use empty/loading/error states, keyboard-accessible controls, responsive layout,
and explicit service-unavailable messages. Do not simulate successful API results
or display fabricated metrics when backend data is unavailable.

## Implementation Plan

### E01 — Governed AI runtime

**E01-S01: Operator control plane, live policy and threat feed** (high risk).
Given an agent token, all admin routes deny it. Given invalid/stale policy or feed,
the last good version remains active. Given valid activation, the next dispatch
uses the new snapshot and an audit event names its version. Bounded indicators
include denied literal patterns/domains and prohibited artifact digests/sources;
unsafe serialized artifact fixtures are inspected as metadata, never executed.

**E01-S02: Private model routing and atomic resource budgets** (high risk).
Given an allowed alias and local upstream, Chat Completions work and preserve
tool-call IDs. Unknown model/URL overrides deny before dispatch. Input secrets
never reach upstream; blocked outputs never reach client, including buffered SSE.
Concurrent calls cannot exceed root/principal/tenant token/call/simulated-money
limits. Timeouts retain unresolved reservations; retries/fallbacks do not escape
attempt accounting. Tests prove real local generation separately from fixtures.

**E01-S03: Scoped tools, approvals and MCP** (high risk).
Memory queries return only permitted tenant data. Forbidden destinations produce
no outbox write. Approved exact actions execute once under retry/concurrency;
mutated payload, replay, expiry, revocation and policy changes cannot bypass
checks. MCP tools preserve call correlation and route through the same authority.
Dependencies: E01-S01, E01-S02 for integrated demo (core tools may be developed first).

### E02 — Operator application and reporting

**E02-S01: Functional dashboard and playground** (medium/high risk).
Operator can log in/out; inspect overview/timeline/budgets/worker state; edit and
validate/activate policy/feed; run allow/redact/deny examples; review exact mail
actions; export evidence. All numbers come from APIs. Test denied operator access,
loading/error/empty states and responsive keyboard use. Dependencies: E01-S01;
model/tool portions depend on E01-S02/E01-S03.

**E02-S02: Durable telemetry delivery and measured performance** (high risk).
Reuse export formats from the existing export PR. One actual local collector
receives correlated minimized events. Retried delivery survives restart, partial
failure and duplicate replay without advancing an unacknowledged cursor. Show
delivery backlog and measured latency without unbounded labels or raw content.
Dependencies: export foundation, E01-S01.

### E03 — Installation and real integrations

**E03-S01: One-command installation and lifecycle** (medium risk).
From a clean supported checkout, documented launcher installs locked dependencies,
initializes private state, prepares requested local assets and starts the app.
Provide start/status/stop/logs/doctor; never overwrite existing keys/state or kill
unrelated processes. Offline restart works after assets are prepared. CoreML is
macOS-only with explicit unsupported-host status. Dependency: runtime/UI contracts.

**E03-S02: Real agent and offline acceptance demo** (high risk).
Run a direct programmatic agent and a restricted Hermes/MCP profile through the
gateway model and tools. Verify actual tool list, root binding, audit and side
effects. Native host tool bypasses are disabled or accurately disclosed. Tests
distinguish unavailable third-party integration from successful execution.
Dependencies: E01-S02/S03, E03-S01.

### E04 — Evaluation and release evidence

**E04-S01: Real semantic evaluation and resource envelope** (medium risk).
Freeze labeled English/Polish benign, quoted, negated and malicious cases before
evaluation. Run both installed backends separately; report accuracy, abstentions,
coverage and measured timings with checkpoint/runtime/fixture hashes. No label
rewrites, stub substitution or universal injection-protection claim.

**E04-S02: Integrated security QA and submission** (high risk).
Map architecture T01–T48 to executable assertions or honest measured evaluation.
Run clean-install, browser, budget races, outage/restart, policy/feed changes,
stream output and collector tests. Independent review covers auth/data/money/
approval boundaries. Prepare <=10-slide PDF, architecture, demo script and known
limits. Team identity fields remain user-owned; no invented members or submission.
Dependencies: all other stories. Scoring/start-time discrepancies remain recorded,
not resolved by claiming organizer approval.

## Definition of done

Every story has an issue, isolated branch, meaningful tests, review evidence and
PR; validated changes are integrated, not left as unrelated prototypes. The app
starts from its documented launcher and exposes real working UI/control paths.
Default tests, install smoke and real integration/evaluation reports identify
exactly what ran. Source and credentials remain separate. Release notes do not
call the app bank-certified or hide residual model-quality/deployment boundaries.
