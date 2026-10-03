# Real local semantic workers

AgentGate now inspects document results through either standard Laya 0.3.24 or
native Laya-CoreML 0.2.0. This is an experimental output inspection stage, after
deterministic authorization, call reservation, execution, and synthetic-secret
checks. Semantic labels cannot grant document permissions or budget capacity.

## Start a profile

Prepare the isolated environments and pinned model files using
[the inference setup](inference-spike.md). From the repository root, initialize a
fresh private demo state once:

```sh
uv run agentgate --state-dir .agentgate/semantic-demo init-demo
```

The command writes a dedicated `worker.token` alongside the one-hour agent
credential. Neither is printed. Start the standard worker in one terminal:

```sh
uv run agentgate --state-dir .agentgate/semantic-demo semantic-worker \
  --backend laya_standard --runtime-python .runtime/laya-standard/bin/python \
  --port 8091
```

Start the gateway in another:

```sh
uv run agentgate --state-dir .agentgate/semantic-demo serve \
  --port 8001 --policy config/policy-semantic.yaml \
  --semantic-url http://127.0.0.1:8091 --semantic-backend laya_standard
```

For native Apple inference use backend `laya_coreml`, interpreter
`.runtime/laya-coreml/bin/python`, worker port 8092, and gateway port 8002.
Both profiles can share the same private state only when using the same policy;
their document calls then share the budget. The default `config/policy.yaml`
does not enable semantic checks. No automatic backend fallback is configured.

```sh
uv run agentgate --state-dir .agentgate/semantic-demo demo-read tenant-a-instructions --port 8001
uv run agentgate --state-dir .agentgate/semantic-demo audit
uv run python scripts/semantic_gateway_smoke.py \
  --state-dir .agentgate/semantic-demo --backend laya_standard \
  --gateway-port 8001 --worker-port 8091
```

The smoke script exercises real HTTP workers and gateway execution, checks
persisted semantic evidence, and writes minimized reports under ignored
`reports/generated/`. Its integration pass is separate from label accuracy.

## Contract and lifecycle

All three loopback worker routes require the dedicated bearer service credential:
`GET /internal/v1/semantic/ready`, `GET /internal/v1/semantic/capabilities`, and
`POST /internal/v1/semantic/evaluate`. Agent credentials cannot replace it.
Requests allow only request ID, the fixed `content-role-v1` question set,
`documents.read`, and bounded untrusted text. No caller-selected model, question,
checkpoint URL, or executable configuration is accepted.

The HTTP supervisor runs in the gateway environment. It launches the inference
engine with the chosen isolated Python interpreter, validates pinned assets, and
loads one model. The standard loader gets a disposable copy because upstream
normalizes tokenizer configuration. The supervisor removes that copy even after
killing its child. Model downloads are disabled during serving.

Admission is one job per worker, with no waiting queue. Startup is capped at 45
seconds. Jobs have a five-second deadline; a timeout, malformed response, or
protocol mismatch kills and reaps the child and makes readiness fail. Restart the
worker service to recover; no ambiguous call is retried. OS-level termination is
not a claim of exact device preemption. A child the OS cannot promptly reap stays
unhealthy and its scratch files are retained.

Worker ingress is limited to 64 KiB JSON and 32 KiB UTF-8 content. The adapter
accepts only loopback HTTP, no redirects/proxy inheritance, at most 16 KiB of
response, and a seven-second total request deadline. Each backend preflights its
actual tokenizer/rendering at 1,024 total tokens including question and metadata.
Over-capacity inputs, removed special markers, or collapsed options are incomplete
before inference. Runtime truncation diagnostics are also checked after inference.
This version supports one full window; it does not silently truncate long text.

Both supervisor and gateway validate IDs, backend, revision, question version,
labels, finite probabilities, coverage, token counts, and measured wall time.
The audit stores these normalized results, never the source content or service
credential. Old events still decode; semantic evidence is an additive field.

## Decision semantics and observed quality

| Result | Strict profile |
|---|---|
| Complete `task_data` | Continue deterministic output filtering and audit |
| Complete `behavior_instruction` | Withhold with `SEMANTIC_BLOCKED` |
| `unclear` / abstain | Withhold with `SEMANTIC_ABSTAIN` |
| Incomplete, invalid, or unavailable | Withhold; operational failure is never clean evidence |

Explicit `semantic_mode: observe` records complete labels without blocking on
them. It still enforces permissions, budgets, DLP, and operational failure handling.
The label is selected by model argmax; the scores are not calibrated security
probabilities, and behavior instruction is not synonymous with malicious intent.

Observed through both real gateway profiles: `tenant-a-instructions` was blocked,
`tenant-a-notes` was withheld as unclear, tenant B was denied before execution or
classification, and the synthetic secret was blocked before classification.
A separate simple report sentence was classified as task data, but with a narrow
margin over unclear. These examples establish integration behavior, not accuracy.
Original four-case loading labels remain unchanged; see the generated integration
reports and [original loading evidence](inference-spike.md).

The deterministic suite uses declared worker fixtures and actual subprocesses
for lifecycle failures; it does not download models in CI. Real standard/CoreML
HTTP checks are separate. Held-out calibration, task/action mismatch, multiple
windows, and persistent inference-token/time quotas remain to build. Tool call
limits and worker concurrency/deadlines already bound this document demo's work.
