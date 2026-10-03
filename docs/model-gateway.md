# Governed local model calls

The model facade adds `GET /v1/models` and `POST /v1/chat/completions`. An agent
credential must include `chat.completions`; the identity, tenant and root budget
come exclusively from that credential. Client URL, key, identity, model-registry
and fallback overrides are rejected. The registered P0 alias is `local-demo`.

`config/policy-models.yaml` enables this path. `config/policy.yaml` continues to
be the document profile. The model adapter is optional and imports no inference
framework into the gateway. Its separate environment is pinned in
`requirements/litellm.txt`, including Prisma error types required by this LiteLLM
version's authentication error handler. No Prisma database is configured.

## Local run

The full application launcher builds on these primitives. For the isolated model
profile, initialize a fresh private state with `agentgate --state-dir PATH
init-demo`. Install the proxy separately using `uv venv --python 3.12
.runtime/litellm` and `uv pip sync --python .runtime/litellm/bin/python
requirements/litellm.txt`. Prepare Ollama's `llama3.2:1b` locally; this profile never
selects a cloud model. Set `LITELLM_MASTER_KEY` from a private file, then run:

```sh
.runtime/litellm/bin/litellm --config config/litellm-local.yaml \
  --host 127.0.0.1 --port 4001 --telemetry False
uv run --locked agentgate --state-dir PATH serve --policy config/policy-models.yaml \
  --model-url http://127.0.0.1:4001/v1 --model-token-file PRIVATE_KEY_FILE
```

Keep `PRIVATE_KEY_FILE` outside version control with mode 0600. Only the gateway
receives that upstream credential; clients receive the separate scoped credential.
Disable external cost-map fetching with `LITELLM_LOCAL_MODEL_COST_MAP=True`; run
the proxy without inherited cloud API keys. Native loopback is a trusted-host
deployment: another process owned by the same OS user can contact Ollama directly.
This does not claim OS isolation or complete host-wide AI enforcement.

## Enforcement and accounting

Input is bounded and inspected before any upstream call. Synthetic secrets block;
supported email addresses are redacted on input and output. Required semantic
analysis fails closed on unavailable, incomplete or abstaining enforce results.
The optional semantic worker has the same standard/CoreML boundary as tool output.

The gateway requests a complete upstream response. Even when the client selects
`stream: true`, it emits SSE only after the entire content and tool arguments pass
inspection and the outcome/usage transaction commits. This intentionally delays
the first token. Returned tool calls preserve IDs and still require a separately
authorized tool execution. Only one tool proposal is accepted per model response.

Each dispatch atomically rechecks its credential, writes intent and reserves calls,
tokens and integer micro-USD in tenant-day, principal-day and tenant/root scopes.
Delegated principals share the root scope. Local prices are zero; nonzero tariffs
are explicitly simulated test prices, not external invoice guarantees. An input
reservation uses serialized UTF-8 bytes plus a template allowance; output reserves
the requested cap. Usage beyond a bound is recorded and freezes affected scopes.

Timeouts, malformed usage and uncertain disconnects retain their reservation and
admission slot across restart. A socket timeout does not prove that native model
work stopped. No hidden retries/fallbacks are configured, and blocked output still
incurs recorded usage. Do not delete reservations to make a stalled demo green;
operator reconciliation must establish what happened before releasing capacity.

## Verified evidence

`tests/test_models.py` covers denied-path provider calls, atomic boundary races,
delegated roots, synthetic DLP, buffered output, tool correlation, money simulation,
unknown/malformed usage, restart retention and audit failure before/after dispatch.
This deterministic suite uses a clearly marked observed provider fixture.

The separate real integration command is:

```sh
uv run --locked python scripts/model_smoke.py --upstream-token-file PRIVATE_KEY_FILE
```

It starts a real HTTP gateway, calls the private proxy and local model, executes a
model-proposed document tool, returns its correlated result, and obtains a model
summary. It also verifies unauthenticated upstream/gateway rejection and zero new
dispatches for a secret or unknown alias. Generated evidence remains under ignored
`reports/generated/` and contains no credentials or raw prompts/documents.

On 2026-10-03 the actual cycle passed with LiteLLM 1.103.2 and Ollama
`llama3.2:1b`, digest
`baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878`.
Measured model request times were 2,218.6 ms (generation), 1,656.0 ms (tool
proposal), and 1,338.0 ms (result summary). These are three local observations,
not percentiles or a quality benchmark. The 1B model needed an explicit argument
example; an earlier ambiguous instruction returned incorrectly shaped arguments.

Provider configuration follows the [LiteLLM configuration reference](https://docs.litellm.ai/docs/proxy/configs)
and [Ollama adapter documentation](https://docs.litellm.ai/docs/providers/ollama).
The gateway supplies the enforcement and durable ledger; neither vendor integration
nor this fixture demonstration certifies a bank deployment.
