# AgentGate development workflow

The current phase is prototype implementation in the public
`bsisduck/laya-sec-agent` repository. `main` is the base. GitHub Actions runs
`make validate`; GitHub is the tracker, labels are disabled, and the QA gate is
enabled in `.ai/agentic.config.json`. Public source is not a production release.

## Delivery flow

| Stage | Action | Evidence |
|---|---|---|
| Intake | Scope a task against the architecture and record acceptance criteria. | Local task brief or, when authorized, tracker issue. |
| Triage | Verify existing behavior and overlapping work (`om-verify-in-repo`). | Confirmed change surface. |
| Design | Resolve relevant contracts; use `om-ux-shape` for UI work. | Bounded plan and required states. |
| Implement | Work on one branch; commit successful steps frequently. | Working code and relevant tests. |
| Review | Read the diff with `om-code-review` and `CODE_REVIEW.md`; fix findings. | Validation results and remaining risks. |
| QA | Exercise changed paths with side-effect evidence and UI states where relevant. | Results tied to the tested commit. |
| Publish | Only on explicit instruction: push and open the requested PR. | Reviewable PR against `main`. |
| Merge/release | Only on explicit instruction and after required checks and QA. | Revertable, validated change. |

The author owns implementation and evidence. The reviewer checks correctness,
security, and contracts. A QA reviewer exercises consequential behavior. The
maintainer owns process changes and release decisions. Roles can be combined for
low-risk work; authentication, tenant isolation, approvals, and money require an
independent review before release, or an explicit maintainer exception.

## Validation gate

The configured command is `make validate`. It checks workflow artifacts and the
Cezar configuration, verifies `uv.lock`, runs Ruff lint and formatting, strict
mypy, pytest, and builds a source distribution and wheel. Tests cover only the
implemented document path; real inference checks and future integration suites
remain separate. Local success does not imply CI success.

Any failing required check blocks completion. Report which deterministic,
real-semantic, and integration suites ran or were skipped, and why.

## Tracker and QA conventions

While labels are disabled, keep claims and review/QA status in local task records.
Do not mutate issues or PRs without the user's publication authorization.
When tracker operations are authorized, use `.ai/trackers/github.md` and check
for an existing assignee, active claim, or overlapping PR before claiming work.

If labels are later enabled, pipeline states are mutually exclusive. Category
and metadata labels are additive; priority and risk each have one value.
`in-progress` means active work, while `ci-monitoring` means only a CI follow-up
is pending. Release claims when work ends.

A `needs-qa` PR cannot merge without `qa-approved` evidence tied to its current
commit. Never combine `needs-qa` with `skip-qa`, and never infer QA approval from
an authoring skill's successful run. Self-QA requires explicit authorization and
evidence and is not available for high-risk changes without a maintainer exception.
Any pending or failed required CI check still blocks merge. CI waiting is bounded
to 40 minutes; a timeout means pending, not passed.

## Automation and changes to this workflow

`make harness` starts Cezar with the `agentgate-local` workflow available. Its
launcher disables background automations and child-task dispatch. The workflow
implements one requested task, reviews it, and runs validation. It does not grant
permission to publish. Other upstream workflows remain subject to `AGENTS.md`.

Change this document and `.ai/agentic.config.json` together when the toolchain or
workflow changes. The optional `om-setup-discovery-pipeline` adds product discovery
if needed; the supplied architecture already provides the current implementation brief.
