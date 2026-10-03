# Release evidence and claim boundaries

Documentation snapshot: **2026-10-03**, release integration
[`09a7c737f32efb30ce3fbae28e781a27b404da43`](https://github.com/bsisduck/laya-sec-agent/commit/09a7c737f32efb30ce3fbae28e781a27b404da43).
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
| [22 installer](https://github.com/bsisduck/laya-sec-agent/pull/22) | `a3b31b6` | Open | Installer code present in release snapshot; not a merged release |
| [28 artifact simulator](https://github.com/bsisduck/laya-sec-agent/pull/28) | `90d42fb` | Open | Pending; metadata policy simulation, no byte verification/download/execution |
| [30 restricted clients](https://github.com/bsisduck/laya-sec-agent/pull/30) | `dfe67c8` | Open | Pending; actual pinned Hermes code/profile with provider-fixture tests; real local cycles pending in that inspected ref |
| [32 semantic v2](https://github.com/bsisduck/laya-sec-agent/pull/32) | `43ea6e6` | Open | Pending contract integration; fresh measured evidence below, no approved detector |
| [31 full-stack integration](https://github.com/bsisduck/laya-sec-agent/pull/31) | `09a7c73` | Open | Root owns review, browser QA, final integration and merge |

Pinned pending source references: [artifact contract at 90d42fb](https://github.com/bsisduck/laya-sec-agent/blob/90d42fb1c720fc61b24e3c72c6ff259cac3257da/docs/artifact-intake.md),
[Hermes launcher at dfe67c8](https://github.com/bsisduck/laya-sec-agent/blob/dfe67c87ff51457699e9500b51956947a0388fa9/src/agentgate/agents/hermes.py),
[v2 contract at 43ea6e6](https://github.com/bsisduck/laya-sec-agent/blob/43ea6e6efd4c442662465af9e9e971e28d8b1356/docs/semantic-question-v2.md).
The Hermes source pin is `f97608f178d1ffeca59860195ab7da295f7c8e5f`
(version 0.21.5); source inspection/profile fixtures do not verify an actual
local-model cycle or isolation from a privileged same-user host process.

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
agent coverage. V2 evidence was inspected read-only in the semantic task's local
`docs/semantic-v2-evidence.md` while its publication was pending. Identifiers:

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

## Before root freezes the release

Refresh this ledger from final merged commits, then update acceptance pending
references, diagram labels, demo steps and slides together. Record root's exact
installed source/head, browser/API/effect evidence and CI links. Do not relabel an
open PR as delivered from task status or copy someone else's tests as this run.
The presentation and submission template are reviewable assets; team details,
organizer clarification and HackTribe submission remain user-owned.
