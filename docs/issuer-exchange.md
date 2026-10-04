# Optional pinned issuer person-token exchange

`POST /v1/authority/exchange` exchanges one issuer-specific person access token
for a short-lived delegated agent credential. This is an optional IAM adapter,
not browser login or a generic OIDC person verifier. Existing local-console and
credential-console modes remain available. Absent trust configuration denies
exchange; legacy agent credentials retain their existing behavior.

The exchanging client authenticates with an existing **exact permitted parent
credential**. Send only `{"access_token":"..."}` in bounded JSON with its agent
Bearer header. Never put tokens in URLs. The response returns `token`,
`expires_at`, and `token_type: "Bearer"` once, with `Cache-Control: no-store` and
`Pragma: no-cache`. The operator UI does not issue or retain this secret. Denials
use content-free `EXCHANGE_DENIED` (401), `EXCHANGE_LIMIT` (429), or
`EXCHANGE_UNAVAILABLE` (503); malformed transport may return 413/415/422/408.

## Public trust import

Use the trusted, local operator command after initializing/migrating the database
and activating a delegation policy. The configuration contains only public trust
material; never place private key parameters in it.

```sh
agentgate --state-dir <private-data> import-issuer-trust \
  --config-file <reviewed-public-trust.json> --expected-generation 0
```

[The public placeholder example](../config/issuer-trust.example.json) is a template,
not an operational issuer. Replace its public RSA modulus, exact parent digest,
agent/tenant/client relation, audience and mappings. Group roles must reference
existing approved delegation profiles. Configuration is bounded to 64 KiB, eight
issuer profiles, eight unique RSA keys per profile, and 32 parent/tenant/group
mappings per profile. Keys are public RSA 2048–8192 bits with exponent 65537,
RS256 and verification-only key operations. Unknown/private JWK fields fail
validation. Profiles use unique exact issuers and IDs.

Every import uses compare-and-swap and increments the **whole trust generation**.
All prior issuer children become invalid immediately, even if their key remains
present. Disable a profile or import `{"version":1,"profiles":[]}` to turn it off.
There is no key discovery, network JWKS fetch, redirect, `jku`, `x5u`, embedded
JWK, algorithm fallback or caller-selected issuer profile. A token issuer/kid
only selects a pinned local verification key. Stop serving before upgrades or
rollback; never mix binaries against one authority database.

## Exact assertion profile

This first version selects RS256 and exact header `typ=at+jwt`. Header members
are exactly `alg`, `typ`, `kid`; duplicate/non-JSON members and excess nesting
are denied. Payload members are exactly `iss`, `sub`, `aud`, `exp`, `iat`, `nbf`,
`auth_time` and the configured person/client/tenant/group claims. These are all
mandatory. Choose exactly one client claim name, `client_id` or `azp`; there is no
fallback. The default signed discriminator is `idtyp=user`. Valid application or
client-credentials JWTs with another discriminator cannot represent a person.
This claim convention is an administrator-selected IdP profile, not a claim about
all OIDC providers. Claims outside this profile require a separately reviewed
contract extension.

Audience is one exact dedicated string, never an array. Numeric dates are finite
integers in 0..253402300799; booleans, floats and numeric strings are denied.
`iat`, `nbf` and `auth_time` may be at most the configured 0–5 seconds ahead of
server time. `auth_time` cannot exceed `iat` by more than that skew. Expiry and
freshness are strict; skew never permits issuance or use of an expired child.
Groups are distinct strings, at most 32, and every group/tenant must map exactly.
All mapped groups must agree on one configured department. Authorization still
intersects human profile, agent profile, immutable issuance ceiling and the current
core policy. No signature or semantic classification grants permission alone.

JWT UTF-8 bytes are capped at 16 KiB, exchange JSON at 17 KiB, JSON nesting at four,
claim objects/arrays at 32 entries, strings at 512 bytes (groups at 256 bytes).
Duplicate JSON members, NaN/Infinity, malformed signing/claims and unknown mappings
fail closed. Required claims and signature/issuer/audience checks use pinned
PyJWT 2.15.1; strict time checks use the gateway clock, sampled again after acquiring
the write lock. PyJWT crypto and cryptography are explicit direct dependencies.

## Identity, refresh, revocation and admission

Canonical subject ID is `issuer-` plus SHA-256 of the ASCII JSON pair `[issuer,sub]`
with length-safe delimiters. No case/Unicode/URL normalization merges principals.
Raw issuer/sub/JWT/claims are not persisted in human records or audit. The public
trust snapshot necessarily contains the configured issuer and public mappings.

