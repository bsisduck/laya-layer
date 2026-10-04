# Measured department usage (model-attempt-evidence-v1)

The authenticated operations overview reports model attempts from persisted
reservation/settlement evidence. This is implemented accounting for the governed
model path, not a classifier evaluation, cloud invoice, department export or
enterprise compliance verdict. Deterministic provider tests use labelled fixtures.
Tool operation charges and semantic-worker installation consumption remain separate.

`GET /admin/department-usage?tenant_id=tenant-a&start=1000&end=2000`
requires the existing operator session, exact tenant identifier and integer UTC
Unix seconds. It rejects duplicate/unknown parameters, invalid tenants, reversed
periods and periods longer than 31 days. Optional `departments` is 1..64 (default
64). Same-origin/host/session boundaries apply in credential and trusted-loopback
local-console modes. Agent credentials cannot read the report.

Selection uses reservation time `[start,end)`, not completion time. An indexed
`(tenant_id,created_at,action_id)` query joins attempt, attribution and settlement
in one SQLite read snapshot. At most 10,000 attempts are selected, ordered by
reservation time/action ID. At most 64 department buckets and 16 distinct minimized
provenance variants per bucket are returned. Truncation is explicit. Totals cover
selected attempts; returned department rows can cover fewer. Unknown/unassigned is
a real bucket, kept first if department rows are truncated. Choose a smaller period
to obtain a complete selected window; this is a bounded report, not generic analytics.

Each action ID contributes once, regardless of its three budget scopes or response
decision. `dispatch_intent` means durable dispatch intent, not confirmed provider
receipt. `settled`, `uncertain`, actual-known/unknown and attribution-known/
explicitly-unassigned/historically-unavailable counts have separate denominators.
Known input/output tokens and simulated micro-USD are sums only over
`known_usage_attempts`; when usage is unknown they are partial sums, not exact
overall consumption. Historical settled rows lacking evidence remain unknown,
with no reservation invented. An unassigned attempt may have known actual usage.
Zero simulated tariff does not mean free enterprise AI or zero resource use.

`model_attribution` captures a minimized authority snapshot after the successful
transactional authority recheck, together with the immutable accounting principal.
Legacy credentials record explicit unassigned attribution. The evidence consumer
accepts positive bounded authority versions, bounded provenance and optional
`issuer_id`/`trust_version`, without assuming every source is `local_demo`. It retains
subject ID/revision/department, drops bindings, roles and raw issuer claims, and
does not implement issuance or permissions. The department report exposes grouped
provenance without subject IDs. Later subject changes or revocation cannot rewrite
historical attribution.

`model_settlement` stores validated actual input/output tokens, exact simulated
micro-USD and over-bound status keyed uniquely by action ID. Settlement, all account
updates, attempt state and terminal audit share one write transaction. Evidence,
account or audit failure rolls them all back; output stays withheld and reservations
remain. Output denied after provider success still settles known work. Ambiguous
timeouts remain unknown and retain reservations/admission. Repeated finish cannot
charge twice. Actual overruns are recorded without capping and freeze affected scopes.

Money is an integer count of **micro-USD per token** from the attempt's captured
simulated tariff revision. Settlement money uses digit-only decimal `TEXT`, not
INTEGER-affinity numeric strings. Reports aggregate with Python integers and
return all monetary totals as decimal strings; the browser never converts them to
`Number`. Bounded token/count totals remain safe JSON integers. Ordinary ledger
storage remains integer. Above int64, exceptional frozen account spend is stored
as nonnumeric `exact:<decimal>` text to prevent SQLite REAL promotion; a later
pending settlement adds exactly in Python and preserves freeze. Model counter
projections use decimal strings above JavaScript's safe integer as well. Admission
rejects reservations exceeding policy capacity before SQL binding. These changes
do not grant extra budget capacity.

Schema: existing SQLite `user_version=2` and authority-v1 remain; additive
`model_usage_schema=1` owns attribution/settlement sidecars and the period index.
Stop serving before upgrade, preserve a SQLite-consistent backup (including WAL
state via the existing backup procedure), run `agentgate migrate`, then restart
the new binary. Migration never backfills history from current subjects or counters.
Missing usage schema fails readiness. Preserve evidence and ledgers on restart.
Old binaries must not serve this database: they omit evidence writes and cannot
safely add to tagged overflow spend. Rollback requires stopped services and a
pre-upgrade backup with the old binary; this loses post-backup activity. Do not
delete sidecars to pretend a live rollback is safe or run mixed binaries.

Legacy REST/MCP response shapes, Identity, authority-v1 bytes, approvals and
export-v1 allowlist are unchanged. Remote department export is an explicit gap.
The only additive HTTP projection is the operator report. No JWT, HR or deck is
implemented here. Root independently reviews high-risk accounting and installed QA
before integration; author checks are not independent approval.

Executable proof: `tests/test_department_usage.py`, `tests/test_models.py`,
`tests/test_authority.py`, `node --test tests/frontend/contracts.mjs` and owned
installed `tests/frontend/department_usage_check.py` (fixture provider; no inference).
See [standards evidence](standards-evidence.md) for the official-source mapping.
