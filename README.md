# Laya Sec Layer — AgentGate

[![Validate](https://github.com/bsisduck/laya-sec-agent/actions/workflows/validate.yml/badge.svg)](https://github.com/bsisduck/laya-sec-agent/actions/workflows/validate.yml)

[Architecture](docs/architecture.md) · [Quickstart](docs/local-app.md) ·
[Demo runbook](docs/demo-runbook.md) · [T01–T48 evidence](docs/acceptance.md) ·
[Challenge mapping](docs/challenge-alignment.md) · [Documentation](docs/README.md)

Laya Sec Layer governs model requests and registered tool execution through one
AgentGate policy boundary. It authenticates identity, enforces tenant/role/model
permissions and budgets, filters supported text, requires exact mail approval and
records minimized evidence before releasing output. Laya is an optional local
semantic signal; its predictions never grant permissions.

**Status: working local full-stack application on a trusted host.** The product
contains the gateway, packaged operator dashboard,
live policy/feed controls, scoped REST/MCP tools, private LiteLLM/Ollama model
routing, persistent budgets, local telemetry delivery, metadata intake checks and
restricted REST/MCP/Hermes agents. These components are integrated; exact validation and independent review
are tracked in the [commit/PR evidence ledger](docs/release-evidence.md).
Enterprise deployment and the limits below require separate acceptance.
Cezar is development orchestration, separate from the product.

## Run the local application

Use a complete checkout on macOS/Linux, `uv`, and an already running local
Ollama with the exact `llama3.2:1b` digest in
[the generation manifest](manifests/generation-model.json). Initial preparation
needs network access or complete dependency/model caches. Then:

```sh
./laya install
./laya status
```

Open the printed operator URL (default **http://127.0.0.1:8080/**) and log in
locally with the private `data/operator.token` file at the printed state path.
Credentials are never printed by the launcher. Agent and operator authority are
separate. Default state is `~/.local/share/laya`; ports are gateway 8080, private
proxy 4000, local contract collector 8095, and optional semantic worker 8091.
An occupied port fails; the launcher does not evict its owner or stop shared Ollama.
For a second installation, choose a new private state directory and unused ports:

```sh
./laya install --state-dir "$HOME/.local/share/laya-demo" \
  --port 8082 --proxy-port 4002 --collector-port 8096
```

Use the operator playground to read `tenant-a-notes` (allow),
`tenant-b-notes` (deny before execution), `tenant-a-contact` (email redacted),
and `tenant-a-leak` (read executed, output withheld). Memory is tenant scoped.
An internal mail proposal remains pending until exact operator approval and
resubmission; it creates one **local fixture outbox** row, never SMTP mail.
Model alias `local-demo` uses local generation; returned tool calls are proposals.

```sh
./laya stop
./laya start    # prepared offline restart; shared Ollama must still be available
./laya logs
./laya doctor   # readiness/tooling, not inference accuracy or enforcement evidence
```

See [installation, backup and explicit credential renewal](docs/local-app.md)
and [the five-minute demo](docs/demo-runbook.md). Restart preserves authority,
spend and policy. It does not renew expired/revoked credentials or reset budgets.

## Evidence and limitations

- Deterministic tests assert dispatch, outbox, ledger and audit effects. The
  [acceptance runner](docs/acceptance.md) maps the original 48 scenarios to real
  tests, frozen evaluation cases, pending work or explicit gaps.
- Semantic inspection is **off by default**. Standard Laya and native Apple
  CoreML have real loading/integration evidence, but quality is experimental.
  Frozen v1: 7/26 correct on each backend, all 16 benign cases withheld, and a
  failed CoreML warm run. V2: 15/28 standard, 16/28 CoreML, with false
  positives and missed malicious paraphrases. See [semantic evidence](docs/release-evidence.md#real-semantic-evidence-remains-imperfect).
- JSONL, ECS-oriented records and Splunk HEC envelopes are local exports.
  Actual delivery uses **Laya local HTTP contract collector v1**, at least once
  with event-ID deduplication. [Vendor adapters and bank deployments](docs/enterprise-integrations.md)
  remain unverified; no SOC/vendor certification is claimed.
- Local financial tariffs are simulated zero; quotas still consume calls/tokens.
  Unknown provider consumption retains reservations. Native same-user loopback
  operation trusts the host and does not prevent direct upstream access.
- Supported email redaction and `AGENTGATE_SECRET[...]` blocking are bounded
  examples, not general DLP or universal prompt-injection protection.

The [full architecture](AgentGate_Full_Project_Architecture.md) is the original
specification. Implementation and measured evidence are tracked separately.

## Development

Python 3.12 runs the gateway; Node 20+ is only needed for development checks and
the Cezar harness. Locked gateway and model/proxy environments stay separate.

```sh
make setup
make validate     # config, lock, lint/format, typing, deterministic tests, packaging
uv run --locked python scripts/acceptance_matrix.py --check
uv run --locked python scripts/acceptance_matrix.py --run
make doctor
make harness      # optional Cezar cockpit on 4322; does not start product tasks
```

`--run` executes mapped control checks and writes ignored evidence. It does not
run heavyweight inference or reinterpret measured semantic errors as passes. Real semantic, local-generation and browser
integration reports must name the tested commit separately.

The lower-level document demo remains available through `make demo-init`,
`make serve`, `uv run --locked agentgate demo-read` (port 8000); see
[its contract](docs/document-slice.md). It is separate from the installed app.

Read [AGENTS.md](AGENTS.md) and [SDLC.md](SDLC.md). Working commits are local;
pushes, PRs, tags, remote changes and messages require explicit user instruction.
[Open Mercato skills](https://github.com/open-mercato/skills) support development
review and QA. Their installation, setup checks and Cezar task counts are not
AgentGate delivery or real-model evaluation.

Restricted direct and pinned upstream Hermes clients are included; see
[commands, approval handling and measured evidence](docs/restricted-agents.md).
Their recorded local generation cycles used semantic inspection off; native host
access remains outside the client profile boundary.

See [two-axis threat evidence](docs/threat-model.md) for the authored L0–L5 ladder, exact seven
layers, strict frozen-corpus sidecar and unknown live-level contract. The taxonomy
adds classification/evidence presentation, not new enforcement or inference results.

An explicit [trusted-computer local console](docs/local-console.md) is available
through `./laya install --local-console`; omitted options retain credential mode
on new installations. Reinstalls remember the choice. The mode uses bounded
HttpOnly sessions and existing CSRF/agent enforcement, with no login screen or
browser credentials. Stop and reinstall with `--no-local-console` to disable it.
