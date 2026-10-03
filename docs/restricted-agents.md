# Restricted direct and upstream Hermes clients

`agentgate-agent` runs a bounded Chat Completions → tool → Chat Completions loop.
`agentgate-hermes` runs **NousResearch Hermes 0.21.5**, release `v2026.9.24`,
commit `f97608f178d1ffeca59860195ab7da295f7c8e5f`, in its own locked Python runtime.
Both use the existing gateway; neither grants permissions, issues/renews tokens,
resets budgets, approves mail, or knows the private LiteLLM key.

The gateway must expose `/v1/chat/completions`, `/v1/models`, `/v1/tools`, REST actions
and `/mcp` (`agentgate serve --mcp`). The supplied **existing** credential must have
chat and intended tool scope. Server-owned identity determines tenant, principal,
agent and root. Restarting either client with that credential retains the same
root/spend. Expired/revoked credentials stop; explicit operator renewal remains
an operator operation. Do not delete state or mint another root to evade limits.

## Direct client

From an installed checkout (`make setup`, including the MCP extra):

```sh
uv run --locked agentgate-agent \
  --gateway http://127.0.0.1:8080 --token-file .runtime/demo/client.token \
  --transport rest --max-turns 6 --max-tokens 256 \
  --state .runtime/direct-pending.json \
  --prompt 'Call documents_read with {"document_id":"tenant-a-notes"}. After it succeeds, summarize the result without calling another tool.'
```

Use `--transport mcp` to execute the same discovered tools over MCP. Both modes
intersect REST discovery with the gateway's actual MCP schemas. Only explicit
`documents.read`/`documents_read`, `memory.query`/`memory_query` and
`mail.send`/`mail_send` mappings exist. The client never exposes shell, browser,
filesystem, network fetching, memory writes, delegation or an approval tool.

The complete inspected assistant proposal and structured action response return
to the model under the **exact** `tool_call_id`. A response may propose one tool;
a run permits 2–16 model turns (default 6), bounded message/response sizes and a
five-minute CLI deadline. Truncation, undiscovered names, duplicate call IDs,
transport errors, denial, and budget exhaustion stop without retry or fallback.
The gateway still rechecks discovery permissions at dispatch.

Exit codes: 0 completed, 2 pending approval, 1 failed. The JSON output contains
inspected final text and minimized trace/call IDs, never credentials. The CLI
scrubs inherited environment credentials. Programmatic embedding is supported
through `GatewayClient` and `DirectAgent`; the embedding host owns its environment.

### Pending approval

A mail proposal returns pending with no outbox effect and no follow-up model call.
The new `--state` file holds a private transcript and action/call IDs, bound to the
same gateway, token digest, model and run limits; it contains no bearer token.
It is mode 0600 and never overwritten. Keep its parent private; it can contain
user input and inspected tool content. The operator reviews and approves the exact
stored action in the dashboard. Approval itself does not execute it.

```sh
uv run --locked agentgate-agent \
  --gateway http://127.0.0.1:8080 --token-file .runtime/demo/client.token \
  --transport rest --state .runtime/direct-pending-next.json \
  --resume .runtime/direct-pending.json
```

Use the original model/transport/limits. Resume calls only the stored action's
REST resume endpoint; no replacement payload is supplied. Once completed, the
original call ID receives the actual response and the bounded model loop continues.
If still pending, another private state file is saved and execution stops again.
An uncertain transport failure never triggers an automatic resume/retry.

With the default **email-redacting model profile**, a model-generated recipient
is withheld because changing routing fields would change the proposed action.
The approval integration fixtures explicitly set `output.redact_emails: false`
for that scenario. Secret blocking, destination allowlisting and exact approval
remain mandatory. This client does not change the operator's policy to send mail.

## Genuine restricted Hermes

Prepare online once; this fetches exact upstream source and syncs its committed
`uv.lock` with the `mcp` extra, outside the gateway environment:

```sh
uv run --locked agentgate-hermes --source .runtime/hermes-source prepare
```

After preparation the run command performs no installation or download:

```sh
uv run --locked agentgate-hermes --source .runtime/hermes-source run \
  --gateway http://127.0.0.1:8080 --token-file .runtime/demo/client.token \
  --max-turns 6 --max-tokens 256 \
  --prompt 'Call documents_read with {"document_id":"tenant-a-notes"}. After it succeeds, summarize the result without calling another tool.'
```

