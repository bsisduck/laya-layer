# Release evidence and claim boundaries

Updated **2026-10-04**. Accepted runtime base is
`a37013449ed4be1994a129bd1d1cd34dc4a65520`, reviewed HR head `c9c47b8`
(runtime unchanged from `34bf344`). Both PR50 CI checks are green. Documentation
and the final ten-slide PL/EN sources require their own root content/visual review;
see [presentation delivery](presentation/README.md). Historical integration
`074cace` (PR31) remains recorded below. Laya Sec Layer is the product; AgentGate
is its gateway. Cezar orchestrates development. This is a working local prototype
on a trusted host, not a production security certification.

## Current HR delivery and independent evidence

| Evidence scope | Actual result | Boundary |
|---|---|---|
| Root full gate at `34bf344` | 1,005 pytest tests, zero skips; workflow/lock, lint/format, strict mypy (58 files), source/wheel build PASS | Pinned Hermes and deterministic provider/semantic fixtures; not real classifier accuracy |
| Node contracts | 18 PASS | Browser component contracts, separately counted |
| Installed HR | Exact approval/mobile/scope/expiry/session PASS; two attributed provider-fixture attempts, one known settlement and one uncertain invalid-provider outcome with output withheld | Approval zero effects; resume/replay one local outbox row; no SMTP |
| Independent installed console at `34bf344` | Actual credential and local-console flows, MCP, unchanged HR startup state, sessions/CSRF, replay and desktop/mobile visuals PASS | Mocked-component loading/error/safety checks explicitly UI-only; no inference |
| Acceptance runner at `34bf344` | 140 cases / 420 setup-call-teardown phases; zero failures, skips or reconciliation problems | Separate runner denominator, never summed with pytest or treated as attack samples |
| Final ladder entrypoint `c9c47b8` | Author and independent reruns PASS | Test-only `/#overview` landing fix; initial failure and failure-entry test retained; no runtime change |
| Actual standard/v2/enforce HR | Ordinary READ and SUMMARY source read both `SEMANTIC_BLOCKED`, `executed=true`; output withheld; zero provider attempts/outbox | Material false positive, unsuitable as a successful normal HR semantic demonstration |

