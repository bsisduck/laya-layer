# Five-minute product demo and recovery runbook

Use the [quickstart](local-app.md) and [release evidence ledger](release-evidence.md).
Record the checkout head, active policy/feed versions, prepared runtime versions,
semantic profile and state directory before recording a demo. Root owns installed
fullstack/browser QA; this runbook does not itself claim execution. Use synthetic
fixtures, private state and credentials. No heavyweight inference is needed to
exercise the deterministic steps below.

## Primary HR sequence (final delivery draft)

Final root acceptance/CI of the HR base is pending. The observed source is
`34bf344`; [HR control and real semantic evidence](hr-release-observation.md)
records the passing fixture workflow and the actual false positive separately.
For a fresh trusted-computer demonstration, prepare dependencies and the pinned
generation model, then use `./laya install --local-console`. Agent APIs still
require scoped credentials. Ordinary credential-console mode remains available.

| Step | Action | Evidence |
|---|---|---|
| Prepare HR | Preview and deliberately activate the reviewed HR delta, then bind the local employee | Preserve unrelated controls/budgets; short-lived authority; no browser-held agent bearer |
| Read and summarize | Select the ordinary synthetic candidate record | Authorized inspected read; actual configured provider result only if the source is releasable |
| Check scope | Try private HR notes and the Finance record | Each missing human/agent grant denies before protected access, even in the same tenant |
| Review message | Propose a message to the approved internal domain and inspect exact recipient/subject/body | Pending and operator approval have zero outbox effects |
| Resume and replay | Resume the original stored action, then repeat | One local fixture outbox row; no SMTP; changed payload/authority needs new consent |
| Inspect operations | Show attribution, actual-known/unknown attempts and local receipt state | Distinct attempts, simulated tariffs, partial unknown sums and collector limits |

**Actual semantic limit:** root's installed standard/content-role-v2/enforce run
at `34bf344` blocked the ordinary READ and SUMMARY source read. Both returned
403 `SEMANTIC_BLOCKED`, `executed=true`: reads occurred, outputs were withheld,
zero model-provider attempts and zero outbox rows. Quota moved 0→2/1000. This
is a false positive and unsuitable as a normal HR semantic success demo.
Do not disable an existing enforce guard to conceal it, substitute a fixture
summary or promise successful classification. Fresh-install semantic inspection
is off by default; an explicitly configured existing installation retains its
policy. CoreML remains experimental. The following historical general-purpose
sequence is an alternate demonstration, not evidence of this HR observation.

## Preparation

Prepare the pinned Ollama generation model and locked runtimes before the demo.
Choose one semantic worker only if its assets/runtime and version are already
prepared; default semantic mode is off. Native CoreML is experimental. Do not
launch standard/CoreML/agent inference concurrently with another evaluation.
Start through `./laya start`, check `./laya status`, open the printed exact
`127.0.0.1` origin and authenticate with the separate private operator token.
Use a fresh dedicated installation for initial rehearsal; preserve its spend
on every restart. Verify available budget instead of resetting state for retakes.

The root-reported installed browser suite passed document/memory/mail/controls/
export/session and responsive layouts at 390/768/1440 widths. A model smoke at
`3772ebc` reported 488 reply characters, 118 tokens (36 prompt, 82 completion),
one durable model attempt, and 4317 ms end-to-end including generation. A secret
input caused zero provider attempts. These are local root observations, not a
classifier benchmark or guard-only latency percentile. See the ledger for scope.

## Live sequence

| Time | Action | Evidence to show |
|---|---|---|
| 0:00–0:40 | Open overview and document playground; read `tenant-a-notes` | Actual allow, execution, trace and audit; controls active |
| 0:40–1:20 | Read `tenant-b-notes`, `tenant-a-contact`, `tenant-a-leak`; query own-tenant memory | Tenant denial before dispatch; email redaction; executed read with withheld secret output; no other-tenant rows |
| 1:20–2:10 | Propose mail to `reviewer@demo.internal` with a stable new idempotency key; inspect approval | Exact stored recipient/subject/body; pending has no outbox effect |
| 2:10–2:40 | Approve fingerprint; attempt changed body/key-payload conflict; retry original exact proposal twice | Approval alone has no effect; changed payload conflicts; original executes once and replay leaves one fixture outbox row |
| 2:40–3:20 | In policy editor, validate then activate a reviewed change using current version; submit stale version; activate a literal feed indicator | Atomic activation; stale CAS conflict; next applicable request blocked with new version, no dispatch |
| 3:20–4:10 | Select `local-demo`, submit a benign short prompt; show model ledger and telemetry | Actual local reply/usage; zero simulated external cost; local collector receipt/lag, not SIEM indexing |
| 4:10–5:00 | Export one scoped page; display acceptance inventory and frozen semantic evidence | Minimized export; deterministic vs real semantic vs installed-app evidence; v1 failures and v2 mistakes visible |

