# Delivery plan and skill guide

## Current product milestones

Status after integration of reviewed installer, semantic profiles, artifact intake
and restricted-agent clients.
See [the evidence ledger](release-evidence.md) for exact commits and [acceptance](acceptance.md)
for T01–T48 mappings; test counts are not completion percentages.

| Deliverable | Evidence | Status / remaining gate |
|---|---|---|
| Document/memory/mail enforcement and MCP | Scoped identity, actual fixture effects, immutable approval and replay tests | Integrated; local outbox only |
| Model facade/private LiteLLM | Allowlist, input/output inspection, atomic call/token/money ledger, actual local cycle | Integrated; buffered output, local zero/simulated tariffs |
| Operator/live controls | Separate sessions/CSRF, policy/feed CAS, explicit renewal, root installed browser checks | Integrated prototype; final root current-head review/CI remains |
| Standard/native CoreML | Frozen v1/v2 reports and real CPU gateway smoke | V2 merged, opt-in; v1 poor/failed evidence retained; CoreML experimental |
| Resource accounting | Shared-root tool/model budgets and persistent worker call quota | Integrated; full cumulative physical-resource governance incomplete |
| Evidence delivery | Scoped exports, durable sender and installed local collector | Local contract lab only; vendor/bank acceptance unverified |
| Install/offline restart | Owned gateway/proxy/collector, prepared runtime reuse, preserved authority/ledgers | Installer22 merged; final installed source/runtime provenance required |
| Artifact intake | Exact approved metadata tuple and no-download/execution probes | Integrated from reviewed PR28; metadata simulation only |
| Restricted direct/Hermes clients | Actual REST/MCP/Hermes two-model/one-document cycles; independently reviewed source and 584 checks | Integrated from reviewed PR30; trusted host, restricted profile |
| Documentation/submission assets | Truthful quickstart, diagrams, requirement map, inventory, nine-slide EN/PL sources/PDFs | Reviewable docs package; user fills team/submission facts; root final status refresh |

No organizer confirmation, enterprise deployment, certification or submission
follows from this development plan. [Challenge alignment](challenge-alignment.md)
records the supplied requirements and discrepancies; bank adapters extend
reporting and remain separate acceptance work.

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
