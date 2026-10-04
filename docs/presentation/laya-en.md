---
marp: true
theme: laya
size: 16:9
lang: en
paginate: true
header: LAYA SEC LAYER / AGENTGATE
footer: 2026-10-04 · Local prototype
---
<!-- _class: lead -->
<div class="kicker">AI Control Layer / HackYeah</div>

# Laya Sec Layer

**Who acts, on which data, with what effect and resource use.**

An HR agent works within granted scope. A person reviews the exact proposed message before execution.

<div class="note">AgentGate governs model calls and actual tool actions.</div>

---
<!-- _class: compact -->
## HR: data, summary and consent

<div class="columns"><div><div class="node"><strong>Alex Rivera · fictional person</strong>Operations coordinator candidate.<br>3 years coordinating support schedules.<br>Spreadsheet reports and communication.<br>Availability: next month.</div><p class="note">Synthetic record and test CV. No candidate ranking or hiring decision.</p></div><div><h3>Work within a controlled scope</h3><p>The HR employee binds the agent to their scope. The agent reads an available record. A summary requires source release by the gate.</p><p>A person reviews recipient, subject and body. Resume after consent records one message in the local fixture outbox.</p></div></div>

<div class="warn">Benefit: help preparing material, visible data scope and control over the specific action.</div>

<!-- Sources: accepted docs/hr-workflow.md at a370134, reviewed c9c47b8 (runtime 34bf344); synthetic fixture hr-candidate-001 in src/agentgate/documents.py. Summary uses the configured provider and inspected tool result, with no substitute response. -->

---
<!-- _class: compact architecture -->
## Two gates, one policy

<div class="flow"><div class="node"><strong>Agent / application</strong>Scoped agent credential<br>Model request</div><div class="arrow">→</div><div class="node"><strong>LLM gate</strong>Input and output<br>Model alias, limits</div><div class="arrow">→</div><div class="node"><strong>Private route</strong>LiteLLM → Ollama<br>Full result before release</div></div>
<div class="shared"><strong>Shared identity, policy, approvals, budget and audit</strong></div>
<div class="flow"><div class="node"><strong>Tool proposal</strong>REST / official MCP<br>Explicit operation aliases</div><div class="arrow">→</div><div class="node"><strong>Action gate</strong>Data scope<br>Recheck before dispatch</div><div class="arrow">→</div><div class="node"><strong>Local executor</strong>Documents and memory<br>SQLite fixture outbox</div></div>
<div class="target-row"><div class="node"><strong>Local services</strong>Optional Laya / native CoreML, audit, collector.</div><div class="node proposed"><strong>External integrations</strong>Corporate IAM / SIEM/SOC: separate acceptance.</div></div>

<!-- Sources: docs/architecture.md, docs/model-gateway.md, docs/scoped-tools.md, docs/telemetry-delivery.md. Solid green boxes are local code paths; dashed orange box marks external deployment targets. Private route requires a trusted host and separately protected upstream access. -->

---
<!-- _class: compact -->
## Human and agent: shared authority

<div class="intersection"><div class="node"><strong>HR employee</strong>Candidate + CV<br>Private HR notes</div><div class="arrow">∩</div><div class="node"><strong>HR agent</strong>Candidate + CV<br>Finance record</div><div class="arrow">=</div><div class="node result"><strong>Permitted read</strong>Candidate + CV<br>Global policy still applies</div></div>

**The same tenant does not grant access to all its data.**

<div class="columns"><div><h3>Trusted person provenance</h3><p>A local operator record or optional token exchange with a pinned issuer. Signature verification grants no extra permissions.</p></div><div><h3>Delegation up to 300 seconds</h3><p>Current scope and the original ceiling still constrain the agent. A new person or delegation retains the accounting owner and root-run budget.</p></div></div>

<div class="note">Token exchange uses generated-key tests. The no-login console trusts the computer and does not verify a corporate employee identity.</div>

<!-- Sources: docs/delegated-authority.md; accepted docs/hr-workflow.md and docs/issuer-exchange.md. Human requester, approval actor and immutable accounting principal are separate. HR browser binding uses local_demo and session-private handles, never a browser-held agent bearer. -->

---
<!-- _class: compact -->
## Tool catalog and exact consent

| Class and actual adapter | Heuristic 0–100 | Action requirement |
|---|---:|---|
| Read: documents / memory | 25 | Human and agent scope, data classes |
| Write: local fixture outbox | 75 | Allowed recipient and exact consent |
| Destructive / unknown | No adapter | Denied before execution |

