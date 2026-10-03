# Full-stack release integration — E04-S02 (#16)

Scope: assemble independently reviewed runtime stories, wire the operator's
credential renewal and measured telemetry/budget status, exercise the installed
application in a browser, and publish a reproducible evidence/demo package.

## Plan and acceptance

1. Integrate reviewed tools, credentials, quota, collector, installer and agents;
   preserve shared history and all persistent authority/accounting contracts.
2. Expose credential expiry/explicit renewal and telemetry status in the operator
   UI. Keep local collector delivery identified as a lab, not vendor deployment.
3. Reuse the product launcher for cold/warm QA startup, then test actual login,
   document/memory/model paths, exact mail approval/consumption, policy/feed CAS,
   quota denial, exports and restart. Separate deterministic, semantic and real
   generation evidence.
4. Map T01–T48 to executable checks or versioned measured evaluation. Keep
   inaccurate/failed model results visible; never reinterpret them as success.
5. Refresh architecture, install/demo/readiness documentation and a <=10-slide
   PDF source/artifact. Team identity and actual organizer submission stay user-owned.
6. Run make validate and independent review of consequential integration changes,
   confirm CI, then merge and run the reviewed app from the user's checkout.

## Boundary

Native loopback deployment trusts the host administrator; mail is a local outbox,
prices are simulated, artifact intake is metadata policy simulation, telemetry is
one local contract lab. No claimed bank access or certification. No raw source PDFs,
private keys, runtime state, model weights or generated logs are committed.

## Evidence

Pending integrated implementation and final gates. This plan is not completion.

## Operator expiry integration

The playground displays server-returned scope, expiry and epoch. Expired authority
has an explicit CAS renewal action; revoked authority remains disabled. A governed
401 action denial no longer discards the separate valid operator session. Both
model and tool credentials use the existing protected server contract; no secret
is sent to the browser. Budget spend and prior approval identity remain unchanged.

Validation: make validate 419 tests PASS plus six native JS contract tests.
Chromium mocked consumer suite PASS, including expiry/renewal/revocation, exact
approval/draft retries, loading/errors and mobile layout. Its first attempt failed
because the temporary static test server omitted /static mapping; corrected test
serving matched the packaged route. This was a test environment error, not an
application failure, and these mocks are not enforcement proof. Installed real
browser QA remains pending.

## Measured observability integration

The gateway owns one durable telemetry sender inside its lifespan, composed with
MCP startup/shutdown. Trusted CLI config/token file flags configure it together.
Admin overview exposes actual acknowledgments, lag, pending/retry state and recent
delivery timing; no credential or raw request content enters the response. A dead
sender is unavailable, never presented as healthy. HTTP response timings use a
bounded 512-sample process-local window and fixed route categories. They explicitly
include provider/tool time and exclude MCP/disconnected requests; these are not
isolated guard overhead or permanent historical metrics.

Validation: make validate 464 tests PASS, six JS contract tests PASS. Three new
integration tests exercise real gateway lifespan + MCP + authenticated admin +
HTTP collector across restart (two records, no duplicates), reject partial sender
configuration, and verify timings only after the final body with bounded memory.
An existing test expecting unknown latency was updated to assert three measured
responses; no protection contract changed. Product launcher wiring remains next.

## Installed application evidence (2026-10-03)

The product launcher now owns private LiteLLM, the local telemetry collector and
its gateway; optional semantic worker profiles are version-bound on both sides.
State migration preserves independent keys, live controls, approvals and ledgers.
The non-editable wheel rebuild fix from PR22 is integrated. Explicit profile
changes version the policy; unknown profiles are refused before provisioning.

At 6495842: `make validate` PASS **536 tests**, Ruff, strict mypy, source/wheel
packaging. The semantic-profile wiring adds real provisioning/CAS checks but
mocks downloads; it is not inference evidence.

