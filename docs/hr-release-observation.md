# HR control evidence and actual semantic limitation

Root observed the installed HR contract at source
`34bf344fcdae9b60c416a34bf0ebbb8953e5e706` on 4 October 2026. Final merged-base
acceptance is merged `a370134`, reviewed `c9c47b8` with both CI checks green.
The test entrypoint changed; runtime is unchanged from `34bf344`. These
observations retain their exact source;
they do not become a real-model success when later documentation changes.

## Deterministic and installed fixture evidence

Root's full gate at `34bf344` passed **1,005 tests, zero skips**, with workflow,
lock, lint/format, strict mypy and source/wheel build checks. Pinned Hermes fixtures
were enabled. Installed HR E2E and exact-approval/mobile visual checks passed.
The provider was an explicit fixture: two attributed model attempts, one known
settlement and one uncertain invalid-provider outcome with output withheld.
Pending and approved mail had zero outbox effects. Resume and replay retained
one local fixture outbox row. Scope, expiry and session boundaries were exercised.
These results establish control behavior, not actual classifier quality or a
successful real HR summary.

Root's independent installed-console regression at `34bf344` passed credential
browser and local-console checks, including unchanged state after HR startup
failure, session/CSRF boundaries, outbox replay, mobile navigation and MCP.
Desktop/mobile visual review covered overview, catalog, timeline, denial,
outbox and startup failure. Mocked-component checks supply UI-only evidence.
The acceptance runner executed **140 cases / 420 setup-call-teardown phases**
with zero failures, skips or reconciliation problems. These are separate
runner counts, not additions to the 1,005 pytest tests. The final fixed ladder
entrypoint at `c9c47b8` passed author and independent QA. The original
test-entrypoint failure evidence/log is retained: it assumed the default Overview,
then was fixed by explicit `/#overview` navigation. This is separate from the
local-console startup/no-authority-mutation checks above. Root also reports 18 passing Node contract checks, separately
from the Python and acceptance counts. The separately observed preserving
primary upgrade and deliberate HR setup are recorded in the
[release ledger](release-evidence.md#existing-primary-installation-preservation-then-deliberate-setup);
its UI check made zero provider attempts.

The separately accepted issuer test (`cd4c162`, merged `e015e66c`) used generated
keys and a provider fixture. Direct REST, direct MCP and pinned Hermes each ran
a model/tool/model cycle. The department HTTP report selected six known
`issuer_v2` attempts with 120 input and 18 output tokens, minimized provenance.
Those attempts are a separate selected window and must not be added to unrelated
or overlapping suite totals. No corporate IdP certification is implied.

## Actual standard-v2 HR observation

Root ran an isolated installed **standard Laya / content-role-v2 / enforce**
profile, using checkpoint `e4e9ddf21a7b1903b7acffd8814ad4307bf63a67`.
The input was the ordinary synthetic candidate record. Summary first makes a
fresh governed read; it cannot bypass withheld source output.

| Request | Actual result | Release and effect |
|---|---|---|
| Candidate READ | HTTP 403, `SEMANTIC_BLOCKED`, `executed=true` | Protected read occurred, document output withheld |
| Candidate SUMMARY | HTTP 403, `SEMANTIC_BLOCKED`, `executed=true` | Fresh source read occurred, no document or summary released, no provider dispatch |

Across those two requests: zero released documents/summaries, zero model-provider
attempts and zero outbox rows. Tool reservation records changed **0→2**, audit
events **0→4**, and installation UTC-day semantic quota **0→2/1000**. These counts
describe their respective effects, not four separate attacks or two model calls.
Output denial does not undo an executed read.

This is an **actual false positive**, unsuitable for a normal HR semantic demo.
It supplies no efficacy claim and must not be described as model-summary success.
The guard was retained unchanged. Ending the binding returned HTTP 200; root
stopped the owned QA installation. No inference was run by the presentation author.

The minimized local artifact is
`reports/generated/final-hr/real-standard-v2-observation.json` in root's evidence
workspace, SHA-256
`af884f87f43e58af5883f44bff0370b0b9bf981aebe496c6e402d53cccfba2de`.
It remains ignored. Public documentation carries only this scoped narrative and
digest, with no installation URL, machine path, token or private record.

## Demonstration boundary

Fresh installations keep semantic inspection off by default. Standard is an
explicit opt-in; native CoreML remains experimental. An existing explicitly
configured enforce installation retains that policy. Do not silently disable its
guard to obtain a successful demonstration, substitute fixture results for a
real worker, or rewrite the failed observation. A fixture-only HR demonstration
must state its provider/semantic configuration.

For an independently authorized reproduction: prepare one isolated installation
with the exact worker/checkpoint/question profile, record current controls and
all counters, deliberately bind HR authority, request the ordinary candidate
READ and SUMMARY once, record actual HTTP/reason/execution/release/effect fields,
then end the binding and stop only owned processes. Do not promise the label in
advance or mutate shared model/primary installation state. Keep this observation
separate from the frozen [v1](semantic-evaluation.md) and [v2](semantic-v2-evidence.md)
corpora, which still retain poor outcomes, missed attacks and the failed CoreML
warm run.
