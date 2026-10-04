# Login-free console on a trusted computer

This opt-in mode grants local operator authority to processes running on the same
trusted computer. Origin checks protect browser requests; they do not identify a
person or separate authority from other local OS processes. Use credential mode
for remote/enterprise access. This feature adds no SSO, four-eyes control, delegated
agent permission, or semantic enforcement capability.

From the checkout, create a private installation with four free distinct ports:

```sh
./laya install --state-dir /absolute/private/laya-console \
  --port 18080 --proxy-port 14000 --worker-port 18091 --collector-port 18095 \
  --semantic off --local-console
```

Open `http://127.0.0.1:18080/`. The packaged console first discovers its mode and
then restores a valid cookie or opens one bounded local session. It shows
**Local console / trusted computer** with no credential-entry or sign-out screen.
The normal local-generation prerequisite remains the pinned Ollama model, but no
inference is needed to use document, scoped-tool, policy, and audit views.

Omitted flags on new/old installations mean credential mode. Reinstall remembers
an explicit choice along with ports; restart uses the remembered configuration.
Stop the owned installation before changing modes or upgrading:

```sh
./laya stop --state-dir /absolute/private/laya-console
./laya install --state-dir /absolute/private/laya-console --no-local-console
```

This is the deliberate off switch. Omitted mode flags subsequently retain
credential mode. No key rotation, credential renewal, epoch reset, policy rollback,
or budget reset occurs. Keep private credentials, database and migration backups.
Old binaries ignore the additive installation field and serve credential mode;
stop first and follow the existing database/credential rollback restrictions in
`BACKWARD_COMPATIBILITY.md`. Disabling bootstrap does not revoke a still-valid
operator cookie; the existing server-side session revocation and 15-minute expiry
remain available. A session itself never confers agent API authority.

## Server and browser contract

`agentgate serve --local-console --port 18080` is the lower-level equivalent with
an initialized operator and private state. It binds `127.0.0.1`, disables Uvicorn
proxy-header trust and requires an exact loopback origin including port. The reusable
`create_app` / `attach_admin_routes` adapters default `local_console=False`;
enabling it requires `serving_address=(literal_loopback, port)` and matching
`admin_origin` / `origin`. Embedders must disable forwarded-header trust on the
actual server. Only canonical `127.0.0.1` and `::1` with explicit ports 1024–65535
are supported; `localhost`, aliases, remote/wildcard binds, userinfo, URL suffixes,
and mismatched schemes/ports fail configuration validation. The admin boundary
also checks the actual ASGI serving address/scheme and rejects forwarded headers.

- `GET /admin/config` publicly returns only `{"mode":"credential"}` or
  `{"mode":"local"}`, with no administrative state or secrets.
- Local-only `POST /admin/session/bootstrap` accepts exactly the empty JSON object
  (1024-byte ingress bound). GET, query arguments, malformed/extra data, duplicate
  security headers/cookies, missing/null/foreign Origin, wrong Host/port, forwarded
  headers and cross-site/same-site Fetch Metadata are rejected.
- A valid previous cookie is reused without extending expiry. Otherwise a session
  uses the existing 900-second expiry and 32-session ceiling. The response contains
  only session metadata/CSRF nonce and the existing HttpOnly, SameSite=Strict,
  `/admin` cookie (Secure on HTTPS); no operator or agent credential is returned.
- Existing sessions, revocation and CSRF checks protect policy/feed changes,
  approvals, playground and export. Approval actors are recorded as `local-console`
  in local mode; this is trusted-host authority, not a verified individual.
- Startup/expiry recovery attempts one restore and at most one bootstrap on 401.
  Failure shows a sanitized service/retry screen without credential input. A retry
  button or reload starts a deliberate new attempt. Failed actions or changes are
  never replayed; review current state before retrying. Agent/playground credential
  renewal still requires its separate explicit action.

## Verification

`make validate` covers default credential behavior, loopback/session/CSRF negative
boundaries, storage effects and installation persistence; Node request/state
contracts are also run through `tests/test_web.py`. For owned installed QA:

```sh
.ai/scripts/test-env-up.sh --local-console
uv run --locked --with playwright python tests/frontend/local_console_check.py \
  --descriptor .ai/qa/test-env.json --artifacts .ai/qa/artifacts_local_console
.ai/scripts/test-env-down.sh
```

The descriptor supplies the installation URL/state and the app is rebuilt as a
non-editable wheel. Browser evidence asserts startup without credential flash,
visible decisions and real audit/outbox effects, denied paths with zero forbidden
effects, expiry recovery without mutation replay or credential renewal, failure/retry,
keyboard navigation and narrow layouts. Artifacts are ignored. These are functional,
integration and E2E control checks; neither classifier fixtures nor this suite are
real-model evaluation. Independent auth/UI review and QA are required before merge.