Installed Chromium QA PASS: login rejects agent authority; scoped documents
allow/redact/deny; memory excludes other-tenant rows; mail approval is immutable;
changed payload conflicts; execution/retry leaves exactly one SQLite outbox row;
expired playground authority renews explicitly while identity and all budget rows
stay unchanged. Policy CAS conflict, next-request feed enforcement, minimized
export, session revocation, keyboard operation and 390/768/1440px layouts passed.
A separate authenticated overview/collector comparison observed 51 acknowledged
minimized records, zero lag, and the tested mail action with no mail payload leak.
Observed response P50/P95 were 19.286/39.985 ms across 28 playground responses;
this includes tool time, not isolated security overhead, and resets on restart.
The test restores configuration at newer revisions without deleting records.

Real installed browser generation also PASS: secret input denied before any model
attempt; ordinary summary produced 488 characters and usage 36 prompt / 82 output
= 118 tokens, one durable provider attempt, 4317.436 ms end to end. This is an
individual generation timing, not a percentile or semantic-quality result.

QA launcher proof PASS: warm reuse 0.244 s, tracked-source touch invalidated reuse,
double stop was idempotent, restart 7.406 s, and private tokens, credential epochs,
tool/model budget accounts were unchanged. Evidence and screenshots live in
ignored `.ai/qa/artifacts_fullstack/`; no credentials or runtime state are published.
Two first browser attempts exposed test assumptions (same-route focus and the
immutable payload also including idempotency_key); corrected assertions then
passed against the unchanged product. Earlier unsuccessful attempts remain in
local audit state.

The owner requested GPT-6.1-Sol for execution. Cezar's live catalog exposes it;
subsequent docs and integrated artifact-review tasks explicitly use that model.
Native prior runs finish on their existing model. Final integration review/CI and
remaining agent/document delivery are still required before product release.

At f6bccde, the complete executable installed browser suite also passed with
`--model`, including the real provider response and durable attempt accounting.
An independently prepared standard/v2 installation passed offline reprepare and
four-service startup. Its actual browser released ordinary notes, withheld the
embedded-instruction document output (`SEMANTIC_BLOCKED`, read executed), and
refused cross-tenant access before execution. Semantic quota advanced from 0 to
2 of 1000; all owned semantic-QA processes were stopped afterwards. This does not
replace the held-out quality evaluation or claim that all attacks are detected.

PR28 artifact intake merged after GPT-6.1-Sol independent exact-head review:
548 deterministic tests plus 56 negative probes, both CI checks green. Its
metadata-only simulator adds no artifact execution/download permission.

Independent GPT-6.1-Sol re-review at 9e1cfec resolved both original findings:
plain FastAPI embedding now reports unconfigured telemetry/latency honestly, and
changing the owned collector port retains checkpoint, pending batch and retry
state across partial publication. Two regressions failed before the fixes; 33
focused checks passed afterward. Independent full557-test gate, six JS contracts,
real CLI port migration/deduplication/new delivery, seven negative probes and
installed browser rerun passed; review5402768489 reports no blockers/majors.
The reviewer's owned QA was stopped; no inference ran.

Reviewed artifact28 and restricted-agent30 are integrated at c7e3a5f. PR30's
independent full gate ran all584 checks with pinned upstream Hermes fixtures,
zero skips; actual cycle report SHA-256 was independently verified. Docs33 was
reviewed and merged into the release branch; diagrams, runbook, acceptance
selectors and EN/PL slides now describe integrated code instead of pending PRs.
ANE and same-user host-isolation gaps remain explicit.

At b740c35 the source-prepared installed wheel passed the complete browser suite
again with actual configured generation. Summary488 characters,118 tokens, one
provider attempt,3450.325ms; secret input made no upstream attempt. Collector92
records, zero lag and observed minimized mail outcome. Observed12-response
P50/P95 8.944/3404.923ms includes generation; not isolated guard overhead.
Reports are ignored under `.ai/qa/artifacts_fullstack_final/`. The common overview
report's former fixed "no inference" wording was corrected to refer to the
separate optional model evidence; the actual model report already records it.

PR35 at54f3369 independently reviewed and merged ba2dae8 with both CI checks
green; root separately ran60 model/fragment tests. T45 now has real chunked HTTP
barriers and exact split-transport evidence, no partial headers/body release,
retained one-dispatch usage and durable audit. No product code changed.
Nine-page EN/PL PDFs rendered with pinned Marp4.5.1; changed slides inspected.
