# laya-sec-agent / AgentGate

AgentGate is the policy-enforcement gateway specified in
`AgentGate_Full_Project_Architecture.md`. This repository currently contains the
specification and a working local full-stack prototype: document/scoped-tool REST
and official-SDK MCP enforcement, exact approvals/local fixture outbox, model
routing through private LiteLLM, packaged operator UI, live controls, persistent
budgets and a local telemetry contract lab. Optional standard/CoreML semantic
inspection is experimental; keep frozen poor/failed results visible. Consult
`docs/release-evidence.md` for exact commits and final release review evidence.
Metadata intake and restricted direct/MCP/Hermes clients are integrated.
Cezar orchestrates development; it is not the
AgentGate gateway or a security sandbox.

## Working rules

- Read the relevant architecture sections before making product decisions.
- Commit working steps locally without asking. Push, PRs, tags, remote/shared
  changes, and messages require the user's explicit instruction, even when an
  installed skill normally publishes automatically.
- One task per branch. With an origin, start from fresh `origin/main`; until then,
  use local `main`. An explicitly requested integration base overrides that default
  (for release documentation: `origin/implement/full-stack-release`). Use a separate
  Git worktree for concurrent activity. Do not
  spawn agents unless requested or explicitly required by an applicable skill.
- Keep shared history intact. Never force-push shared branches. Review the diff,
  run the applicable validation, and leave a clean working tree at handoff.
- Never commit credentials, host-specific settings, runtime state, model weights,
  dependency directories, generated reports, or build output.
- Distinguish proposed, implemented, fixture-tested, and real-model-verified work.
- Save unfinished-task checkpoints under `~/.codex/handoffs/` without secrets.

## Task routing

| When the task involves… | Read first | Key rules |
|---|---|---|
| Development workflow | `SDLC.md`, `.ai/agentic.config.json`, `.ai/cezar/config.json` | Local publication boundary wins over skill defaults. |
| Implemented document path | `src/agentgate/`, `tests/test_gateway.py`, `config/policy.yaml` | Credential-owned identity; durable intent before reads; audit before output release. |
| Initial implementation | Architecture §§4–7, 22–23; `.ai/specs/implementation-start.md` | Python 3.12; build contracts and one vertical slice first. |
| Identity, tools, approvals | Architecture §§7–9, 14–16, 19 | Authenticate identity; explicit operation aliases; approve exact payloads; assert actual side effects. |
| Models and Laya | Architecture §§10, 13–14, 21 | Standard and native macOS CoreML are separate workers; semantic signals cannot grant permissions. |
| Budgets and persistence | Architecture §§11, 15–16 | Atomic reservations; uncertain dispatch retains budget; root budgets cover delegated work. |
| Dashboard and reporting | Architecture §§18, 24 | Report actual coverage and measured evidence; privileged admin boundary. |
| Tests and failures | Architecture §§19–21, 25; `CODE_REVIEW.md` | Separate deterministic, real semantic, and end-to-end results. |
| Public contracts | `BACKWARD_COMPATIBILITY.md`, architecture §14 | Update schema, consumers, migration notes, and tests together. |

## Validation

Run `make setup` once, then `make validate`: workflow/config checks, lockfile
consistency, Ruff lint/format, strict mypy, pytest, and source/wheel packaging.
`make doctor` audits local tools and skills. Python 3.12 and gateway dependencies
are locked in `uv.lock`. Keep model environments separate from the gateway.
Use `scripts/acceptance_matrix.py --check` / `--run` for T01–T48 mapping and
control evidence. Inventory/pytest success is not 48 semantic successes.
Real inference smoke runs are separate from the deterministic gate; never report
the gateway suite as real-model evaluation. Do not add empty or no-op test targets.

Use `om-code-review` for review, `om-root-cause` for diagnosis, and
`om-prepare-test-env` / `om-integration-tests` for integration QA when those tasks
exist. Use PR-producing skills only within the user's publication authorization.
