# Delivery plan and skill guide

## Ordered product milestones

Each step needs a focused branch, meaningful failure-path tests, review, and a
working local commit. Keep security claims tied to demonstrated behavior.

| Step | Deliverable | Acceptance evidence | Status |
|---|---|---|---|
| 1 | Document enforcement and audit | Auth, tenant, role, no execution on denial, output filtering | Implemented; 57 deterministic tests |
| 2 | Public repository, docs, CI | Reproducible setup, architecture diagrams, hosted validation | Published; GitHub CI passed |
| 3 | Atomic tool resource budgets | Tenant/day, principal/day, root-run limits; race tests; uncertain dispatch retains reservation | Implemented; deterministic suite now 84 tests |
| 4 | Authenticated semantic workers | Both real backends; capacity and coverage validation; timeout/invalid-result denial | Loaders verified; services pending |
| 5 | Model facade and private LiteLLM | Model allowlist, per-attempt reservations, bounded output, buffered SSE | Planned |
| 6 | MCP and remaining fixture tools | Shared authorization; isolated memory; exact-payload approval and one outbox write under retry | Planned |
| 7 | Policy/feed activation and dashboard | Privileged access, valid atomic activation, event-derived reporting and export | Planned |
| 8 | Hermes and offline product demo | Both protected paths; bypass boundaries disclosed; reproducible end-to-end evidence | Planned |
| 9 | Release evidence and presentation | Independent security review; held-out classifier evaluation; acceptance map and submission assets | Planned |

Steps 3–8 may be split further when a contract or failure mode needs its own
review. No deadline or organizer confirmation is inferred from this plan.

## Which skills to use

The installed [Open Mercato collection](https://github.com/open-mercato/skills)
already provides the main delivery workflow. Start with a bounded slice of the
architecture, rather than asking a skill to implement the entire document at once.

| Need | Skill | Suggested invocation |
|---|---|---|
| Write a bounded implementation spec | `om-spec-writing` | Specify the next milestone with contracts, failure modes, and acceptance tests |
| Implement an approved spec through a PR | `om-auto-implement-spec` | Implement a specific `.ai/specs/<slice>.md` |
| Resume an existing implementation PR | `om-auto-continue-pr` | Continue the existing PR instead of creating overlapping work |
| Diagnose a bug | `om-root-cause` → `om-fix` | Reproduce the failure, then fix its cause with a regression test |
| Review code locally | `om-code-review` | Review the task diff against `CODE_REVIEW.md`; run `make validate` |
| Review a published PR | `om-auto-review-pr` | Review the specific PR and its current validation evidence |
| Prepare and exercise integration tests | `om-prepare-test-env` → `om-integration-tests` | Verify the actual gateway and worker boundaries |
| Shape the dashboard | `om-ux-shape` → `frontend-design` | Define the operator tasks, then build the interface |
| Verify the dashboard in a browser | `om-auto-qa-pr` or `om-qa-buddy` | Exercise allowed, denied, pending, failure, and empty states |
| Maintain GitHub CI | `github-actions` | Keep Actions pinned, read-only, and aligned with `make validate` |

`om-setup-agent-pipeline` is already configured; rerun it only when intentionally
changing the process. `om-discover` and `om-backlog` are useful for product
questions beyond the supplied architecture. Cezar is the development cockpit;
these skills are workflows; AgentGate is the product being built.

PR-producing skills publish and may post tracker messages by default. Invoke
them when that publication is authorized. Local review and implementation can
proceed without them. Public source publication does not certify a release;
security-sensitive changes still need the independent review in `SDLC.md`.