Use `AGENTGATE_SECRET[demo-input]` only as a synthetic secret marker to show
pre-model denial. Do not enter real secrets. For feed rehearsal, use a unique
literal in a supported stage and restore through a new valid activation, never
by editing SQLite or deleting audit records. Choose small budgets for a separate
fixture-only race demo; real generation can continue after a client timeout and
must not be used to pretend a reservation was safely released.

## Semantic and agent demonstrations

Use the frozen [v1 evaluation](semantic-evaluation.md) and [v2 summary](release-evidence.md#real-semantic-evidence-remains-imperfect)
for presentation. Record actual label, coverage and timing; never promise that
spontaneous adversarial content will be classified correctly. V2 standard real
HTTP ordinary-allow/attack-output-deny was observed in the semantic task and
root's installed CLI/browser run at `f6bccde` (quota 0→2/1000), while
ACL/DLP/quota remained authoritative. V2 is opt-in and still misses paraphrases.
Do not claim the v1 CoreML warm failure is cured by one successful v2 run.

The integrated metadata intake demo accepts the registered manifest and rejects a
changed digest without downloading or executing artifact bytes:

```sh
uv run --locked agentgate-artifacts config/artifact-demo/approved.json \
  --approved config/artifact-demo/registry.json --feed config/artifact-demo/feed.json
uv run --locked agentgate-artifacts config/artifact-demo/changed-digest.json \
  --approved config/artifact-demo/registry.json --feed config/artifact-demo/feed.json
```

The second command intentionally exits 2. See [artifact intake](artifact-intake.md).
For a real bounded agent cycle against the default installation:

```sh
uv run --locked agentgate-agent \
  --gateway http://127.0.0.1:8080 \
  --token-file "$HOME/.local/share/laya/data/client.token" \
  --transport rest --max-turns 6 --max-tokens 256 \
  --state .runtime/direct-demo.json \
  --prompt 'Call documents_read with {"document_id":"tenant-a-notes"}. After it succeeds, summarize the result without calling another tool.'
```

Use a new private state filename per run. `--transport mcp` selects MCP. The
[pinned Hermes runbook](restricted-agents.md) covers its separately prepared
runtime. Actual REST/MCP/Hermes cycles each made two model calls and one document
read, retaining usage and the exact tool-call identity. Restricting a client does
not isolate it from a privileged same-user host process.

## Restart and recovery

```sh
./laya stop
./laya start
./laya status
./laya logs
```

Prepared restart reuses installed runtimes and assets offline; shared Ollama must
remain available. Source-only updates must reinstall the gateway wheel (installer
uses `uv sync --reinstall-package agentgate`); a stale installed wheel is not
proof that the new checkout was tested. Record runtime preparation with source head.

Expired credentials require explicit renewal while stopped: `./laya renew-agent`
or `./laya renew-playground --scope tools` / `--scope model`, then start. Identity,
root spend and history must remain unchanged; revoked/active credentials cannot
be renewed. Propose and approve again under new authority as needed. Operator
session expiry requires login, not credential renewal. UI renewal uses the
separate authenticated operator/CSRF boundary. See [renewal contract](credential-renewal-contract.md).

Back up the **whole stopped state** before upgrade/restore. Unknown port ownership,
unsafe permissions, corrupt metadata, required-worker failure and unavailable
collector state are real failures; choose unused ports or investigate bounded
logs. Do not kill shared services, erase budgets, extend native deadlines or
substitute fixtures for a failed model. Collector disconnection retains a batch
for retry/replay; inspect receipt IDs, source lag and unavailable/backpressure
status. Local file export is not a delivery acknowledgment.

## Evidence package

Keep generated reports and sanitized screenshots in ignored output. Include
exact Git/runtime preparation heads, request/trace/event IDs, policy/feed version,
side-effect counts, provider attempts, ledger usage and missing suites. Use
`scripts/acceptance_matrix.py --run` for mapped controls, `make validate` for the
full deterministic gate, the existing frontend browser suite for installed UI,
and separately authorized model/semantic scripts for actual inference.

Root-reported screenshot: `.ai/qa/artifacts_fullstack/model-generation.png` in
its release worktree; include only after checking that no credential/content leaks.
A recording is evidence of the shown path, not all SDKs, vendor connectors,
production scale, SOC certification or a bank deployment.
