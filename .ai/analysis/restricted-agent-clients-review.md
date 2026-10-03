# PR30 author review — restricted agent clients

Scope: E03-S02 / #14, original architecture and full-stack delivery spec. Review
uses om-code-review, CODE_REVIEW.md and BACKWARD_COMPATIBILITY.md. This is an
author review, not independent release approval. No extra agents or merge.

## Boundary checked

- New direct and pinned upstream Hermes clients consume the existing gateway.
  No gateway policy implementation, identity issuance, renewal, spend reset or
  approval API is introduced. Explicit aliases are intersected with discovery;
  per-request permissions and root identity remain server-owned.
- Direct CLI preserves inspected assistant proposals, complete action responses
  and tool IDs. Bounded turns, sizes, deadlines, one call per response, duplicate-ID
  rejection and explicit pending-state binding stop replay/fallback behavior.
- Hermes actually imports the verified upstream source and invokes AIAgent's
  conversation loop and MCP handlers in its separate locked environment. Active
  registry checks exclude native tools and Tool Search. Private home, clean env,
  disabled dotenv/memory/context/auxiliary features, fixed model transport and
  Python network/process guard narrow the profile. Native same-user host access
  is outside the boundary; this is not an OS sandbox.
- Failed model dispatch is latched; SDK retries and upstream recovery are disabled.
  Pending/denied MCP results escape the loop. Explicit post-approval reinvocation
  retains gateway idempotency and root spend; no operator credential enters Hermes.
- Public changes are additive CLI entries and modules. Existing gateway contracts,
  semantics defaults and persistence schemas are unchanged. Hermes dependencies
  remain separate; upstream MIT source and lock hashes are recorded.

## Findings fixed and rechecked

Failure diagnostics originally discarded Hermes correlation evidence. Minimized
trace/argument-shape evidence now survives without arguments or content. Model
protocol errors latch closed; malformed JSON, redirects and repeated IDs have
regressions. Direct pending files validate their structure/binding before requests.
Both CLI run paths discard inherited credentials. Private files reject symlinks,
public permissions and invalid text. Smoke reports cannot overwrite prior attempts.

The destination-denial fixture previously could stop at model email redaction.
It now explicitly permits unredacted routing in that fixture so the real gateway
recipient allowlist is exercised; exact persisted reason codes are asserted for
every scenario. New malformed-schema argument regressions reproduce the real
small-model failure through REST, MCP and actual upstream Hermes, asserting zero
effect and no second model call. No assertions were weakened.

## Evidence and limits

See docs/restricted-agents.md for actual local-generation call IDs, trace IDs,
source versions, report hashes, cumulative spend and all five failed development
attempts. Final direct REST/MCP and genuine Hermes each completed two model calls
and one fixture document read. Semantic inspection was disabled; these are not
Laya enforcement/quality results. Approval/outbox evidence uses a deterministic
provider and synthetic local mail, not actual mail delivery. Final make validate passed574 tests with10 explicit optional upstream skips;
Ruff,strict mypy and source/wheel builds passed. Prepared upstream client suite
passed55 tests including all10 actual Hermes subprocess scenarios.

No remaining blocking/major finding in this author pass. Independent release
review remains required before merge; this task does not grant it.
