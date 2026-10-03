# Explicit credential renewal contract

Status: implemented and fixture-tested on PR24 /
`feat/operator-credential-renewal`. Installer PR22 consumes the trusted helper.
Model PR6 retains `agentgate.admin.playground_credential(service, model=True)`;
the tools/default call is unchanged. No model execution is added by this change.

## Trusted Python hooks (`agentgate.admin_credentials`)

- `playground_credential(service, *, model=False) -> str`: retain first-use
  bootstrap and stable internal token, now keyed by durable scope epoch. Epoch
  zero preserves the existing tools/model HMAC derivation. Never auto-renews.
- `playground_credential_status(service, *, model=False) -> dict`: `{scope:
  "tools"|"model", epoch: int, state: "unissued"|"active"|"expired"|"revoked",
  expires_at: number|null}`. Contains no token/digest.
- `renew_playground_credential(service, *, model=False, expected_epoch: int) ->
  dict`: atomic compare-and-swap, only for expired non-revoked current authority.
  Retire the old token, increment epoch, issue a new 24-hour token; return the
  status shape. Same tenant/principal/root/operations, unchanged budget rows.
- `renew_agent_credential(store, token, *, now: float, expires_at: float, persist=None) -> str`:
  trusted operator/installer-only hook. Replace an expired non-revoked credential
  with a fresh random token and the exact stored identity. New expiry must be
  after `now` and at most 24 hours later. Return secret only to the trusted caller.
  No REST/MCP agent renewal/issuance endpoint. Caller must privately persist the
  replacement; serialize renewal with private-file publication and stop serving
  during installer rotation. Optional trusted `persist(token)` runs after replacement
  statements but before COMMIT. The installer fsyncs `client.token.next` and its
  directory there; callback failure rolls back the transaction. Recovery publishes
  only a token matching committed old/new digests, identical identity and non-revoked
  replacement. Uncommitted pending files may be discarded only while the old row
  remains non-revoked and the pending token has no credential row. The default
  callback remains absent for existing trusted callers. Never log or print the returned token.
- `CredentialRenewalError.reason`: `missing`, `revoked`, `active`, `conflict`.
  Invalid bounds/types raise `ValueError`; unavailable durable state raises
  `StorageUnavailable`. No partial epoch/token transition on failure.

## Operator HTTP (existing session/origin/CSRF protections)

- GET `/admin/playground/credential?scope=tools|model` returns the status shape.
  `scope` is mandatory; unknown/duplicate fields reject.
- POST `/admin/playground/credential/renew` body
  `{"scope":"tools","expected_epoch":0}` returns the new status shape.
  Requires `Origin` and `X-CSRF-Token` plus a valid HttpOnly operator session.
  404 missing/unissued, 403 revoked, 409 active/stale epoch. Invalid data 422.
  Success never returns the internal token. Renewal does not execute an action.

Renewal keeps historical rows and marks old authority revoked. Old tokens and
old approval fingerprints cannot authenticate as the new credential. Concurrent
renewals produce exactly one replacement. Restart retains the new epoch; automatic
playground retries continue using that epoch. A failed/replayed renewal cannot
extend expiry. Ledger keys retain the same tenant/principal/root, so accrued
spend and unresolved reservations remain binding. The operator identity itself
and operator session TTL are unchanged.

## Evidence and integration limits

`tests/test_credential_renewal.py` exercises epoch-zero compatibility, separate
chat/tool scope, session/origin/CSRF controls, expiry and revocation, simultaneous
CAS/agent renewals, replay, rollback on renewal-history failure, restart, private
persistence, actual document denial after exhausted root spend, and model denial
after spent/uncertain reservations. `make validate`: 334 deterministic tests pass.

Additional isolated cross-branch QA used PR19 `4d08fe666c8b61615b9105fcce2e939555382ea1`
plus this helper, with no edits to either author's branch: four pending/approved
mail × agent/playground replacement cases pass. New tokens cannot resume the old
action or repeat its old idempotency key (403, zero outbox rows). A fresh key creates
a new proposal; only its new explicit approval permits one fixture outbox effect.
This is deterministic executor/ledger evidence, not SMTP delivery or model inference.
The installer remains responsible for securely publishing/recovering agent token
files; this hook's atomicity covers the credential database transaction only.
