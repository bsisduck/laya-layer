# Approved tool catalog and explainable policy risk

Deliver the catalog portion of the user's action-control requirements independently
of delegated identities. Design review87777afc identified this as a bounded useful
capability. Existing tools documents.read, memory.query and mail.send already
share REST/MCP enforcement; mail requires exact approval and writes a local outbox.

## Behavior

- One immutable, versioned administrator-reviewed catalog for implemented canonical
  tools: effect read/write/destructive, data sensitivity/class scope, reversibility,
  whether it may affect a person, executable adapter/effect scope, and enforced
  authorization/approval disposition. Explain operation-level potential exposure
  separately from a request's actual authorized resource. Never pretend text was
  classified as PII/special categories merely from its tool name.
- A deterministic bounded integer score with explicit named components and a risk
  band, driven by trusted metadata. Document exact formula/version and examples.
  This is a local policy heuristic, not probability, semantic native score, an
  OWASP level, or AI Act legal high-risk classification. No scoring model/inference.
- Catalog metadata is included in a versioned approved registry digest used by
  exact action approval. A changed risk/effect/adapter interpretation invalidates
  stale pending approvals; consumed-action replay acknowledgment remains compatible.
  Explicitly document safe pending-approval reproposal during this registry upgrade
  and test it. Do not rewrite old action snapshots/fingerprints or spend.
- Control order remains hard authorization first, then action policy, then required
  approval, with revalidation before effect. Reads in permitted scope can execute
  automatically; existing mail approval remains mandatory regardless of score.
  Destructive/unregistered effects must deny unless an implemented reviewed executor
  and explicit policy path exists (none is added here). The risk catalog must agree
  with actual enforcement and be consumed by it, not be an unrelated fake UI table.
- Generate outbound MCP annotations only from approved catalog metadata. Untrusted
  client hints/descriptions or tool arguments cannot downgrade effect/risk/approval;
  a client-provided destructiveHint=false never grants execution. Test actual
  adapters with attempted hint/metadata injection, direct undiscovered calls and
  zero forbidden side effects. The gateway is not a generic remote MCP proxy.
- Optionally show non-executable Dev gitlab.merge_main and Finance payments.transfer
  examples in the operator catalog, clearly unavailable/proposed. They MUST NOT
  enter executable REST/MCP discovery and direct calls deny before dispatch. No
  real GitLab/bank credentials, transfer, external merge or fabricated success.
  Merge is consequential under policy, not inherently irreversible; payment
  reversibility depends on the external system. Use careful example wording.

## Product and contract surfaces

Expose the catalog through a protected bounded admin endpoint and a clear Catalog
view in the current style. Show effect, data, reversibility, risk components/band,
approval disposition and actual adapter scope. Existing public /v1/tools response
keys/list remain compatible; MCP additions are standard optional annotations.
Preserve policy, scopes, identity, root budgets, existing action/reason/body/status
contracts, exact approvals/replay and export-v1. No credential/semantic-score/raw
payload exposure. Future identity work consumes this catalog, not a parallel list.
Update BACKWARD_COMPATIBILITY and docs with diagram/limits and actual action policy.
Keep loaded UI metadata safe and handle old/missing/error/empty states, narrow layout,
keyboard navigation. No dependency or login-mode changes are needed for this task.

## Proof and delivery

One scoped issue/branch/draft PR from fresh origin/main; check overlap with taxonomy
issue36 and local-console task but do not duplicate either. Frequent working commits,
Open Mercato integration/review/check-and-commit, make validate + JS. Tests cover
score formula boundary/invalid metadata, canonical alias equivalence, catalog/
discovery/executor consistency, real approval+resume one effect, changed catalog
invalidates pending, consumed replay remains stable, malicious hints/unknown tools
zero effects and protected endpoint. Installed browser QA from a rebuilt wheel
proves the view renders actual backend metadata. Owned isolated QA only, noprimary
8080/sharedOllama/heavy inference. Retain artifacts ignored and teardown finally.
Author publishes validated draft, NO merge; root independently reviews/tests/merges.
