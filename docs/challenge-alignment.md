# Laya Sec Layer: AI Control Layer challenge alignment

Assessment updated **2026-10-04** with catalog, local console, delegated authority
and department accounting, plus accepted HR/issuer base `a370134`;
exact source and observations are in [release evidence](release-evidence.md).
The product is Laya Sec Layer, implemented by AgentGate. Cezar task completion
and setup validation do not prove challenge delivery. No challenge-completion
percentage or judging score is inferred from this map.

User-supplied **B1** `AI Control Layer.pdf` (4 pages) and **B2**
`TaC AI Control Layer.pdf` (3 pages) were reread from the supplied originals.
SHA-256s match the earlier assessment; originals and extracted copies are not
republished:

- B1: `786a9bb4a858f98dd178085dc27ad5fb81d599a523d9318901ef2a0ff6aaf11c`
- B2: `31a3fb1537ac1d02d3f4c8e22989b2a377d82c1f7ff2df749f461de695784924`

## Requirement-to-evidence map

| B1 requirement | Current code / concrete evidence | Limits and remaining acceptance |
|---|---|---|
| Intercept agent/model/MCP/API interactions; simple diagram (§§2–3, p. 2) | Authenticated model facade, REST registered execution and official-SDK MCP; [diagrams](architecture.md); real local model/tool cycle recorded in [model gateway](model-gateway.md) | Restricted direct REST/MCP and genuine pinned Hermes clients have actual local cycles; no universal SDK/native-tool coverage or host sandbox |
| Central policy, strictness, allowed models and budgets (§4.1, p. 3) | Validated live policy/feed snapshots, atomic CAS activation, `local-demo` allowlist, deterministic enforcement and optional semantic enforce/observe; `test_control_plane.py`, `test_models.py` | Root reports browser activation/stale conflict; no calibrated safety threshold or enterprise IAM; invalid edits keep last good state |
| Deterministic controls (§4.2, p. 3) | Server-owned identity/ACL, tenant memory queries, schema parsing, recipient policy, exact approvals, bounded email/marker DLP; T01–T27 | Supported synthetic formats only; outbox fixture, no SMTP or general DLP |
| Semantic controls (§4.2, p. 3) | Actual standard/native CoreML workers; supported model input/output, tool-action/result inspection; frozen [v1](semantic-evaluation.md) and merged v2 [evidence](release-evidence.md) | V1 7/26 correct each and failed CoreML warm run retained; v2 15/28 CPU,16/28 CoreML, false positives/negatives; not approved detector; optional/off by default, CoreML experimental |
| External/local resource governance (§2, p. 2; §4.3, p. 3) | Atomic tool/model call/token/micro-USD ledgers, delegated root scopes, retained unknown usage, native concurrency/deadlines, persistent installation-wide UTC-day semantic quota; T21–T30 | Local tariff simulated zero; nonzero tariffs only deterministic simulations; no commercial invoice cap or full cumulative semantic token/time scopes |
| Historical attacks and managed signatures (§2, p. 2; §4.4, p. 3) | Typed bounded literal/domain/digest/serializer feed, validate/CAS activation, pinned actual asset files; T31–T36 with exact approved metadata registry | Metadata simulation performs no hostile model download/execution/CVE reproduction; external signed feed refresh and production intake proposed |
| Interactive dashboard, security/resource/cost reporting (§3.3, §4.5, p. 3) | Packaged authenticated operator UI, event-derived states/counters, approvals, live controls, ledgers, scoped exports and local sender/collector; root reports installed browser suite +51 collector records/zero lag | Export envelopes are not vendor delivery; UI timings include configured scope, no security posture certification; global local operator authority |
| Executable positive/negative controls (§4.6, p. 3; §6, p. 4) | [T01–T48 inventory](acceptance.md) maps concrete tests/fixtures, effects and gaps; full deterministic `make validate`; real loopback MCP/telemetry | Classifier process/math fixtures are not real accuracy; measured labels not all passes; ANE gap; independent review/root current-head gate separate |
| Spontaneous prompts and config/feed changes (§6, p. 4) | Operator model/document/memory/mail playground, versioned live policy/feed; root browser checks and actual local model smoke | Do not promise a correct semantic label for spontaneous prompts; approval revalidation, audit/ledger effects must accompany UI claims |
| Own setup without paid services (§7, p. 4) | `./laya` installed gateway/UI/private proxy/local collector, prepared local Ollama; optional isolated standard/native CoreML; [runbook](demo-runbook.md) | Dependencies/assets must be preloaded for offline restart; trusted host/shared Ollama is not an egress sandbox; fresh-host install and each final runtime head need evidence |

The primary final presentation uses the synthetic HR workflow. Local human/agent
intersection and the catalog are implemented; generated-key issuer exchange is an
optional accepted adapter, not corporate IdP certification. The distinct department
model report uses trusted attribution, known/unknown attempt denominators and
simulated tariffs; department export is unavailable. [Official standards associations](standards-evidence.md)
support specific controls without automatic RODO/AI Act/DORA/OWASP compliance.
AI Act classification depends on intended purpose and applicable Article 6
exceptions, not the word HR.

Root's actual HR standard/v2/enforce observation at `34bf344` blocked the ordinary
candidate READ and SUMMARY source read: executed reads, withheld results, zero
model-provider attempts/outbox. This is a [false positive](hr-release-observation.md),
preserved alongside passing fixture HR checks and the 1,005-test root gate.
Base `a370134` is accepted with green CI. This cannot be presented as a successful
real HR summary or merged semantic improvement.

No particular SIEM, bank credentials or Goldman Sachs deployment is mandated by
these PDFs. [Bank capabilities](enterprise-integrations.md) describe proposed
interfaces, not access or validated compatibility. The brief allows pre-existing
agents/tools and judges the control layer; do not attribute Laya, LiteLLM, Hermes
or Cezar as original team product work.

## Submission and discrepancies

| Criterion | B1 §8, p. 4 | B2 §11, p. 2 |
|---|---:|---:|
| Robustness / guardrails | 30% | 30% |
| Architecture / performance | 20% | 20% |
| Security reporting | 20% | 20% |
| Self-testing | 15% | 20% |
| Implementability / scalability | 15% | 10% |

The final two weights disagree. No precedence is inferred. B2 §5, p. 1 specifies
project title, team name, 1–6 members, description, a **maximum ten-slide PDF**,
and HackTribe submission in **English or Polish**. Its literal earliest start is
23:00 October 3 and cutoff 23:00 October 4, with no timezone in that clause.
Record organizer clarification; do not silently repair the hours or declare
eligibility. B2 §13, p. 3 says later changes are not considered. Cross-category
eligibility is unresolved by these files.

Reviewable [English/Polish presentation sources](presentation/README.md) and
[submission template](submission-template.md) are supplied. Team identity, dates,
eligibility, demo URL and actual HackTribe submission are user-owned.
Team fields are deliberate, not invented facts or a blocking question. The public
repository is https://github.com/bsisduck/laya-sec-agent; no public demo URL or
HackTribe submission is invented.
