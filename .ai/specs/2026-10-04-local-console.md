# Login-free local console

The user explicitly confirmed: presentation AND the whole local application
without a login screen, retaining the current visual style. Implement this as an
explicit trusted-installation capability, independently of delegated authority.
This contract incorporates design review 87777afc's local-console findings.

## Contract

- Add a lifecycle installation option `--local-console` (and deliberate inverse
  if needed) persisted in the owned versioned installation metadata. New omitted
  options and existing installations remain credential mode. Reinstallation
  preserves the remembered choice, credentials, epochs, controls and budgets.
  User's primary installation will be explicitly enabled by root after review.
- Plumb an optional default-false server configuration to admin routes. It is
  permitted only for actual loopback serving and exact loopback origin. Refuse
  remote binding/origins, forwarded-header trust and unsupported host forms;
  install/serve validation must establish this, not just a UI message.
- A public minimized configuration route can report credential/local console mode,
  but no secret, token or administrative state. The UI uses it to avoid flashing
  the credential form in local mode.
- In local mode only, a bounded POST bootstrap accepts exactly `{}`. It creates
  the existing operator session, setting only the existing HttpOnly/SameSite cookie
  and returning session metadata and the in-memory CSRF nonce. No key/token in
  HTML/JS, URL, local/session storage, logs or screenshot. Normal credential mode's
  existing login and negative agent-credential tests remain unchanged.
- Use exact Host and Origin (scheme, host, port), reject missing/null/foreign Origin,
  duplicate security headers, different ports and DNS-rebinding hosts. Reject GET
  bootstrap and cross-site Fetch Metadata. No wildcard CORS, remote enabling or
  trusted proxy bypass. Same-user OS clients are explicitly trusted in this mode;
  Origin is a browser-origin boundary, not authentication of a person.
- Preserve session expiry, server revocation, SameSite and CSRF enforcement for
  policy/feed/approvals/playground/export. Session bootstrap does not execute an
  action or renew any agent/playground credential. Never change existing operator
  tokens or lower agent API authentication to get the demo working.
- Automatic startup/expiry restoration is bounded (one attempt), uses existing
  cookie/session state and does NOT automatically replay a failed mutation.
  An expired action must be reviewed/retried deliberately; renewal of a session
  is not approval. Avoid retry loops on 401/outage. Failed local startup shows an
  actionable service/retry state, never a credential input. Manual reload remains
  possible. Local mode has no login/logout/lock credential UI; clearly label it
  Local console / trusted computer, retaining existing styling.
- Record approval actor mode honestly if necessary: local authority is not a
  verified individual human or separation from other same-host processes.
  Do not claim enterprise SSO or four-eyes controls. Credential mode remains the
  recommended remote/enterprise boundary, which this local mode cannot enable.

## Required evidence and delivery

Read AGENTS/SDLC/BACKWARD_COMPATIBILITY and use applicable Open Mercato implementation,
integration, check-and-commit and review instructions. Scope one issue and draft PR
from fresh origin/main, explicit user publication authorization persists. Working
commits are automatic. Author does not merge; root independently reviews auth/UI.

Test default-disabled mode, real local bootstrap cookie/session/CSRF boundaries,
malformed/oversized/extra bodies, duplicate headers, missing/null/foreign Origin,
rebinding Host, wrong ports, cross-site Fetch Metadata, GET, invalid serving config,
normal credential flow and agent API auth. Prove expired-session restoration never
replays approval/action/policy writes; no agent credential renewal occurs. Exercise
persisted install config upgrade/reinstall/restart and backward defaults.

Run make validate plus relevant JS and installed Playwright tests in an owned
private QA installation. Actually install the wheel with local mode and open it
in a fresh browser context: no credential form at startup, working overview and
navigation, one deliberate demo action, no tokens in DOM/browser storage, narrow
and keyboard interaction, sanitized failure and expiry restoration. Preserve audit
and side effects, teardown owned QA finally, do not touch primary8080/sharedOllama.
No heavyweight inference is required. No generated QA/PDF artifacts in commits.
Document exact installation command, deliberate host trust and rollback/off switch.
Final report: exact head/issue/draft PR, checks/limits/QA evidence/teardown.
