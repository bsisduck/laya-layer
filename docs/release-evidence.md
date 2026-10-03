# Release evidence and claim boundaries

Documentation snapshot: **2026-10-03**, release integration
[`032bb77c50443279d653263fb3600102e80d55a6`](https://github.com/bsisduck/laya-sec-agent/commit/032bb77c50443279d653263fb3600102e80d55a6).
Documentation initially branched from `09a7c73` and was rebased to this published
release ref after root reported installer/semantic integration and installed QA.
Laya Sec Layer is the product; AgentGate is its gateway. Cezar is development
orchestration. A Cezar task, passing setup check or rendered screenshot does not
prove product completion. This is a local prototype, not a production release.

## What exists in this release branch

| Boundary | Implementation and evidence | Limit |
|---|---|---|
| Model | Authenticated `local-demo` Chat Completions via private LiteLLM/Ollama; input/output and decoded tool-argument inspection; atomic call/token/micro-USD reservations | Buffered responses, one proposed tool call; local tariff is zero/simulated, no external invoice guarantee |
| Tools | Credential-owned tenant/role/agent/root, registered document and memory operations, REST and official-SDK MCP | Synthetic registered resources; no arbitrary shell/URL executor or general host sandbox |
| Mail | Exact stored payload/fingerprint, separate operator approval, revalidation, one local outbox effect under replay | `delivery_state=fixture`; no SMTP delivery |
| Controls and UI | Packaged local dashboard, separate operator sessions/CSRF, policy/feed validation and compare-and-swap activation, explicit expired-credential renewal | Global local operator, no enterprise tenant RBAC/SSO; root owns final browser QA |
| Resources | Tool/model ledgers, shared-root accounting, conservative uncertain reservations, persistent installation-wide daily semantic-call quota | No full cumulative per-tenant semantic token/time ledger or measured hardware preemption |
| Evidence | Minimized audit, JSONL/ECS-oriented/HEC-envelope downloads, async durable sender and authenticated local collector | Local protocol v1 with at-least-once delivery and event-ID deduplication; no tested SIEM/bank adapter |
| Installation | `./laya` lifecycle, private state, separate environments, owned children, prepared offline restart | Ollama is shared and preloaded; initial installation needs dependencies/cache; optional native CoreML is Apple-only |

Evidence in the integrated tree: `tests/test_gateway.py`, `test_models.py`,
`test_scoped_tools.py`, `test_mcp.py`, `test_full_stack.py`, `test_control_plane.py`,
`test_credential_renewal.py`, `test_semantic_quota.py`, `test_lifecycle.py`,
`test_observability_integration.py`, `test_telemetry_http.py`. These names are
references to deterministic/integration checks, not a claim they all ran in this
documentation session. Current execution results belong in the ignored review
report and CI for the exact documentation head. See [acceptance](acceptance.md).

## Integration and publication ledger

The GitHub state below was read on 2026-10-03. Presence in the release branch and
merge to `main` are separate facts. Open PRs remain pending release review even
where their code is already integrated into PR31.

| PR | Observed head | GitHub state | Presence/claim at snapshot |
|---|---|---|---|
| [19 scoped tools](https://github.com/bsisduck/laya-sec-agent/pull/19) | `0ab2672` | Merged (`255a17e`) | Integrated tools/MCP/approvals; fixture outbox |
| [21 telemetry](https://github.com/bsisduck/laya-sec-agent/pull/21) | `9ba757e` | Merged (`0b8af56`) | Local contract sender/collector, not vendor delivery |
| [24 credential renewal](https://github.com/bsisduck/laya-sec-agent/pull/24) | `5b982a6` | Merged (`4e82729`) | Integrated explicit operator authority |
| [26 semantic quota](https://github.com/bsisduck/laya-sec-agent/pull/26) | `a81d86b` | Merged (`4fe26c4`) | Integrated installation-wide call quota |
| [22 installer](https://github.com/bsisduck/laya-sec-agent/pull/22) | `a3b31b6` | Merged (`b15eb65`) | Root reports independent 504-test merged-head gate and both Linux CI green; source-only wheel fix uses `--reinstall-package agentgate` |
| [28 artifact simulator](https://github.com/bsisduck/laya-sec-agent/pull/28) | `703a33e` | Merged main (`798bab1`) | Root reports independent exact-head 548 tests +56 negative probes and green CI; absent from release snapshot `032bb77`, integration pending |
| [30 restricted clients](https://github.com/bsisduck/laya-sec-agent/pull/30) | `dfe67c8` published; `f07add0` author run | Open | Actual pinned Hermes code/profile inspected; author reports real cycles; final gate/root review/merge pending |
| [32 semantic v2](https://github.com/bsisduck/laya-sec-agent/pull/32) | `3ec6ec5` | Merged (`4a1fe3d`) | Integrated version binding and remembered installer profile at `6495842`; fresh measured evidence, no approved detector |
| [31 full-stack integration](https://github.com/bsisduck/laya-sec-agent/pull/31) | `032bb77` | Open | Root owns review, browser QA, final integration and merge |

Pinned source references (artifact merged-main/pending integration; agent open; semantic merged): [artifact contract at 703a33e](https://github.com/bsisduck/laya-sec-agent/blob/703a33e2c6786b51beeb1200c5b7c4f43974ced9/docs/artifact-intake.md),
[Hermes launcher at dfe67c8](https://github.com/bsisduck/laya-sec-agent/blob/dfe67c87ff51457699e9500b51956947a0388fa9/src/agentgate/agents/hermes.py),
[v2 contract at 43ea6e6](https://github.com/bsisduck/laya-sec-agent/blob/43ea6e6efd4c442662465af9e9e971e28d8b1356/docs/semantic-question-v2.md).
The Hermes source pin is `f97608f178d1ffeca59860195ab7da295f7c8e5f`
(version 0.21.5); source inspection/profile fixtures do not verify an actual
local-model cycle or isolation from a privileged same-user host process. The later actual-cycle
observation below is separately attributed to its author.

## Real semantic evidence remains imperfect

| Frozen measurement | Standard | Native CoreML | Interpretation |
|---|---|---|---|
| v1 first pass, 26 cases | 7/26 correct; 15 abstain, 2 incomplete | Same | All 16 benign cases withheld by strict policy |
| v1 warm run | Completed | Failed after 12 warm answers; five-second timeout | Failed run retained; no blanket Apple speedup/stability claim |
| v2 first pass, 28 fresh cases | 15/28 correct; 7 false positives, 4 false negatives | 16/28 correct; 6 false positives, 4 false negatives | Two deliberate incomplete inputs each; four benign quotations falsely flagged and four indirect malicious paraphrases missed on both |

[V1 evidence](semantic-evaluation.md) retains its freeze, complete outcome table,
denominators and failed CoreML report hash. The v2 freeze is `b466537`, evaluation
revision `43ea6e6`; standard gateway demonstration revision `f503b0f` released
ordinary notes and withheld malicious document output using real Laya and HTTP.
That two-document demonstration does not establish held-out accuracy or complete
agent coverage. V2 evidence was first inspected read-only in the semantic task and is now
[committed with merged PR32](semantic-v2-evidence.md). Identifiers:

| V2 artifact | SHA-256 |
|---|---|
| Standard first report | `b8a998be3ee7ba6c7f5dd67941530e110e6685f53ac7ac916028676efaa1f3d8` |
| CoreML first report | `e700299747420b6b6a564fce99ecc8f6d6b64dc377a00fa74ae0d3cf17d179c8` |
| Comparison | `3f1fc187198b88f6e886410d555bb42aa5b3180b0d8bdaf5cc7822b28415fc58` |
| Standard gateway smoke | `aef0b5e443da0fd194e79d3b183089caf8d46dba6b9ecdfb1630fdf8a99cdead` |

Standard is the preferred explicit opt-in runtime; CoreML remains experimental.
V1 stays the compatibility default and semantic inspection is off in the default
installer. The corpora and question meanings differ, so this is not a controlled
v1/v2 improvement estimate. No inference ran during documentation authoring.

## Root-reported installed QA

These results are supplied by root, separately from this documentation task's own
control run. Root owns final runtime preparation/current-head review. The
committed [full-stack QA record](../.ai/runs/2026-10-03-full-stack-release.md)
is in release snapshot `032bb77`; later observations below identify their refs.

| Scope and ref | Reported observation | Evidence limit |
|---|---|---|
| Installer22 main `b15eb65` | Independent 504-test merged-head gate, both Linux CI green; stale source-only wheel fixed via `--reinstall-package agentgate` | Runtime source preparation still must match the tested installed head |
| Installed UI through `032bb77` / semantic wiring `6495842` | 536 deterministic checks; real browser document allow/redact/tenant deny, memory isolation, immutable mail approval/changed-payload conflict/exact execution/retry with one SQLite outbox row, explicit renewal preserving identity/budgets, policy CAS/feed/export/session, 390/768/1440 layouts | Synthetic tool resources; root evidence, not this docs task's browser run |
| Installed collector through `032bb77` | 51 minimized receipt records, zero source lag; tested mail action without payload leak | Local protocol lab, no vendor indexing proof |
| Operator timings | P50/P95 19.286/39.985 ms, 28 playground responses | Includes tool time; bounded process-local window resets on restart, not isolated security overhead |
| Actual model smoke `3772ebc` | Secret denied with zero new provider attempts; benign summary 488 characters, 118 tokens (36 prompt,82 output), one durable attempt, 4317.436 ms | Single end-to-end timing including generation; not a percentile/semantic benchmark; root notes subsequent runtime reprepare |
| QA cache/lifecycle | Warm reuse 0.244 s; source touch invalidated reuse; double stop idempotent; restart 7.406 s; tokens/epochs/tool/model ledgers preserved | Single local observations, not portable startup targets |
| Installed standard-v2 `f6bccde` | Explicit `--semantic standard --question-set content-role-v2 --no-start`, offline reprepare/start, four owned services ready; ordinary notes allowed/executed; malicious result withheld after executed read; tenant denial before read; quota 0→2/1000 | Proves selected CPU profile for those fixtures, not general detection; no CoreML reinference |
| Artifact28 main `798bab1`, reviewed `703a33e` | Independent GPT-6.1-Sol full548-test gate +56 negative probes and green CI | Exact metadata policy simulation; release integration still pending in `032bb77` |
| PR30 author run `f07add0` | REST 4.46 s, MCP 3.32 s, genuine Hermes 6.46 s; each two model calls and one document cycle | Individual end-to-end observations; published inspected head `dfe67c8`; final gate/root review/merge pending |

The installed semantic denial is **`SEMANTIC_BLOCKED`, `executed=true`, result
withheld**. The cross-tenant denial is **`RESOURCE_NOT_ALLOWED`, `executed=false`**.
An output denial does not undo an executed read. All owned semantic QA children
were stopped by root. The earlier failed CoreML run remains retained.

Root report paths in its ignored `.ai/qa/artifacts_fullstack/`:
`model-generation.png`, `qa-cache-lifecycle.json`, `installed-semantic-v2.json`,
`semantic-output-blocked.png`, `semantic-overview.png` and minimized browser/model
JSON. The current browser suite includes `tests/frontend/browser_check.py` and
`fullstack_flows.py`; optional actual-model mode requires prepared Playwright.
This task neither reruns their inference nor republishes their private artifacts.
Independent PR31 QA and PR30's final gate/review were pending at this cutoff.

## Before root freezes the release

Refresh this ledger from final merged artifact/agent/release commits, then update acceptance pending
references, diagram labels, demo steps and slides together. Record root's exact
installed source/head, browser/API/effect evidence and CI links. Do not relabel an
open PR as delivered from task status or copy someone else's tests as this run.
The presentation and submission template are reviewable assets; team details,
organizer clarification and HackTribe submission remain user-owned.
