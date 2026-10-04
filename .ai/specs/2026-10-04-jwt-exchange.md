# Optional person-token exchange for delegated authority

Implement after the delegated-authority core is accepted. This fulfills the IAM
integration requirement without inventing a corporate login or weakening local
no-login mode. Use the SAME persisted human/parent/child authority resolver and
approval/accounting invariants. No new trust inferred from a valid signature alone.

## Issuer profile and exchange

Administrator imports bounded PUBLIC trust configuration into a versioned/CAS
snapshot in the private control database: exact issuer, dedicated gateway audience,
allowed asymmetric algorithm (start RS256 only), pinned local JWKS with unique key
IDs, allowed requesting client IDs, typed tenant/group mappings to existing approved
profiles, and an issuer-specific person-token discriminator. No token-controlled
URL, jku/x5u discovery, redirects, network JWKS fetch or fallback algorithm.

Require an access-token profile (e.g. typ=at+jwt) AND a configured signed person
claim (e.g. idtyp=user), approved client/azp mapping and authentication-time semantics.
Reject machine/client-credentials tokens even if signature/audience are valid. This
is a specific configured IdP profile; do not claim all OIDC providers use these
claims or that generic JWT verifies a person. Issuer subject pairs are authoritative
identity; normalize to safe opaque internal IDs, retaining only minimized provenance.

Verify mandatory iss, sub, aud, exp, iat, nbf/auth_time as explicitly selected by the
profile; no missing-claim implicit pass. Exact dedicated audience policy, maximum
assertion age and child lifetime, finite bounded integer time types (no booleans),
small documented clock skew; malformed/unknown/unmapped claims fail closed. Enforce
bounded UTF-8 JWT/body/key/claim arrays and sanitized denial. PyJWT/cryptography are
already in the lock; add an explicit runtime dependency if importing them. Follow
pinned library validation API and require claims, never decode without verification.

POST exchange authenticates an existing permitted agent credential and accepts the
human access token in bounded JSON; no arbitrary identity/department/issuer/group
claims outside the token. The resulting child cannot exceed either authority, its
issuance ceiling, parent/assertion expiry or the core lifetime cap. Issuance writes
subject/binding/credential atomically only after parent/subject/policy/trust snapshot
revalidation inside BEGIN IMMEDIATE. Concurrent trust/key/policy changes invalidate
verification against old snapshots; no stale-verified token is issued. Trust changes
also affect existing children according to a documented fail-closed generation
binding; revocation remains immediately enforced by the core resolver.

Bound active child creation and exchange admission per parent to prevent unbounded
credential growth; include explicit policy/config limits and test exhaustion without
new tokens/rows. Never log raw tokens, include them in URLs, persist plaintext JWTs
or expose signature diagnostics. Response may return the new child secret once to
the authenticated exchanging client; mark it non-cacheable. Do not surface it in
operator UI/storage. CLI writes it privately when used in local integration.

## Verification and limits

Use generated ephemeral fixture signing keys and actual exchange-to-REST/MCP/model
requests to prove broad/narrow intersections, before-read denial, model nondispatch,
parent/human/key-policy revocation, malformed/wrong-alg/key/issuer/audience/purpose/
client/time/group/tenant claims, mandatory-claim rejection, machine-token rejection,
configuration race, limits, rollback and sanitized audit. Preserve budget identity,
legacy credentials/approvals and normal local/credential console modes.

Provide configuration examples with public placeholders and a reproducible fixture
integration script. Unit, functional, integration and E2E verification must be
reported separately. No corporate tenant is available: clearly report fixture wire/
crypto evidence, not SSO deployment certification. Document key rotation, short
assertion freshness, upstream IdP-revocation window and remote TLS requirements.
No browser OAuth authorization-code flow is claimed by this adapter.

Primary references (verified during design review):
- https://www.rfc-editor.org/rfc/rfc9068.html (application subjects are possible)
- https://pyjwt.readthedocs.io/en/stable/api.html (required-claim enforcement)
- https://pyjwt.readthedocs.io/en/stable/usage.html

Follow one issue/branch/draft PR, Open Mercato review/integration/check-and-commit,
make validate and actual installed owned QA; root independent high-risk review.
No primary/shared service changes, secrets/artifacts commits or author merge.
## Independent design review resolutions (authoritative)

Review 2b515b65 identified two blocking shared-schema contracts. Apply these to
the accepted core; do not change version-1 local binding serialization/digests.

- Use one canonical collision-safe subject ID for exact `(issuer, sub)`, for
  example a fixed prefix plus SHA-256 of a canonical length-safe JSON pair. No
  per-token subjects or identifier normalization that merges distinct principals.
- Add explicit versioned issuer-asserted human/binding variants. Existing local
  records and consent bytes remain unchanged. Bind issuer profile, exact signed
  client claim, permitted parent/agent+tenant relation and current trust generation.
  Configure one client claim name; no interchangeable `client_id`/`azp` fallback.
  Check missing/disabled/mismatched trust in the shared admission AND transactional
  dispatch/resume resolver, including already-issued children.
- Keep human authority revision stable for unchanged roles/department/tenant/
  revocation. Keep any person-level assertion cap stable. Each JWT child separately
  retains its immutable assertion expiry/freshness bound; a refreshed token never
  extends old children. Child expiry is at most parent expiry, assertion bounds
  and 300 seconds. Local v1 deadline equality remains compatible.
- Maintain an assertion-order watermark separately from authority revision.
  Reject stale conflicting profiles and equal-time conflicting assertions;
  unchanged refresh preserves existing children within their original limits.
  Authority changes increment revision and invalidate old children. Exchange
  never clears a revocation tombstone, even with a newer signed token.
- Subject refresh, admission limits, exact parent recheck, child+binding creation
  and issuance audit use ONE owning write transaction. Refactor bounded internal
  transaction helpers where necessary; do not call the separately committing
  provision_subject followed by issuance. Recheck assertion validity with a fresh
  clock AFTER acquiring the write transaction so lock/verification delay cannot
  issue an expired token. Audit failure rolls back all authority changes.
- Add concurrent unchanged/changed refresh, stale/equal-time conflicts, subject
  revocation, trust generation change, lock-wait expiry, rollback and local-v1
  migration/consent compatibility tests. Valid application JWTs remain rejected
  by the configured person-token profile.