Issuer records use explicit version 2. Local `HumanSubject`, `DelegatedBinding`,
attribution, consent and digest bytes remain version 1 and are unchanged. Shared
`parse_human`/`parse_binding` helpers understand both versions. V2 audit attribution
uses safe configured `issuer_id` and `trust_version` with the existing human,
department, revision and accounting fields. Audit export-v1 retains its exact
projection and omits authority extensions.

A separate assertion-order table tracks the maximum `iat`. An unchanged mapped
profile preserves human revision, human assertion cap and consent bytes. Older
unchanged assertions may issue only within their own remaining bounds; the ordering
watermark never moves backwards. Older or equal-time **conflicting** authority is
denied. Newer changed tenant/roles/department increments authority revision,
invalidating old children. Each child keeps its own immutable assertion expiry and
freshness: minimum of `exp`, `iat+max_assertion_age`, `auth_time+max_auth_age`, parent
expiry, child lifetime and any stable person-level cap. Lifetime/maximum assertion
age are at most 300 seconds; maximum authentication age is at most 3600 seconds.
Refresh never extends old children.

Trusted `revoke-human --subject <opaque-id> --expected-revision <n>` creates a
revocation tombstone. Exchange never clears it. Parent revocation and missing,
disabled or changed trust generation are enforced at entry and again in the
owning document/memory/model/approval dispatch transaction. A committed dispatch
remains the existing revocation boundary. Upstream IdP revocation is not
introspected: an otherwise-valid assertion can remain usable until its short
freshness/expiry window, unless the operator revokes the human/parent or changes
trust first. Remotely exposed gateway deployments require authenticated TLS and
separate privileged admin protection; the supplied CLI intentionally accepts only
an explicit loopback HTTP origin.

One `BEGIN IMMEDIATE` owns parent/policy/trust revalidation, admission, human refresh,
child/binding creation and issuance audit. A fresh post-lock clock rejects
lock-wait expiry. A savepoint rolls back human/child mutations on business denial,
then commits only bounded admission and a minimized denial audit. Storage/audit
failure rolls back the whole transaction, including admission. No token is released
before issuance audit commits.

Per parent, defaults are eight active children, 128 total durable child rows and
128 exchange admissions per UTC day. Caps are explicit configuration fields;
maximums are 64 active, 4096 durable children and 4096 daily admissions. All
one-hop children count toward exchange growth caps, including expired/revoked
rows; this deliberately bounds lifetime growth without deleting consent/audit
references. Admission uses one row per parent, reused each day, and is not reset by
trust imports. Invalid verification and valid-but-denied assertions consume the
same cap. Preflight avoids verification after observed exhaustion; concurrent
requests can verify before the transactional counter reaches its limit. The
transaction bounds admitted outcomes and child growth, not requests per second or
perfect prevention of concurrent verification work.

## Local integration and evidence

```sh
agentgate exchange-person-token --gateway http://127.0.0.1:<qa-port> \
  --parent-token-file <private-parent.token> \
  --access-token-file <private-person-access.token> \
  --output-token-file <new-private-child.token>
```

The output file is created once with mode 0600 and refuses overwrite. A file/write
or client disconnect after successful HTTP issuance cannot undo the committed
child; it expires under its original limits. Use the new file with existing
`agentgate-agent` REST/MCP or pinned `agentgate-hermes` adapters. Retain private
input token files only as long as required; they are never operator UI state.

Reproduce installed QA with:

```sh
AGENTGATE_HERMES_SOURCE=<prepared-pinned-hermes> \
  uv run --locked python scripts/issuer_exchange_smoke.py
```

The script owns this checkout's `.runtime/qa-install`, uses its non-editable wheel
and supervisor, substitutes an authenticated **provider fixture** in its private
provider slot, exercises exchange-to-installed direct REST, direct MCP and actual
pinned Hermes model/tool/model cycles, exact outbox approval/replay, audit rollback
and trust-revocation nondispatch, and stops only owned QA in `finally`. It restores
policy/trust at newer audited revisions and retains minimized ignored evidence.
Shared Ollama, primary8080, the normal user installation and other QA worktrees are
untouched. Generated keys and input/child token files are ephemeral/private.

`tests/test_issuer_exchange.py` separates unit (`test_unit_*`), functional
(`test_functional_*`) and integration (`test_integration_*`) cases. These generated-key
crypto/wire/provider fixtures prove deterministic enforcement and rollback; they
are not a corporate SSO deployment certification or real-model evaluation. The
installed smoke is separately executed E2E evidence. Root supplies independent
high-risk review and integration/CI approval; author QA does not authorize merge.