<div class="note">Sum: effect + potential data + exposure + reversibility + person impact. A local policy heuristic, with no probability or legal classification.</div>

<div class="flow"><div class="node"><strong>Propose</strong>Recipient, subject, body<br>Stable key</div><div class="arrow">→</div><div class="node"><strong>Exact consent</strong>Immutable snapshot<br>Zero effect</div><div class="arrow">→</div><div class="node"><strong>Resume</strong>Current authority<br>One row, replay deduped</div></div>

<div class="warn">Changed content or authority needs new consent. Local fixture outbox, without SMTP.</div>

<!-- Sources: docs/tool-catalog.md (tool-policy-heuristic-v1, scores 25 and 75); docs/scoped-tools.md; docs/delegated-authority.md. Components for mail: 25+25+10+5+10. Read: 0+25+0+0+0. Local_record_retained is a reversibility descriptor, not a recall guarantee. Hard denials remain mandatory at every score. -->

---
<!-- _class: compact taxonomy -->
## L0–L5 and seven protection layers

| Authored scenario type | Narrow defense / explicit boundary |
|---|---|
| L0 · Accident | Text patterns and budgets / no general DLP |
| L1 · Direct known attempt | Permissions and registry / no universal detector |
| L2 · Concealment and evasion | Strict operation registry / no general normalization |
| L3 · Indirect content | Scoped reads and output checks / semantic errors |
| L4 · Authority and action abuse | Intersection, exact consent / incomplete correlation |
| L5 · Control and supply-chain target | Durable controls, quotas, metadata / unsigned feeds |

<div class="layer-strip"><span>Identity</span><span>Input</span><span>Data</span><span>Actions</span><span>Output</span><span>Resource<br>consumption</span><span>Supply<br>chain</span></div>

<div class="warn">Separate axes: scenario type and layer. Live levels unknown. OWASP: control associations.</div>

<!-- Sources: docs/threat-model.md and testdata/test-cases.json. Exact layer IDs in user order: identity, input, data, actions, output, consumption, supply_chain. Scenario labels are authored, not observed attacker sophistication. Metadata intake downloads/executes no artifacts. OWASP editions: LLM 2025 and Agentic Applications 2026. -->

---
<!-- _class: compact -->
## Operations: audit and department usage

<div class="flow"><div class="node"><strong>Minimized audit</strong>Decision and execution<br>Durable intent</div><div class="arrow">→</div><div class="node"><strong>Durable retry</strong>Retained batch<br>Visible backlog and error</div><div class="arrow">→</div><div class="node"><strong>Local collector</strong>Ack after commit<br>Event-ID deduplication</div></div>

| Department report for a selected period | What the measurement means |
|---|---|
| Issuer test: 6 known attempts, issuer_v2 | Attributed department, fixture provider |
| 120 input / 18 output tokens | Selected period, simulated tariff |
| Uncertain outcome / unknown consumption | Reservation retained, sums may be partial |

<div class="note">Dev: the proposed GitLab merge has no adapter. Finance: the proposed transfer has no adapter.</div>
<div class="warn">Local receipts and JSONL/ECS/HEC files need a separate adapter and delivery proof for SIEM. Department export is unavailable.</div>

<!-- Sources: accepted docs/department-usage.md at e6ac3564; docs/telemetry-delivery.md. Operator-only bounded selected-period report counts model attempts once, independently of three ledger scopes. Known token/money sums have known_usage_attempts denominator; dispatch_intent is not provider receipt. Accepted issuer QA at cd4c162: six known issuer_v2 provider-fixture attempts, 120 input and 18 output tokens. HR fixture window at 34bf344: two attributed attempts, one known settlement and one uncertain invalid-provider outcome with output withheld. Separate selected windows, never summed. -->

---
<!-- _class: compact standards -->
## Controls supporting specific obligations

| Framework | Technical support | Deployment obligations |
|---|---|---|
| GDPR · Articles 9 and 22 | Scope, action approval, audit | Legal basis, human involvement |
| AI Act · Articles 6, 12, 14, 26 | Audit, review, hard denial | Purpose, oversight, party duties |
| DORA | Limits, failure handling | ICT, incidents, resilience, third parties |
| OWASP · LLM 2025 / Agentic 2026 | Access, actions, disclosure, consumption | System-specific threat and gap assessment |

<div class="warn">AI Act: assess recruitment and candidate evaluation by purpose and exceptions (Art. 6, Annex III 4). HR alone does not establish classification.</div>
<div class="note">Official sources: <a href="https://eur-lex.europa.eu/eli/reg/2016/679/">GDPR</a>, <a href="https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-6">AI Act</a>, <a href="https://www.esma.europa.eu/da/node/207346">DORA</a>, <a href="https://genai.owasp.org/llm-top-10/">OWASP</a>. Controls need separate compliance assessment.</div>

