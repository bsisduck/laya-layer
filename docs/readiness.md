# Release readiness and evidence — 3 October 2026

The local full-stack application has integrated implementation and validation. See the
[claim ledger](release-evidence.md) for exact commits, merged versus open PRs,
frozen semantic measurements and root-reported installed QA. This record does
not certify production readiness or challenge completion.

## Repeatable gates

```sh
make setup
make validate
uv run --locked python scripts/acceptance_matrix.py --check
uv run --locked python scripts/acceptance_matrix.py --run \
  --output reports/generated/acceptance-controls-readiness.json
```

`make validate` checks workflow/config, lock consistency, Ruff, strict mypy,
pytest and source/wheel packaging. Its deterministic tests include fixture
providers/native child protocols and real SQLite/loopback transport. It does not
load Laya, certify semantic accuracy or substitute for installed browser/local
model QA. No empty proposed `make test-e2e`/`eval-*` target is claimed.

Integrated head `074cace` passed **614 tests with zero skips**, six JavaScript
contracts and 139 mapped control observations; both CI checks passed. The installed
browser suite at `b740c35` passed full tool/control/session flows with actual
local generation and collector delivery. Component and final integration review
references remain in [release evidence](release-evidence.md) and PR31.

## Runtime preparation

Use `./laya install`, then `./laya status` and the exact printed operator origin.
`./laya start` reuses prepared runtimes without package resolution; Ollama must be
running with the pinned local generation digest. Installer/source changes must
reprepare the installed wheel (`--reinstall-package agentgate`); record the
runtime source head. A healthy old wheel cannot validate new source.
`./laya doctor` and `make doctor` audit preparation/tooling only.

Default semantic mode is off. Optional standard Laya and native CoreML use
separate environments/assets. Choose one and run actual evaluation only in an
exclusive, explicitly scheduled slot. Actual installed standard-v2 and local-generation observations are recorded in
the release ledger; deterministic validation does not repeat that inference. Keep
v1 frozen evidence and the CoreML warm failure. V2's opt-in real standard gateway
smoke does not turn 15/28 standard or 16/28 CoreML holdout into an approved
security detector. CoreML remains experimental.

## Remaining release and deployment gates

1. Reviewed artifact intake, restricted agents and semantic profiles are integrated.
   Keep the exact independent review and validation references with each release.
2. Reprepare the installed wheel after source changes; retain source/runtime and
   browser/effect/collector evidence, and require green CI before publication.
3. Preserve permission, root budgets, live controls and all private state on
   upgrade/restart/renewal; independent security review remains required for
   consequential changes. No privileged same-user host isolation is provided.
4. Vendor delivery, bank endpoints, SSO/RBAC, signed external feed refresh,
   generalized DLP, ANE, production scale/retention and full physical resource
   accounting remain separate engineering/acceptance work.
5. User fills team/submission fields and confirms organizer ambiguities. PDF
   deck assets are reviewable; no HackTribe submission or eligibility decision
   follows from test success.

Cezar is optional development tooling. Task counts, skills installed, login
status and harness health are not evidence of AgentGate enforcement. Cezar's
runtime state and local tooling inventory do not ship with the product.
