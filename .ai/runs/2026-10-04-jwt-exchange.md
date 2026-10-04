# Pinned person-token exchange

Source doc: .ai/specs/2026-10-04-jwt-exchange.md

Goal: exchange a configured issuer person access token for a short-lived child of an existing permitted agent credential, using the shared persisted resolver.

Scope: versioned issuer records, bounded pinned RS256 trust/CAS, exact parent/client/tenant mappings, atomic refresh/admission/issuance/audit, additive HTTP and private CLI, generated-key tests and installed adapter QA. Preserve local v1 bytes and consent, accounting and old approvals.

Risks: authority and trust races, assertion ordering, rollback, bounded growth and unchanged refresh consent. Root independently reviews high-risk changes. First push/draft PR held until root supplies final integration base; no author merge. No department views, HR, deck or real model inference.

## Implementation Plan

1. Establish versioned records/shared decoders and trust generation contract.
2. Implement verification, atomic exchange, HTTP/CLI and limits.
3. Prove unit/functional/wire/concurrency/rollback/compatibility behavior.
4. Run installed owned adapter QA and full gate; review and report ready head.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Contracts and implementation

- [x] 1.1 Establish shared issuer contracts without changing local v1 bytes — 04c1f29
- [x] 1.2 Implement bounded pinned verification and atomic exchange — 0470908

### Phase 2: Evidence and handoff

- [x] 2.1 Verify generated-key behavior, concurrency, rollback and compatibility — 0470908
- [x] 2.2 Verify installed adapters, full gate and code review
- [x] 2.3 Report ready local head and await final integration base before publication

## Local review and verification

Verdict: approve for local handoff. No unresolved blocker/major found in the
author review against CODE_REVIEW.md, BACKWARD_COMPATIBILITY.md and the complete
spec. This does not authorize merge: root's independent authentication review,
installed QA, final integration base and green CI remain required.

| Check | Result | Evidence |
| --- | --- | --- |
| Prepared-Hermes `make validate` | PASS | 942 tests in 124.85s; workflow/Cezar config, lock, Ruff lint/format, strict mypy and source/wheel packaging |
| Issuer unit cases | PASS | 5 collected cases; exact pair identity, concurrent refresh, lock expiry and local v1 bytes |
| Issuer functional cases | PASS | 57 collected cases; generated-key signed claims, malformed JSON, tombstones, caps and consent |
| Issuer integration cases | PASS | 22 collected cases; MCP wire, document/memory/model/approval dispatch races, audit rollback, admission and export-v1 |
| Installed E2E | PASS | Owned non-editable wheel: direct REST, direct MCP and actual pinned Hermes each dispatched one protected document read and two provider-fixture calls; one approved fixture outbox row with replay; complete authority/admission/audit rollback; trust-revocation nondispatch |
| Root admission reproduction | PASS | Root independently reran unchanged quota reproduction plus 83 issuer cases at 0470908; concrete finding resolved, final approval pending |
| Real semantic/model evaluation | NOT RUN | No heavy inference; all provider output above is explicitly a fixture |

The full gate initially found the installed runner replacing an already-loaded
package during in-process imports. Separate Hermes commits b4496e8/af552b0 expose
only agentgate through a package file spec and preserve an existing package. No
sys.path/site-packages injection, Hermes pin/runtime or gateway SDK version changes.
Both installed/pinned dependency regressions and an existing-package regression
pass. Earlier failed QA fixture attempts remain uncertain budget admissions;
the bounded temporary QA policy allowed subsequent verification without resetting
usage and was restored. QA stopped in finally, all ephemeral token files removed.
Ignored reports/logs remain under `.ai/qa/artifacts_issuer_exchange/`; generated
keys, runtime state, build output and reports are not committed.

Shared surfaces are additive issuer-v2 human/binding/attribution variants and
versioned parsers. Local-v1 serialization/consent and audit export-v1 keys are
unchanged. Migration adds issuer sidecars; old binaries must not serve the upgraded
authority-bearing database. Root relayed safe issuer_id/trust_version names to the
parallel department/HR consumers; integration with their final base remains pending.

## Integrated delivery

Root supplied final main e6ac356 after department PR47 and explicitly released
first-push hold. The six unpublished commits rebased without changes or conflicts;
SHA references above now name rebased commits. Author integrated gate at acbbea6
passed 973 tests/all checks. Root independently passed the same 973 tests with zero
skips, strict mypy over 57 files, full gate/build and owned installed adapter smoke,
then queried six known issuer-v2 department attempts (120 input/18 output tokens).
Root reports no unresolved blocker/major.

Commit 7fbca66 adds only the actual exchanged-child department consumer regression
(passed) and installed minimized report assertion (passed), with no department
runtime changes. Existing reserve attribution callback, atomic settlement,
readiness, report and local v1/export-v1 remain unchanged. Expanded final author
checks precede authorized draft publication; root owns CI acceptance and merge.
