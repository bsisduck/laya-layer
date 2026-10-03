# laya-sec-agent — AgentGate

AgentGate is a planned policy-enforcement gateway for agentic applications,
combining deterministic controls with local Laya decisions. The complete design
is in [the architecture](AgentGate_Full_Project_Architecture.md).

**Status: development setup prepared; gateway and inference not implemented.**

## Development

Node 20+ runs the Cezar development harness; Python 3.12 is the planned application
runtime. From this directory:

```sh
make setup       # install locked development tooling
make validate    # check setup and load the Cezar workflow
make doctor      # inspect host tools and installed Open Mercato skills
make harness     # start Cezar; select the agentgate-local workflow
```

Cezar opens at http://localhost:4322, with project-local workspace state under
the ignored `.ai/cezar/home/`. If that port is in use, run
`npm run harness -- --port 4323`. The runner is Codex using its existing login and
native model configuration. The launcher disables background automations and
child-task dispatch. No coding task starts merely by opening the cockpit.

The private `package.json` and lockfile belong to development tooling, not the
future Python gateway. `make validate` currently verifies setup only. The first
implementation must add meaningful application lint, typing, tests, and build checks.

Read [AGENTS.md](AGENTS.md) and [SDLC.md](SDLC.md) for workflow rules. Local commits
are automatic; publishing requires an explicit user instruction. There is no
project Git remote yet.

## Skills and next work

The Cezar catalog uses [Open Mercato skills](https://github.com/open-mercato/skills)
at the commit in `.ai/cezar/config.json`. Codex and Claude Code can also use the
globally installed collection. `make doctor` checks local coverage; machine
installations are separate from the pinned Cezar catalog.

See [readiness](docs/readiness.md) for verified tools and remaining prerequisites,
and [the first implementation slice](.ai/specs/implementation-start.md) for the
next task. Optional product discovery is available through
`om-setup-discovery-pipeline`.
