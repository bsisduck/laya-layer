# Laya Sec Layer operator dashboard

The gateway serves its credential-free shell at `/` and packaged ES modules/CSS
at `/static/`. The wheel includes every asset; installed use needs no Node,
frontend build, CDN, external fonts or network connection. Static routes do not
shadow missing `/admin` or agent endpoints. Only authenticated admin APIs supply
data and execute actions. This UI never makes an enforcement decision.

## Start and operator access

After integrating the control-plane story, the existing Python CLI is sufficient:

```sh
uv sync --locked
uv run agentgate --state-dir .agentgate init-demo
uv run agentgate --state-dir .agentgate init-operator --policy config/policy.yaml
uv run agentgate --state-dir .agentgate serve --port 8000
```

Run initialization once in a new private directory. Open `http://127.0.0.1:8000`
and enter that installation's private `operator.token` through the password field.
Do not put the credential in a URL, screenshot, console, or agent configuration.
An agent credential cannot log in. For another origin, configure the control
plane's exact `--admin-origin`; loopback HTTP is local-only.

**Integration status:** this frontend branch does not implement operator APIs.
The CLI's `init-operator` and admin attachment arrive with control-plane PR17.
On a document-only backend the login screen reports the missing API. Model routing
(PR6) and scoped tools (PR19) must be attached by their owners before their live
playground/approval flows can run. No placeholder server responses are installed.

## Operator flows

- Overview reports API counts, their bounded audit window, active versions, service
  state, coverage and ledger counters. A dash means unknown; no security score or
  real-model result is inferred. Budget units and raw reported evidence remain visible.
- Timeline filters the latest 100 records by decision and trace, operation, tenant,
  principal or reason. Expand an event for minimized evidence. Intent and completed
  events remain distinct; execution is only claimed for `executed: true`.
- Playground provides editable document, model, memory and mail presets. Presets
  are requests, not promised results. Denials retain their actual action evidence.
  Missing/unavailable services show errors without fabricated results. Model alias
  `local-demo` is an editable example and must match the active model policy.
- Policy studio validates against the server. Policy/feed activation requires a
  before/after review and an explicit checkbox. The posted `expected_version` is
  the version loaded with the document, never a freshly fetched replacement. A
  409 keeps the draft visible; refresh and reconcile. Increase the revision; JSON
  drafts are bounded to 64 KiB. Feed validation occurs with atomic activation.
- Approvals show the exact stored mail payload, identity/root, expiry, fingerprint
  and policy/registry/payload digests. Approve/reject sends the original fingerprint.
  **Approval is not execution.** To execute a playground mail action after approval,
  return to Playground and repeat the unchanged payload and idempotency key. Drafts
  survive navigation only in this session's memory; reload/lock discards them.
- Outbox shows bounded metadata for a selected tenant. `fixture` is a local test
  effect, not SMTP delivery. Audit export downloads one selected tenant or
  unattributed page; use the returned high-water and cursor for subsequent pages.
  `has_more: true` explicitly means the export is incomplete.

Cookies are HttpOnly and owned by the backend. The browser retains only its CSRF
nonce and in-progress drafts in memory. Lock/401/expiry removes privileged DOM,
clears drafts/nonce and invalidates pending requests so late responses cannot
unlock or refill the workspace. A failed logout reports that revocation was not
confirmed. State-changing network failures report an unknown outcome and are not
automatically retried. All API content is inserted as text; no HTML content sinks.

## Consumed contracts

The source of truth is `docs/control-plane-contract.md` (PR17) and
`docs/scoped-tools.md` (PR19). Browser consumers use:

