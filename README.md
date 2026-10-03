# laya-sec-agent — AgentGate

[![Validate](https://github.com/bsisduck/laya-sec-agent/actions/workflows/validate.yml/badge.svg)](https://github.com/bsisduck/laya-sec-agent/actions/workflows/validate.yml)

[Visual architecture](docs/architecture.md) · [Documentation](docs/README.md) ·
[Delivery plan and skills](docs/delivery.md)

AgentGate is a policy-enforcement gateway being built for agentic applications.
The first working slice authenticates document reads, enforces tenant/role/agent
permissions, filters output, and persists minimized audit events. The complete
target design is in [the architecture](AgentGate_Full_Project_Architecture.md).

**Status: document-enforcement prototype.** Atomic call budgets and authenticated
standard Laya / native CoreML workers are implemented. The optional semantic
profile inspects document results before release; classification is experimental.
Model routing, approvals, MCP, Hermes, and the dashboard remain to build.
The product is also referred to as **Laya Sec Layer**. See the
[challenge coverage](docs/challenge-alignment.md) and
[enterprise integration design](docs/enterprise-integrations.md) for the supplied
PDF requirements and proposed bank-stack connections. Local event export is
implemented; live vendor and bank integrations are not yet verified.

## Run the document demo

```sh
make setup
make demo-init   # once: private .agentgate/ state; one-hour tenant-A credential
make serve      # http://127.0.0.1:8000
```

In a second terminal:

```sh
uv run agentgate demo-read                     # allowed; records intent and outcome
uv run agentgate demo-read tenant-b-notes      # denied before execution
uv run agentgate demo-read tenant-a-contact    # email redacted before release
uv run agentgate demo-read tenant-a-leak       # synthetic secret withheld after read
uv run agentgate audit                         # minimized local event records
uv run agentgate budgets                       # reserved and spent tool attempts
uv run agentgate audit-export --tenant tenant-a --format ecs  # one local export page
```

Denied reads exit with code 1. Credentials are written with mode 0600 and never
printed by initialization. The SQLite credential table stores only their digest
and server-owned identity. `init-demo` refuses to overwrite existing state. For a
fresh session, use `--state-dir .agentgate/session-2` before each subcommand.

The partial policy lives in `config/policy.yaml`; restart to apply changes.
Use [the semantic worker runbook](docs/semantic-workers.md) to run real Laya or
CoreML inspection. A required but unavailable worker fails readiness and dispatch.
The output scanner covers the explicit synthetic marker
`AGENTGATE_SECRET[...]` and a bounded email pattern; it is not general DLP.
The loopback demo assumes trusted host processes and registered fixture executors.
See [the implemented contract](docs/document-slice.md) for precise boundaries.
The [export runbook](docs/audit-export.md) covers formats, privacy and resumable pages.
Existing schema-1 state needs the [budget migration](docs/budgets.md#upgrading-existing-local-state)
before starting this version. Fresh demo initialization needs no migration.

## Development

Node 20+ runs the Cezar development harness; Python 3.12 is the application
runtime. From this directory:

```sh
make setup       # install locked Python and development tooling
make validate    # config, lock, lint, format, typing, tests, and package build
make doctor      # inspect host tools and installed Open Mercato skills
make harness     # start Cezar; select the agentgate-local workflow
```

Cezar opens at http://localhost:4322, with project-local workspace state under
the ignored `.ai/cezar/home/`. If that port is in use, run
`npm run harness -- --port 4323`. The runner is Codex using its existing login and
native model configuration. The launcher disables background automations and
child-task dispatch. No coding task starts merely by opening the cockpit.
Work done directly in a Codex chat is not automatically a Cezar task. Use
`make harness-verify` to record a real validation run in its Tasks view; see
[where progress appears](docs/cezar.md). Local task history is intentionally
excluded from Git; a fresh checkout starts with an empty cockpit.

The private `package.json` and npm lockfile belong to development tooling.
`pyproject.toml` and `uv.lock` define the gateway. Real Laya loading checks use
separate environments; see [the inference spike](docs/inference-spike.md).

Read [AGENTS.md](AGENTS.md) and [SDLC.md](SDLC.md) for workflow rules. Local commits
are automatic; publishing requires an explicit user instruction. The public
repository is [bsisduck/laya-sec-agent](https://github.com/bsisduck/laya-sec-agent).
GitHub Actions runs the same deterministic validation gate on pushes and PRs.
Real inference remains a separate, hardware-dependent check.

## Skills and next work

The Cezar catalog uses [Open Mercato skills](https://github.com/open-mercato/skills)
at the commit in `.ai/cezar/config.json`. Codex and Claude Code can also use the
globally installed collection. `make doctor` checks local coverage; machine
installations are separate from the pinned Cezar catalog.

See [readiness](docs/readiness.md) for verified tools and remaining prerequisites,
and [the first implementation slice](.ai/specs/implementation-start.md) for the
next task. Optional product discovery is available through
`om-setup-discovery-pipeline`.