This invokes upstream `AIAgent.run_conversation`, tool selection/execution and
upstream MCP discovery/handlers using official MCP SDK 2.0.0, OpenAI 2.24.0 and
httpx2 2.7.0. Gateway MCP is separately locked at 2.3.0. Source must match the pinned
commit with a clean tree; missing source/runtime or an incompatible active tool
registry is **unavailable/failed**, never a successful substitute. MIT upstream
source and lock hashes are in [the runtime manifest](../manifests/hermes-runtime.json).

The restricted launcher makes these explicit adaptations to the pinned source:

- Fresh mode-0700 disposable home and working directory, a mode-0600 generated
  configuration, clean environment, disabled project/home dotenv loading, and no
  inherited upstream/operator/vendor credentials. Only the scoped gateway token
  enters the child, through stdin and its temporary MCP configuration.
- Upstream discovers one MCP server. Its actual handlers/schemas are registered
  under gateway aliases; every native registry entry is removed. Only that toolset
  is enabled. Tool Search's indirect dispatch bridge, resources, prompts, sampling
  and elicitation are disabled; the actual tool list is checked before dispatch.
- Memory/user-profile stores, context files, identity loading, compression,
  background review, checkpoints and trajectories are disabled. An empty system-prompt override suppresses Hermes' general-purpose prompt,
  which exceeds the default gateway request bound. The measured small generator
  also copied schemas into arguments under the tested short system prompts. The agent loop and MCP execution remain upstream code.
- OpenAI SDK retries are zero; Hermes attempts one model request with zero recovery
  cycles and no fallback. MCP recovery callbacks are removed. A request failure
  permanently closes the model-dispatch path for that invocation. Denied/pending
  tool results stop the upstream loop before another model request.
- The fixed model transport permits only gateway Chat Completions; it drops a
  reviewed set of inference/display metadata, sets temperature zero, caps output and prohibits new routing
  fields. It does not modify tool-call IDs or execute a model-proposed tool locally.
- A Python audit hook refuses subprocess creation, external DNS and socket
  connections outside the chosen gateway origin. Stdout/stderr are discarded;
  only the minimized result crosses back. Temporary state is removed at exit.

Hermes pending results return the action/approval IDs and stop. After operator
approval, **explicitly** reinvoke the same exact mail request/key with the same
credential. The gateway consumes the stored approval once; any changed payload
fails or requires a new approval. No automatic polling/retry or agent approval
exists. Unlike the direct client, this profile does not persist a Hermes transcript
for resumption. Deterministic upstream tests exercise explicit reinvocation.

These are client restrictions and Python-level defense in depth, **not an OS
sandbox**. Trusted native code, the interpreter/dependencies and same-user host
access remain outside isolation. Another process under the OS user can read files
or contact Ollama; private runtime/home alone cannot prevent that. No claim covers
stock Hermes, other profiles/plugins, or a compromised runtime.

Pinned source references: [agent initialization](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/agent/agent_init.py),
[MCP registration and trust](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/tools/mcp_tool_registration.py),
[MCP recovery handlers](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/tools/mcp_tool_handlers.py),
[configuration](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/cli-config.yaml.example).
The architecture's illustrative `key_env` configuration was not assumed to work.

## Reproduce the evidence

Deterministic protocol and actual HTTP/SQLite checks run in `make validate`.
To additionally invoke the real prepared Hermes runtime against the deterministic
provider (no heavy model inference):

```sh
AGENTGATE_HERMES_SOURCE="$PWD/.runtime/hermes-source" \
  uv run --locked pytest tests/test_agent_client.py tests/test_agents_http.py tests/test_hermes_profile.py
```

Without that variable the upstream-dependent cases are explicitly skipped. Unit
profile checks do not substitute for upstream execution. These fixtures prove
correlation, root accounting, zero/one effects and denied paths; they do not measure
model quality or Laya classification.

The separate actual-generation runner starts its own HTTP gateway and invokes the
CLI clients sequentially, using persistent private state. It never renews a token
or clears spend and terminates only its owned gateway. A shared evaluation lock
and active-worker check reject overlap with Laya. Coordinate with other inference
users before running; a socket timeout does not prove Ollama compute has stopped.

```sh
uv run --locked python scripts/agent_clients_smoke.py \
  --state-dir .runtime/agent-demo \
  --assets-root /path/to/shared/laya-sec-agent \
  --upstream-token-file /path/to/private/upstream.token \
  --hermes-source .runtime/hermes-source
```

