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
