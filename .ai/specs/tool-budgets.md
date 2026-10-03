# Atomic document dispatch budgets

Source: full architecture §11; follows the implemented document boundary.

Add optional `tool_budgets` policy configuration with nonnegative integer limits
for tenant/day, principal/day, and root run. Existing policies without the block
keep their behavior; the demo explicitly enables limits in revision 2.

Reserve one tool attempt in all three scopes in the same SQLite write transaction
as the final credential check and dispatch-intent event. Use UTC day sampled
after lock acquisition. Tenant is part of every scope; root scope also includes
the principal. Agents sharing a server-owned root share its allowance. A denied
action reserves nothing, and exhaustion returns 429/BUDGET_EXCEEDED before reads.

On a known executor return, atomically settle one call with the outcome audit,
including blocked/invalid output. Executor exceptions keep an uncertain
reservation. An outcome audit failure retains its prior reservation and withholds
output. Restart, TTL, policy revision, retry, and credential replacement must not
reset usage. No automatic reconciliation or refunds in this slice.

SQLite schema 2 adds counters and reservations; provide explicit migration from
schema 1 and documented backup/restore rollback. Existing HTTP shapes and policy
defaults remain compatible. Add a bounded local operator budget-list command.

Acceptance: all three scope limits independently; shared agents and new roots;
tenant isolation; concurrent boundary; UTC rollover; expiry/revocation race;
denied paths; blocked output; uncertain failure; audit failure; restart; duplicate
settlement; lowered limits; v1 migration preserves credential and audit records.
This is call-count governance, not money, tokens, inference time, concurrency,
provider retries, or client idempotency for non-idempotent tools.
