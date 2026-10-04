# Measured department usage and standards evidence

## Outcome and dependencies

Deliver the user's management/security/regulator views on the accepted delegated
authority core (issue 40). This is a consumer of trusted attribution, not a new
identity or authorization implementation. Preserve the current visual style,
local-console mode, taxonomy, catalog and immutable historical evidence.

Current model_accounts repeats each charge in tenant_day, principal_day and
root_run accounts. Summing these is wrong. Current model_attempts retains bounds
and tariffs but not actual per-attempt settled usage. Do not derive department
costs from those aggregates or from latest subject records.

## Transactional usage evidence

Add versioned, additive per-attempt attribution and settlement evidence keyed by
unique action_id. Capture trusted subject/department/provenance at the successful
model reservation transaction, using the accepted authority resolver. Legacy calls
are explicitly unassigned. Preserve the parent accounting principal and existing
budgets. Never accept request department fields or rewrite historic attribution
when a subject changes department or is revoked.

Persist actual input/output tokens and simulated micro-USD, when known, in the
SAME transaction as ModelLedger.finish accounts and terminal audit. Unknown usage
remains unknown with retained reservations. Over-bound actual usage remains actual
and visibly frozen, not capped to a prettier number. Rollback on any evidence,
ledger or audit failure must leave all related writes consistent. Repeated finish
cannot duplicate charges; prior settled rows without evidence stay unknown.

Provide one bounded authenticated admin projection with an explicit time window,
source/version and completeness status. Count each attempt once, not once per
budget scope. Include dispatched/uncertain/settled counts, known actual input/output
tokens, known simulated spend, outstanding reservations and historical unavailable
evidence. Do not label a zero tariff as free enterprise AI or turn unknowns into
zero. Keep operation costs and model token usage distinct. No public API or export-v1
shape change; remote department export remains a documented gap unless a separately
versioned, tested consumer is actually delivered.

Bound the selected time range and number of departments, use an indexed query,
validate inputs and expose truncation if it can occur. Unknown/unassigned is a real
bucket, not discarded. Tenant selection remains operator-only and exact. Prefer a
small explicit reporting period to a new generic analytics subsystem.

## User interface and standards

Add measured department usage to existing operations UI with loading/error/empty
states, keyboard access and narrow-screen readability. Label local-demo subject
provenance and simulated tariffs. Keep real collector acknowledgments, backlog and
errors visible; no universal SIEM-delivery, bank integration or invoice claims.

Add a compact standards evidence view or section: framework/article, relevant
implemented control, executable or documented evidence, and remaining obligation.
Use RODO/GDPR Articles 9 and 22, AI Act Annex III point 4 / Articles 12, 14 and 26,
DORA ICT risk/incident/testing/third-party context, and versioned OWASP LLM 2025 /
Agentic 2026 associations. No certification/compliance badge or legal risk score.
Every claim should link to actual local evidence/docs and official sources:

- https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng
- https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng
- https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- https://www.esma.europa.eu/publications-and-data/interactive-single-rulebook/dora
- https://genai.owasp.org/llm-top-10/
- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/

Reverify official legal sources when finalizing. HR use alone does not establish
high-risk classification; purpose and applicable exceptions matter. A review click
does not establish Article 22 compliance or meaningful human involvement. Data
labels are not a legal basis for special-category processing. Avoid an unnecessary
date claim; if included use the current consolidated text, not recalled deadlines.

## Required proof and compatibility

Unit tests: correct distinct-attempt aggregation, tariff units, period boundaries,
unassigned/historic/unknown handling, immutable department attribution and bounds.
Functional/integration tests: actual reservation and finish, two departments sharing
the same parent accounting owner, no three-scope multiplication, denied calls with
no attempt/charge, uncertain outcome, overrun freeze, duplicate settlement, restart,
migration, injected transactional failure and subject department change. Fixture
providers are labelled fixtures; never count them as real inference evaluation.

Installed E2E: render data from real persisted QA attempts (a separately labelled
fixture provider is allowed for deterministic token counts), assert UI totals
against the DB, check empty/error/loading/mobile states and authenticated access.
Existing local no-login and normal credential modes must both retain boundaries.
Run make validate, applicable JS and owned installed QA. Document new schema version,
backup/restart/rollback and exact export-v1 compatibility. Publish one draft PR;
independent review and green CI are required before root integrates it.
## Independent design review resolutions (authoritative)

Review 2b515b65 clarifies accounting assertions and reporting semantics:

- Zero-attempt/zero-charge assertions apply to denials BEFORE model reservation/
  dispatch. Count every reserved attempt regardless of the returned decision.
  Provider output withheld by output controls still contributes validated actual
  settled usage. An ambiguous timeout retains reservations and unknown usage.
  Never aggregate only allowed responses or silently erase blocked-output costs.
- Select attempts by reservation time in UTC `[start, end)` and read attribution,
  attempts and settlements in one consistent database snapshot. A `dispatched`
  database state means durable dispatch intent, not independently confirmed provider
  receipt; use that precise label in reporting.
- Attribution availability and usage availability are separate. An unassigned
  attempt may have known actual usage; an attributed attempt may have unknown usage.
  Publish known totals with contributing-attempt counts, unknown counts and explicit
  truncation/completeness status. Do not mislabel a partial sum as an exact total.
- Add output-denied-after-provider-success, timeout, overrun and settlement-rollback
  tests. Semantic classifier consumption remains its separate installation ledger;
  this report cannot claim to allocate its GPU/model cost per department.