<!-- Official sources checked 2026-10-04: https://eur-lex.europa.eu/eli/reg/2016/679/ ; https://www.edpb.europa.eu/system/files/2024-12/edpb_opinion_202428_ai-models_en.pdf ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/annex-3 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-6 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-12 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-26 ; https://www.esma.europa.eu/da/node/207346 ; https://genai.owasp.org/llm-top-10/ ; https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ . Interpretive control mapping: docs/standards-evidence.md. Action consent is operator approval, not GDPR data-subject consent. No deadlines or formal legal-classification verdict. -->

---
<!-- _class: compact evidence -->
## Control tests and semantic limitations

<div class="columns"><div><h3>Control behavior evidence</h3><table><tr><th>Type</th><th>Example</th></tr><tr><td>Unit</td><td>Grants, scopes, heuristic</td></tr><tr><td>Functional</td><td>Denial and exact consent</td></tr><tr><td>Integration</td><td>REST/MCP + SQLite transactions</td></tr><tr><td>Installed E2E</td><td>Wheel, browser and effects</td></tr></table><p>Base a370134: 1005 tests, zero skips.<br>0 before consent → 1 row after resume and replay.</p></div><div><h3>Frozen real Laya measurements</h3><table><tr><th>Corpus</th><th>Standard CPU</th><th>CoreML</th></tr><tr><td>v1 · 26</td><td>7/26 correct</td><td>7/26</td></tr><tr><td>v2 · 28</td><td>15/28 correct</td><td>16/28</td></tr></table><p class="note">V2: CPU/CoreML 7/6 false positives, 4/4 false negatives. Malicious paraphrases missed.</p><p class="note">V1: 16 benign cases withheld. CoreML warm run failed. The corpora differ.</p></div></div>

<div class="warn"><strong>Real HR / standard v2: false positive.</strong> Ordinary record blocked at READ and SUMMARY. Two reads executed, outputs withheld. 0 model calls and 0 messages.</div>
<div class="note">Semantic inspection off by default. CoreML experimental.</div>

<!-- Sources: root acceptance of department PR47, reviewed 40eb409 / merged e6ac3564; docs/semantic-evaluation.md, docs/semantic-v2-evidence.md, docs/release-evidence.md. Never sum overlapping suite counts. V1/v2 corpora/question sets differ; two v2 incomplete cases per backend. Actual installed HR observation at 34bf344 / standard content-role-v2 enforce, checkpoint e4e9ddf21a7b1903b7acffd8814ad4307bf63a67: benign read and summary fresh read both HTTP403 SEMANTIC_BLOCKED executed=true; zero released documents/summaries/provider attempts/outbox. Two tool reservations and four audit events; quota 0 to 2/1000. False positive, unsuitable ordinary HR semantic demo. Report SHA256 af884f87f43e58af5883f44bff0370b0b9bf981aebe496c6e402d53cccfba2de. Accepted runtime base a370134, reviewed c9c47b8 (runtime 34bf344); root gate 1005 zero skips and 18 Node contracts; separate acceptance 140 cases/420 phases; installed credential/local-console and mocked UI-only evidence separately attributed. Final ladder entrypoint reruns passed with failure-entry test retained. Control tests are not detector accuracy. -->

---
<!-- _class: lead closing -->
## Run the product and the next boundary

```sh
git clone https://github.com/bsisduck/laya-sec-agent.git
cd laya-sec-agent
./laya install --local-console
```

Prepare `uv` and the pinned Ollama model. Open the local URL. No-login console, scoped credentials for agent calls.

<div class="target-row"><div class="node"><strong>Local product scope</strong>HR, model and REST/MCP, exact consent, budgets, audit and collector.</div><div class="node proposed"><strong>Next deployment acceptance</strong>Corporate IAM, HR/mail systems, SIEM and service isolation. No bank deployment.</div></div>

[Repository and instructions](https://github.com/bsisduck/laya-sec-agent) · PDF and HTML work offline, without login.

<div class="note">Original work: policy and execution. Laya, LiteLLM, Ollama, Hermes: dependencies. Team: [to fill].</div>

<!-- Sources: README.md, docs/local-console.md, docs/local-app.md. Fresh install needs prepared dependencies/assets or network. Prepared restart can be offline. Default install without --local-console retains credential mode on a new installation. Team facts remain user-owned in docs/submission-template.md. No public-demo URL is invented. -->
