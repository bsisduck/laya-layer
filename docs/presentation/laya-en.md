---
marp: true
theme: laya
size: 16:9
paginate: true
header: LAYA SEC LAYER / AGENTGATE
footer: Integrated evidence · 2026-10-03 · Local prototype · docs/release-evidence.md
---
<!-- _class: lead -->
<div class="kicker">AI Control Layer / HackYeah</div>

# Laya Sec Layer

**One policy boundary for models and actions.**

Scoped access, bounded resources, exact approval and evidence before output release.

<div class="note">AgentGate is the gateway. Cezar orchestrates development.</div>

---
## Two paths must be governed

<div class="flow"><div class="node"><strong>Model path</strong>Registered alias<br>Input inspection</div><div class="arrow">→</div><div class="node"><strong>AgentGate</strong>Identity + policy<br>Budget + audit</div><div class="arrow">→</div><div class="node"><strong>Private router</strong>LiteLLM → Ollama<br>Buffered result</div></div>
<div class="flow"><div class="node"><strong>Tool path</strong>REST / official MCP<br>Explicit aliases</div><div class="arrow">→</div><div class="node"><strong>Same authority</strong>ACL + exact approval<br>Recheck at dispatch</div><div class="arrow">→</div><div class="node"><strong>Registered effect</strong>Documents / memory<br>Local fixture outbox</div></div>

<div class="warn">A model tool call is a proposal. Execution needs its own authorization.</div>

---
## Deterministic controls are the authority

<div class="grid"><div class="card"><h3>Identity and scope</h3><p>Credential-owned tenant, role, agent and root. No conversational permission grants.</p></div><div class="card"><h3>Supported text protection</h3><p>Email redaction and synthetic-secret blocking before relevant egress.</p></div><div class="card"><h3>Atomic resource limits</h3><p>Calls, tokens and reservations. Uncertain dispatch retains capacity.</p></div><div class="card"><h3>Live controls</h3><p>Validate and activate policy/feed atomically; stale versions conflict.</p></div></div>

<div class="note">Bounded synthetic formats, not universal DLP. Local tariff is simulated zero.</div>

---
## Approval binds one immutable action

<div class="flow"><div class="node"><strong>Propose</strong>Exact payload<br>Stable key</div><div class="arrow">→</div><div class="node"><strong>Approve</strong>Operator reviews<br>Fingerprint</div><div class="arrow">→</div><div class="node"><strong>Revalidate</strong>Same authority<br>Current controls</div><div class="arrow">→</div><div class="node"><strong>Consume</strong>One fixture row<br>Replay deduped</div></div>

**Pending and approved states produce no outbox effect by themselves.**

Changed payload conflicts. Credential renewal preserves identity and root spend.

<div class="warn">Mail is a local SQLite outbox. No SMTP delivery is claimed.</div>

---
## Semantic evidence stays visible

| Frozen first pass | Standard CPU | Native CoreML |
|---|---:|---:|
| v1 · 26 cases | 7/26 correct | 7/26 correct |
| v2 · 28 fresh cases | 15/28 correct | 16/28 correct |

<div class="warn"><strong>V2 mistakes:</strong> 7 / 6 false positives and 4 false negatives each. Both missed indirect malicious paraphrases.</div>

<div class="note">V1 withheld all 16 benign cases; its CoreML warm run failed. Different corpora/questions are not a controlled improvement estimate. Installed CPU v2: allow / executed-read output withheld / tenant deny; quota 0→2. Standard preferred opt-in; CoreML experimental; semantic off by default.</div>

---
## Security reporting with real receipts

<div class="flow"><div class="node"><strong>Audit</strong>Minimized events<br>Actual execution</div><div class="arrow">→</div><div class="node"><strong>Durable sender</strong>Retained batch<br>Replay on failure</div><div class="arrow">→</div><div class="node"><strong>Local collector</strong>Durable exact ack<br>Event-ID dedup</div></div>
<div class="grid"><div class="card"><div class="metric">51</div><div class="label">Local receipt records · root installed QA</div></div><div class="card"><div class="metric">0</div><div class="label">Observed source lag in that run</div></div></div>

<div class="note">Laya local HTTP protocol v1; at least once, not exactly once. Scoped JSONL/ECS/HEC file export is separate from delivery.</div>

---
## A bank connection needs separate acceptance

<div class="columns"><div><div class="node"><strong>Available local boundaries</strong>Model + REST/MCP enforcement<br>Operator approval + live controls<br>Minimized export + local receipt</div><p class="note">Native loopback trusts the host. Same-user direct upstream access is outside this boundary.</p></div><div><div class="node proposed"><strong>Proposed enterprise adapters</strong>Splunk / Elastic / OpenSearch<br>Kafka / Security Hub<br>SSO + secret-store integration</div><p class="note">Require exact versions, authenticated delivery, indexed-event proof and failure/replay tests.</p></div></div>

<div class="warn">No bank deployment, vendor/SOC certification or live SIEM connector is claimed.</div>

---
## Reproducible tests, bounded live evidence

<div class="grid"><div class="card"><h3>T01–T48 inventory</h3><p>Concrete tests, frozen semantic cases, explicit coverage limits and an ANE gap.</p></div><div class="card"><h3>Installed browser QA</h3><p>Root reports document/memory isolation, exact mail, live controls, export and session checks.</p></div></div>

`make validate` · `scripts/acceptance_matrix.py --run`

<div class="warn">Actual local summary: 118 tokens, one provider attempt, 4317 ms end-to-end including generation. One observation, not guard-only latency.</div>

<div class="note">Control fixtures and model accuracy are separate. Metadata intake and restricted REST/MCP/Hermes clients are integrated and reviewed.</div>

---
<!-- _class: lead -->
## Working local prototype. Explicit limits.

**Original work:** policy enforcement, controlled execution, budgets, approvals, live controls and minimized evidence.

Laya, LiteLLM, Ollama and Hermes are dependencies; Cezar is development tooling.

Independent review and reproducible checks support the local product. Enterprise acceptance remains separate; semantic errors stay visible.

<div class="node"><strong>Submission fields — user owned</strong>Team: [TEAM NAME] · Members (1–6): [MEMBERS]<br>Repository: github.com/bsisduck/laya-sec-agent<br>Public demo: [URL] · Organizer: [CONFIRMED DETAILS]</div>

<!-- Speaker notes: Fill deliberate template fields before submission. English or Polish is permitted. Keep at most ten PDF pages. Do not claim organizer eligibility or submission from documentation completion. -->