The independent minimized report is retained in ignored
`.ai/qa/artifacts_final_deterministic/report.md`; the acceptance artifact is
`reports/generated/final-deterministic-34bf344.json`. Root supplies CI status
separately from that report. See PR50's [push gate](https://github.com/bsisduck/laya-sec-agent/actions/runs/37174047015)
and [PR gate](https://github.com/bsisduck/laya-sec-agent/actions/runs/37174049349).
[The exact semantic profile, counters and artifact digest](hr-release-observation.md)
preserve the failed real observation alongside successful fixture controls.

### Existing primary installation: preservation then deliberate setup

Root upgraded the existing installation offline to `a370134`. A read-only
before/after snapshot verified **37 pre-existing stable tables**, using their old
column projection, including collector/quota state, and all key/token hashes
unchanged **before HR setup**. Local-console mode and standard/content-role-v2
**enforce** remained selected. Owned services and shared Ollama were ready.

The operator then deliberately reviewed and CAS-activated the HR delta. It changed
only revision/delegation/document roles/mail roles, retaining model budgets, feed
and semantic controls. This intentional setup is distinct from upgrade preservation.
A fresh actual Playwright UI check passed: no login, no DOM/storage bearer,
HR ready for deliberate Start binding, mobile fit and department/standards views.
It made **zero provider attempts** and does not establish successful HR generation.
Root left the installation running. The existing guard was not weakened.

Minimized ignored delivery evidence: `reports/generated/live-console/hr-delivery.json`,
`hr-workspace.png` and `hr-mobile.png` in the same directory. No private state path,
installation URL, key or token is published. The author did not mutate the primary
installation, shared Ollama or other QA state.

## Integrated capabilities

| Boundary | Implementation and evidence | Limit |
|---|---|---|
| Model | Authenticated `local-demo` Chat Completions through private LiteLLM/Ollama; input/output and tool-argument inspection; atomic call/token/micro-USD reservations | Buffered output, one proposed tool call; local tariff zero/simulated |
| Tools | Credential-owned tenant/role/agent/root; document and memory operations over REST and official-SDK MCP | Synthetic resources, no arbitrary shell or URL executor |
| Mail | Stored immutable payload, separate operator approval, revalidation and one effect under replay | SQLite fixture outbox, no SMTP delivery |
| Agents | Bounded direct REST/MCP and pinned upstream Hermes clients; actual two-model-call/one-document cycles | Restricted profile, no isolation from privileged same-user host authority |
| HR/person authority | Preserving HR setup, local employee/agent grant intersection, session-private child, optional pinned issuer exchange | Generated-key issuer tests, no corporate IdP certification; real HR semantic false positive retained |
| Catalog/department usage | Three reviewed adapters, explainable 25/75 heuristic; one selected-period row per model attempt with immutable attribution | No destructive/payment/merge adapter; unknown consumption and simulated tariffs explicit; department export absent |
| Controls/UI | Packaged dashboard, sessions/CSRF, policy/feed validation and CAS activation, explicit expired-credential renewal | Global local operator; enterprise tenant RBAC/SSO absent |
| Budgets | Shared-root tool/model ledgers, conservative unknown consumption and persistent installation-wide semantic call quota | No full cumulative per-tenant semantic token/time or physical-resource accounting |
| Evidence | Minimized audit, scoped JSONL/ECS-oriented/HEC-envelope downloads, durable sender and owned local collector | Local protocol v1, at-least-once with event-ID deduplication; no tested bank/SIEM adapter |
| Artifacts | Exact approved metadata tuple and active-feed checks; executable serializers rejected | No artifact download, byte verification, deserialization or execution |
| Installation | `./laya` lifecycle, private state, isolated runtimes, owned children, prepared offline restart | Initial dependencies/assets required; shared pinned Ollama; CoreML Apple-only |

The [T01–T48 inventory](acceptance.md) maps concrete control tests, measured
semantic cases and gaps. A passing control suite does not imply all 48 outcomes
or reliable semantic detection.

## Historical full-stack validation (PR31)

At `074cace`, `make validate` passed **614 tests, zero skips**, including pinned
upstream Hermes fixtures, plus workflow/config/lock checks, Ruff, strict mypy and
source/wheel packaging. Six JavaScript contract checks passed. The acceptance
runner executed **139 control observations**, all passed, and retained the
39 control /3 partial /5 measured /1 gap classifications. ANE remains the gap;
pytest does not turn measured semantic errors into success. Both GitHub CI checks
passed (604 tests plus 10 optional upstream-Hermes skips in CI; local enabled
fixtures account for the full 614). See [push](https://github.com/bsisduck/laya-sec-agent/actions/runs/37154818912),
[PR](https://github.com/bsisduck/laya-sec-agent/actions/runs/37154821021).

Source-prepared installed browser QA at `b740c35` passed all full-stack flows
with `--model`. The actual summary used one provider attempt and 118 tokens in
3450.325 ms; secret input caused zero attempts. The local collector held 92
acknowledged records with zero lag. The 12-response P50/P95 was 8.944/3404.923 ms,
including generation time. These are local observations, not latency guarantees.
Reports remain in ignored `.ai/qa/artifacts_fullstack_final/`.

## Review and integration ledger

| PR | Reviewed head | Integrated result |
|---|---|---|
| [19 tools/MCP](https://github.com/bsisduck/laya-sec-agent/pull/19) | `0ab2672` | `255a17e`; scoped effects and approvals |
| [21 telemetry](https://github.com/bsisduck/laya-sec-agent/pull/21) | `9ba757e` | `0b8af56`; local delivery contract |
| [24 renewal](https://github.com/bsisduck/laya-sec-agent/pull/24) | `5b982a6` | `4e82729`; explicit operator authority |
| [26 semantic quota](https://github.com/bsisduck/laya-sec-agent/pull/26) | `a81d86b` | `4fe26c4`; persistent call limit |
| [22 installer](https://github.com/bsisduck/laya-sec-agent/pull/22) | `a3b31b6` | `b15eb65`; independent merged-head 504-test gate, green CI; source-only wheel upgrade regression |
| [28 artifact intake](https://github.com/bsisduck/laya-sec-agent/pull/28) | `703a33e` | `798bab1`; independent GPT-6.1-Sol 548-test gate and 56 negative probes, green CI |
| [30 restricted clients](https://github.com/bsisduck/laya-sec-agent/pull/30) | `08d6e7b` | `0010602`; independent 584-test gate with all pinned upstream fixtures enabled, green CI |
| [32 semantic v2](https://github.com/bsisduck/laya-sec-agent/pull/32) | `3ec6ec5` | `4a1fe3d`; reviewed frozen measurements and version binding, green CI |
| [35 fragmented HTTP](https://github.com/bsisduck/laya-sec-agent/pull/35) | `54f3369` | `ba2dae8`; independent 60-test model/transport gate, green CI; no product code changes |
| [33 documentation](https://github.com/bsisduck/laya-sec-agent/pull/33) | `4586f40` | `aaaa0e0` into PR31; reviewed mapping runner and EN/PL deck sources |
| [31 full-stack release](https://github.com/bsisduck/laya-sec-agent/pull/31) | Final `074cace` | Independent GPT-6.1-Sol delta review: APPROVE, no blockers/majors; earlier two defects fixed and independently reproduced |
| [47 department/standards](https://github.com/bsisduck/laya-sec-agent/pull/47) | `40eb409` | `e6ac3564`; root 886-test zero-skip gate, installed accounting both console modes and mobile/keyboard PASS, green CI |
| [49 issuer exchange](https://github.com/bsisduck/laya-sec-agent/pull/49) | `cd4c162` | `e015e66c`; root 974-test zero-skip gate; generated-key REST/MCP/Hermes fixture cycles and nondispatch/replay PASS, green CI |
| [50 HR workspace](https://github.com/bsisduck/laya-sec-agent/pull/50) | `c9c47b8` (runtime `34bf344`) | `a370134`; current evidence above, independent test-entrypoint rerun and both CI green; actual real semantic false positive retained |

PR31's initial review reproduced a plain-FastAPI overview failure and a stranded
sender after a collector-port change. Fix `9e1cfec` supplies honest unconfigured
adapter defaults and migrates the same owned collector's binding under the sender
lock while retaining pending work. Two regressions failed before the fixes and
passed afterward. The independent follow-up reproduced both fixes, real installed
port migration, deduplication/new delivery, interrupted publication recovery and
seven negative probes; its exact-SHA verdict remains on the PR.

## Real semantic evidence remains imperfect

**Current HR limitation:** at `34bf344`, actual installed standard/v2/enforce
blocked the ordinary candidate READ and the fresh source read for SUMMARY with
`SEMANTIC_BLOCKED`, `executed=true`. Two protected reads occurred, output was
withheld, and no model-provider attempt or outbox effect occurred. This is a
false positive, not a successful real HR summary. The guard and all frozen
measurements remain unchanged. [Exact profile, counters and artifact digest](hr-release-observation.md)
separate this observation from passing deterministic/provider-fixture checks.

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

## Installed runtime observations

The committed [full-stack QA record](../.ai/runs/2026-10-03-full-stack-release.md)
identifies source and ignored reports. Historical measurements are observations,
not portable performance targets; final validation results belong to their exact
commit and CI run.

| Scope | Observed evidence | Limit |
|---|---|---|
| Installed browser through `f6bccde` | Document allow/redact/tenant deny; memory isolation; immutable mail approval/changed-payload conflict/one effect and replay; renewal retains identity/budgets; policy CAS/feed/export/session; 390/768/1440 layouts | Synthetic tool resources; actual packaged wheel, not a dev server |
| Installed local model | 488-character summary; 36 prompt +82 output tokens; one provider attempt; 3.747 s in full browser run; secret-input denial with zero new attempts | One end-to-end observation including generation, not guard-only latency |
| Installed collector | 51 minimized receipt records, zero source lag; no mail payload in exported records | Local receipt, no vendor indexing proof |
| Operator timings | P50/P95 19.286/39.985 ms over 28 playground responses | Includes tool time; bounded process-local window resets on restart |
| Lifecycle | Warm QA reuse 0.244 s; source change invalidates cache; double stop idempotent; restart 7.406 s; keys/epochs/ledgers retained | One local lifecycle observation |
| Installed standard-v2 `f6bccde` | Explicit standard/v2 installation and prepared offline restart; all four services ready; ordinary document allowed, injected instructions withheld, tenant denial before read; quota 0→2/1000 | Selected CPU profile and those fixtures only; no new CoreML inference |
| Genuine agents `f07add0`, final reviewed `08d6e7b` | REST 4.46 s, MCP 3.32 s, pinned Hermes 6.46 s; each two model calls and one document cycle with exact call-ID/root correlation | Semantic off; single-cycle timings. Five failed developmental Hermes invocations retained and charged with zero tool effects |

The installed semantic denial is **`SEMANTIC_BLOCKED`, `executed=true`, result
withheld**. Cross-tenant denial is **`RESOURCE_NOT_ALLOWED`, `executed=false`**.
Output denial does not undo an executed read. Isolated semantic and agent QA
children were stopped; shared Ollama was left untouched.

Pinned upstream Hermes: version 0.21.5, commit
`f97608f178d1ffeca59860195ab7da295f7c8e5f`. Its final actual-cycle report was
independently checked: SHA-256
`a2761469f02b9029dd591f4d3b472b0bb94862caec114a2951907ec8fbd68a85`.
Native upstream fixtures ran in the separate pinned source/runtime; setting
`AGENTGATE_HERMES_SOURCE` enables them in the gateway gate. They do not run
heavyweight inference.

Ignored browser evidence includes `installed-semantic-v2.json`,
`semantic-output-blocked.png`, `semantic-overview.png`, `model-generation.png`
and `qa-cache-lifecycle.json` under `.ai/qa/artifacts_fullstack/`.
The executable browser suite is `tests/frontend/browser_check.py`, with `--model`
for the actual configured local provider.

Final independent [review at `074cace`](https://github.com/bsisduck/laya-sec-agent/pull/31#pullrequestreview-5402838442)
checked preserved runtime files and merge resolution, six HTTP/effect checks, six
JavaScript contracts, all 21 acceptance report source hashes and sanitized installed
model/collector evidence. It issued an APPROVE technical verdict as COMMENT
(the authenticated repository account also authored the PR). The final result
documentation is a subsequent docs-only delta reviewed by the release owner.

## Acceptance still outside the local product

Live vendor/bank endpoints, enterprise IAM, SMTP delivery, signed external feed
refresh, generalized DLP, ANE, production scale/retention and physical-resource
accounting need separate implementation and acceptance. Team details, organizer
clarification and HackTribe submission remain user-owned. Neither test success
nor a rendered deck claims a submission, eligibility decision or certification.