| Route | Request / consumed response |
| --- | --- |
| `/admin/session` | POST `{token}`, GET introspection, DELETE logout; `authenticated`, `csrf_token`, Unix `expires_at` |
| `/admin/overview` | Counts/window, versions, controls, services, coverage, latency, budgets |
| `/admin/events?limit=100` | `{events, control_events}` |
| `/admin/policy`, `/admin/feed` | Versioned `{policy,version}` / `{feed,version}` |
| `/admin/policy/validate` | POST `{policy}` → `{valid,version}` |
| `/admin/policy/activate`, `/admin/feed` | POST `{policy|feed,expected_version}` |
| `/admin/playground` | POST discriminated body below → ActionResponse or model object with `agentgate` evidence |
| `/admin/approvals?tenant_id=…&limit=100` | `{approvals}` with immutable payload/digests/state |
| `/admin/approvals/{action_id}/decision` | POST `{tenant_id,fingerprint,approve}` → ActionResponse; no execution inferred |
| `/admin/outbox?tenant_id=…&limit=100` | `{messages}` metadata |
| `/admin/audit/export` | GET selected scope/format/cursors/limit → NDJSON and `X-AgentGate-Cursor` |

Playground bodies have no client-owned identity:

```text
document: {mode:"document",document_id}
memory:   {mode:"memory",query,limit}
mail:     {mode:"mail",recipient,subject,body,idempotency_key}
model:    {mode:"model",model,messages,max_tokens}
```

The model body is the consumer contract for root's `/admin/playground` binding;
it must route through the real `ModelService`. The mail binding must retain one
stable private credential through proposal/approval/retry. Frontend code cannot
repair one-off server credential deletion. These integrations belong to backend
owners, and their E2E proof must be reported separately.

## Verification and reproduction

`make validate` includes `tests/test_web.py`: public routing and traversal boundaries,
security headers, ES syntax, unsafe-sink checks, Node built-in request/state tests,
and real wheel/source asset inclusion. Node is a repository test tool only.

Browser scripts require separately installed Python Playwright + Chromium. They do
not add a product dependency or run inference. Use the documented `webapp-testing`
helper (`with_server.py --help` first) or start this disposable server explicitly:

```sh
uv run python tests/frontend/serve.py --state-dir .runtime/dashboard-qa --port 8765
python3 tests/frontend/browser_components.py --url http://127.0.0.1:8765
```

`browser_components.py` intercepts admin requests with **mocked component data**.
It tests loading/empty/error/401/503, payload text safety, exact approval bodies,
CSRF consumption and mail draft/key preservation. It is not enforcement evidence.

For full product verification, prepare an isolated **installed** application:

```sh
.ai/scripts/test-env-up.sh
uv run --locked --with playwright python tests/frontend/browser_check.py \
  --url <baseUrl-from-.ai/qa/test-env.json> \
  --state-dir <stateDir-from-descriptor>/data \
  --artifacts .ai/qa/artifacts_fullstack
.ai/scripts/test-env-down.sh
```

Install Playwright Chromium separately if needed. The suite asserts document and
memory isolation, exact approval/one outbox effect/replay, explicit renewal,
live policy/feed activation, scoped exports, sessions and 390/768/1440 layouts.
It temporarily changes controls and a QA-owned credential, then restores controls
at newer audited revisions; it retains effects and budgets. Use the isolated QA
state, not an unrelated operator installation. Add `--model` to exercise the real
configured provider in an exclusive inference slot. Model observations are written
separately from the common delivery/latency report.

The historical control-plane-only browser baseline used backend PR17 commit
`90b262da16df628471d9c83491b1ee9c89bd9c4b`. The current expanded suite requires
the installed full stack; the old development harness is only for component QA.
Screenshots and runtime data stay ignored; never publish credentials or databases.

Accessibility uses semantic headings/forms/tables, explicit labels, keyboard focus,
a skip link, scrollable table regions, live status announcements, reduced-motion
support, local font fallbacks and mobile navigation. Screenshots do not substitute
for independent release accessibility/security review.

## Installed release QA

The source-prepared installation at `b740c35` passed the complete browser suite
with `--model`: actual memory/mail/renewal/control/export/session/layout checks,
one SQLite outbox effect under replay and local collector receipt/lag assertions.
The local generation used one attempt and 118 tokens; input secret denial made
no attempt. See [release evidence](release-evidence.md) for exact source, timings
and limits. Mocked UI consumers, installed integration and real semantic accuracy
remain separate evidence classes.

See [two-axis threat evidence](threat-model.md) for the authored L0–L5 ladder, exact seven
layers, strict frozen-corpus sidecar and unknown live-level contract. The taxonomy
adds classification/evidence presentation, not new enforcement or inference results.