Requires the already prepared authenticated LiteLLM at loopback port 4001 and
Ollama `llama3.2:1b`. The upstream token file goes **only to the gateway**, never
to either agent. The runner uses `config/policy-models.yaml`: **semantic inspection
is disabled**. This proves generator/gateway/tool integration, not real Laya
protection. Standard/CoreML semantic quality and enforcement have their own
[evaluation report](semantic-evaluation.md). No cloud fallback or model download.
Minimized generated reports stay ignored under `reports/generated/`. Report files
are never overwritten; select a fresh `--report` path for another explicit run.
`--clients hermes-mcp` can measure only Hermes without repeating the direct runs.

## Measured generation evidence — 3 October 2026

Final CLI runs used committed client profile `f07add0d28768bffd8b89801f26f76d2449e2b39`
on main `4a1fe3d`, real authenticated HTTP gateway, existing private LiteLLM
1.103.2 and user-owned Ollama 0.35.1. The generator was `llama3.2:1b`, 1.2B Q8_0,
manifest digest `baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878`.
Hermes source/runtime is pinned above; its actual upstream loop and MCP handlers
ran in the isolated runtime. No weights, generated reports or runtime logs ship.

| CLI | Model calls / document reads | Exact proposal → result call ID | Elapsed |
|---|---:|---|---:|
| Direct REST | 2 / 1 | `call_9k25z3oi` | 4458.2 ms |
| Direct MCP | 2 / 1 | `call_mwdhfmew` | 3322.7 ms |
| Genuine Hermes MCP | 2 / 1 | `call_spx2ryxv` | 6456.7 ms |

Each final response released inspected text. Every dispatch has persisted intent
and completion events. All three used tenant-a / run-demo from the same existing
credential. Hermes exposed exactly documents_read, mail_send and memory_query.
Its document trace was `trace-385fa10d976f4d37ad93f3ace38e5d7b`, between model
traces `trace-63703afb88214e4781bbe58a4504068b` and
`trace-17214e86290c424c89e436c2a47f376f`. The final report asserts exact call-ID
correlation, dispatch counts and one root, and records minimized trace/audit IDs,
policy/client source hashes and cumulative budget counters.

**Development failures remain part of the evidence.** Five earlier explicit
Hermes invocations generated malformed arguments and stopped with zero tool
dispatch and no model retry. A diagnostic confirmed that the small generator
emitted JSON Schema fields instead of a document_id instance. Changing schema
serialization order or short system instructions did not resolve it. Suppressing
the system prompt produced a successful two-call Hermes cycle (7900.4 ms), then
the final run above reproduced it. No malformed proposal was repaired, replayed
automatically or executed outside the gateway. This is prompt-sensitive local
integration evidence, not a generator reliability or answer-quality benchmark.

Across development and final runs the same root retained **17 model calls, 5699
tokens and six document reads**; no reservations remained and the outbox stayed
empty. No spend reset, token renewal or replacement root was used. All owned
gateway/agent children were reaped before releasing the shared inference slot;
the user's Ollama service was left running.

The runtime policy was `config/policy-models.yaml`: **semantic inspection disabled**.
Hard gateway controls and fixtures were exercised; these agent cycles do not
prove real Laya protection. The separate versioned semantic evaluation records
actual standard/CoreML classifier behavior and its substantial quality limits.

Minimized local report SHA-256 identifiers (failed attempts retained):

| Report | SHA-256 |
|---|---|
| agent-clients.json | `34cef56ebd259bb35112c8a88a4ca1ad80dbfa1b54a0b906349503a25c88f0d3` |
| agent-clients-hermes-temperature0.json | `918ea9a12b657651a1ecf37e92c999e1fce389682cbac05064066803e9ad16c5` |
| agent-clients-hermes-diagnostic.json | `80e2d29bad787a3d8623b3f1b82614b40a76cd816d5a76fecc4c6fe5bf452696` |
| agent-clients-hermes-stable-schema.json | `51a398e1e02b42f1e8f152946636fe915f6c9991b772cc035a9b7d9bad85e25d` |
| agent-clients-hermes-minimal-prompt.json | `d695d99c1b808492931472d8116e5792f7b693238397cd4998ef8d1e6b858f81` |
| agent-clients-hermes-no-system.json | `7c46065bfbe154b6de9db5ecbbb549b944bacf8c27718ee8016ab1b01698e6a9` |
| agent-clients-final.json | `a2761469f02b9029dd591f4d3b472b0bb94862caec114a2951907ec8fbd68a85` |

The complete deterministic gate and final author review are recorded on PR #30.
A separate 55-test client run includes all ten genuine Hermes subprocess cases
with a deterministic provider; these exercise denied paths, exact response/call
correlation and one approved outbox effect. They are not real-model evaluation.
