# Development readiness — 3 October 2026

This record covers development preparation and the first document-only slice on
the inspected Apple Silicon Mac. It does not certify the full proposed MVP.

## Current implementation

The REST document path now enforces scoped credentials, tenant/role/agent
permissions, bounded requests, filtered output, and a durable minimized audit.
`make validate` runs lockfile, lint/format, typing, 84 tests, and package builds.
Atomic tenant/day, principal/day, and root-run tool budgets are also implemented;
see [tool budgets](budgets.md) for accounting semantics and schema migration.
Live HTTP checks verified allowed, denied, redacted, blocked-output, and missing-
credential cases. See [the implemented contract](document-slice.md).

Actual standard Laya and native CoreML loading also succeeded on pinned assets.
Both matched 2/4 expected smoke labels, agreeing on all four. These standalone
runs are not connected to the gateway. See [the inference spike](inference-spike.md).

## Harness and skills

- [Cezar](https://github.com/open-mercato/cezar) 0.14.0 is installed as a pinned
  development dependency; transitive versions are recorded in `package-lock.json`.
  An existing separate Cezar 0.10.1 cockpit was found on port 4321 and left running.
  `make harness` uses port 4322 and its own ignored `.ai/cezar/home/` workspace.
- `.ai/cezar/config.json` selects Codex with its native model configuration and
  the [Open Mercato skills](https://github.com/open-mercato/skills) source at
  `2b5647fd35048ee391c7a3dea0e944bd2cdadf07`.
- 41 Open Mercato skills were already installed globally. The missing
  `om-qa-buddy` was installed from that commit, with Codex and Claude Code links.
  The global collection now has 42 skills; existing global skills were not upgraded
  and may differ from the pinned Cezar catalog. The newly installed skill is
  available to Codex on the next turn.
- GitHub and browser provider descriptors were copied from the installed
  `om-setup-agent-pipeline` skill. The public repository is
  [bsisduck/laya-sec-agent](https://github.com/bsisduck/laya-sec-agent); labels remain
  disabled. Hosted CI passed for the first published baseline.
- `agentgate-local` implements one task, reviews it, and validates locally.
  Launch with `make harness`. The launcher disables automatic skill updates,
  background automations, and child-task dispatch.

## Verified host inventory

| Capability | Observed status |
|---|---|
| Host | macOS 27, arm64 |
| Git | 2.49.0 |
| Codex | 0.160.0, logged in through ChatGPT |
| Claude Code | 2.1.288 installed; authentication not tested |
| Node / npm | 22.23.1 / 10.9.8 |
| Python | 3.12.13 available explicitly; default `python3` is 3.14.6 |
| uv | 0.12.8 |
| Docker | Engine 29.7.2 reachable |
| Ollama | Service reachable; local model inventory returned |
| Swift | 6.3.3, Apple Silicon target |
| Browser QA | agent-browser 0.35.2 checksum verified; Chrome installed; doctor passed |
| GitHub CLI | Upgraded from 2.74.0 to 2.101.0; existing authentication retained |

`make doctor` repeats the read-only tool and skill checks. It does not install
dependencies, start application services, send model requests, or print tokens.
The browser doctor launches a temporary headless browser to verify it works.

## Validation evidence

- Preparation checks passed, including Cezar's actual config and workflow loaders;
  the gate has since been extended to Python implementation checks above.
- Cezar 0.14.0 HTTP startup/health verified the project, Codex runner, disabled
  automation/dispatch, and loaded local workflow. No coding agent task was launched.
- The pinned upstream catalog resolved to all 42 Open Mercato skills. Global
  skill coverage and cross-skill file references also passed.
- Browser QA doctor completed a real headless launch with no failures.
- npm reported no known vulnerabilities in the 17-package development-tooling tree
  at installation time; this is not a security audit of AgentGate.

## Remaining prerequisites

1. Public source and deterministic CI are configured. Production release still
   needs independent security review and the remaining integration evidence.
2. Confirm the competition start-time ambiguity documented in architecture §2
   before competition implementation. Judging weights and cross-category eligibility
   also remain organizer questions.
3. Implement authenticated semantic worker services around the verified loaders;
   enforce token/coverage/time limits and define handling for `unclear`. Dependencies
   and asset hashes are now pinned. Keep CoreML native, outside Linux containers.
4. Extend call budgets to inference/provider resources; add approvals, policy
   reload, feeds, and the other architecture controls.
5. Select and test a local tool-capable generation model. Existing Ollama models
   have not been validated for this workflow; generation is separate from Laya.
6. Implement and verify LiteLLM, MCP, and Hermes integration. Available development
   tools do not establish application integration compatibility.

The initial task and next slices are recorded in
[implementation-start.md](../.ai/specs/implementation-start.md). Follow the
architecture's separate deterministic, real-semantic, and end-to-end suites.
The pytest cases include parametrizations of a subset of the architecture's
48 planned scenarios; they are not a claim that all 48 scenarios are implemented.
