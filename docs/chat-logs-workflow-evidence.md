# Chat / Logs / Workflow evidence

The three-page console retains actual REST/MCP/model/approval contracts and
no-login local-session recovery. Empty/unknown hashes now open Chat; old hashes
and overview section/trace queries retain their views and active parent.
Context navigation groups HR/approvals/outbox/playground under Chat,
timeline/operations/usage/export under Logs and catalog/policy/feed/standards/
controls under Workflow. Native links and discard confirmation remain.

Four authored histories have explicit outcome, authority, request/response,
reason/layers, operation/data, policy, effects and next step. They make no API
requests and do not enter audit records, counts or actual approval lists. The
Live HR workspace retains actual enforcement. No canned text is inference.

Workflow is a conceptual five-step request path plus two cross-cutting rails,
not an assertion of one literal runtime sequence. Layer details cite inspected
source and partial coverage. No Redis, full OIDC SSO, PESEL/IBAN/cards detector,
Llama Guard/Granite, generic loop/circuit, active-element/canary removal, 17-feed
inventory or MCP descriptor pinning is claimed. Unknown operations remain denied.
Hard denials cannot be overridden by approval; exact server approval and
revalidation precede explicit dispatch. Read classification never grants scope.

## GDPR associations

Articles 9 and 22 retain scoped access/filtering and exact-action review/audit
associations, with gaps in sensitive-category detection and legally significant
automated-decision safeguards. These associations are not certification.

Article 20 is an individual portability right for provided personal data where
processing is automated and based on consent/contract. It calls for a structured,
commonly used, machine-readable format, protecting the rights of others. Existing
audit JSONL is a minimized technical export, **not subject portability**; subject
request eligibility, extraction and delivery are not implemented.

Article 30 is an organizational record of processing activities (RoPA), covering
purposes, data/subject categories, recipients, transfers, retention, safeguards
and responsible parties. Technical logs support investigation; **they are not a
complete RoPA**. This change builds neither register nor case-management backend.

Sources: [official GDPR text](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng/),
[EDPB portability guidance](https://www.edpb.europa.eu/documents/guideline/right-to-data-portability_en),
[EDPB individual rights guide](https://www.edpb.europa.eu/sme/be-compliant/respect-individuals-rights_en),
[Commission individual requests](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/dealing-requests-individuals_en).
Articles 20/30 replace the originally ambiguous DP20/DP30 placeholders following
the user's clarification. No policy defaults were activated.

## Validation

Runtime is frozen at `a7f173c62689d2c13e666c7d44ad9657a64d9ec4`.
The subsequent `3146ee6` and `84fa9bd` commits add browser regression coverage
only; the latter verifies actual legacy page titles, including `#approvals`.
QA used the installed, non-editable wheel through the repository's isolated
environment helper. Owned services were stopped; shared services were untouched.

| Gate | Measured result / scope |
|---|---|
| `make setup` | PASS; locked gateway/MCP dependencies and configured tooling |
| `make validate` at `3146ee693d860aac9f92d51fa43f41c5588af6f9` | PASS; workflow/Cezar checks, lock consistency, Ruff/format (125 files), strict mypy (58 files), **1,005 pytest tests / 0 skips in 131.44s**, source/wheel build |
| `node --test tests/frontend/contracts.mjs` | **26 passed**; route grouping, example metadata, deny-first branches and distinct GDPR purposes/gaps, plus retained security contracts |
| Installed `three_pages.py` at `84fa9bd35102cdfdb7ce5c5f2c89c20c994495bf` | **9 groups passed**; zero-call examples and unchanged audit/approval/outbox counts, real correlated denial/no effects, seven layers/three branches, all four widths, actual deep-route titles/parents, keyboard/back/forward, modified/same-hash clicks, dirty query recovery, log loading/empty/error/stale responses, actual local expiry/no mutation replay; observed startup 149ms |
| `workspace_components.py` | **5 groups passed**; mocked operations/navigation/inbox presentation, global approval counts, exact payload/XSS and stale-response assertions retained |
| `browser_components.py`, `hr_components.py` | PASS; explicit mocked presentation/error/validation fixtures, not backend or inference evidence |
| Installed `local_console_check.py`, `browser_check.py` | PASS; real REST/MCP/denial, exact approval/local outbox, control CAS/feed/export, session/auth/recovery and keyboard/mobile consumers; no inference |
| Installed `department_usage_check.py --local-console` | PASS; 7 persisted fixture attempts, 5 known / 2 unknown, exact simulated micro-USD totals, freeze/rollback/denied effects and presentation states; no invoicing or real-model claim |
| Installed `threat_ladder.py` | **9 scenarios passed**; durable fixture denial/no effect, protected endpoint, overlapping/unknown filters, safe text, mobile/loading/error; no inference |
| Installed `hr_flow.py` at runtime `a7f173c` | PASS; actual HR/exact approval/local outbox: **1 outbox row**; labelled provider fixture: **2 calls**, failed output withheld, usage attribution checked; active controls restored at a newer revision |

The default HR injection probe returned **allow with semantic inspection off**.
The authored blocked-injection history is conditional on the relevant active
feed/required inspection; it is not a result of that probe. Fixture-provider
calls are not real-model inference. These gates do not establish semantic
accuracy, SMTP delivery, portability/RoPA implementation or legal compliance.

Screenshots `chat`, `logs` and `workflow` at 360/390/768/1440px were inspected.
The destructive/undeclared refusal is a separate red branch; permitted reads
and reviewable writes have distinct lanes. All three primary links remain visible.
New static route/example/workflow modules total 17,563 source bytes, with no new
runtime dependency; the startup observation is local QA, not a comparative benchmark.

Local artifacts (ignored, not packaged or committed):
`.ai/qa/artifacts_three_pages/` contains `final-make-validate.log`,
`final-contracts.log`, `deep-route-three-pages.log`, `result.json`, the serial
`final-*.log` browser/HR reports and `<page>-<width>.png` screenshots.

## Author review

Verdict: **approve (author self-check)**; no unresolved blocker/major finding.
Independent review is performed by root. Checked the frontend/test diff against
the architecture, SDLC, CODE_REVIEW and BACKWARD_COMPATIBILITY rules. Public APIs,
policy formats, schema, model environments and backend enforcement are unchanged;
legacy hashes retain actual pages. The default Chat and contextual grouping are
the intentional compatibility change documented in BACKWARD_COMPATIBILITY.

Resolved findings: same-hash activation needed workspace focus/discard handling;
modified Ctrl/Meta clicks needed native default behavior without a re-render;
the legacy-route test used a SQLite table name and could pass via fallback.
Each now has an installed regression. Initial test-only table-name mistakes were
corrected against the real schema before rerunning the gates. No timeout/retry
expansion, guard bypass or weakened side-effect assertion was used.
