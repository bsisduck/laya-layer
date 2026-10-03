# laya-sec-agent / AgentGate

AgentGate is the policy-enforcement gateway specified in
`AgentGate_Full_Project_Architecture.md`. This repository currently contains the
specification and development harness. Runtime code, model workers, and product
tests have not been implemented. Cezar orchestrates development; it is not the
AgentGate gateway or a security sandbox.

## Working rules

- Read the relevant architecture sections before making product decisions.
- Commit working steps locally without asking. Push, PRs, tags, remote/shared
  changes, and messages require the user's explicit instruction, even when an
  installed skill normally publishes automatically.
- One task per branch. With an origin, start from fresh `origin/main`; until then,
  use local `main`. Use a separate Git worktree for concurrent activity. Do not
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
| Initial implementation | Architecture §§4–7, 22–23; `.ai/specs/implementation-start.md` | Python 3.12; build contracts and one vertical slice first. |
| Identity, tools, approvals | Architecture §§7–9, 14–16, 19 | Authenticate identity; explicit operation aliases; approve exact payloads; assert actual side effects. |
| Models and Laya | Architecture §§10, 13–14, 21 | Standard and native macOS CoreML are separate workers; semantic signals cannot grant permissions. |
| Budgets and persistence | Architecture §§11, 15–16 | Atomic reservations; uncertain dispatch retains budget; root budgets cover delegated work. |
| Dashboard and reporting | Architecture §§18, 24 | Report actual coverage and measured evidence; privileged admin boundary. |
| Tests and failures | Architecture §§19–21, 25; `CODE_REVIEW.md` | Separate deterministic, real semantic, and end-to-end results. |
| Public contracts | `BACKWARD_COMPATIBILITY.md`, architecture §14 | Update schema, consumers, migration notes, and tests together. |

## Validation

Run `make setup` once, then `make validate`. `make doctor` audits local tools and
skills. At this preparation stage, validation checks configuration and workflow
loading only; it is not evidence of working security controls.

The first application-code task must extend `make validate` with real lint,
typecheck, tests, and packaging checks. Do not add empty suites or no-op targets
to make a gate green. The product stack and dependency versions remain to be
resolved and locked during the first integration spike.

Use `om-code-review` for review, `om-root-cause` for diagnosis, and
`om-prepare-test-env` / `om-integration-tests` for integration QA when those tasks
exist. Use PR-producing skills only within the user's publication authorization.
