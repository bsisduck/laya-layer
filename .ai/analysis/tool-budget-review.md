# Tool budget review

## Verdict

Approve for prototype source publication. This is author self-review, not the
independent security review required before production release.

## Summary

Document execution reserves tenant/day, principal/day, and root-run call capacity
under the credential recheck and audit transaction. A limit denial rolls back all
scopes before the executor. Known returns settle with the outcome; executor and
audit failures cannot silently release reservations. Review covered the spec,
`budgets.py`, store, service, policy, CLI, tests, and affected documents.

## Findings

No unresolved Blocker or Major findings in this bounded slice. The first gate
caught the shipped policy test still expecting revision 1; it now asserts revision
2 and its root limit. No assertion was weakened. Provider accounting, native
inference admission, automated reconciliation, and non-idempotent tool retries
are outside this slice and remain explicit product gaps.

## Validation Gate

| Command | Status | Evidence |
|---|---|---|
| `make validate` | PASS | Workflow checks, lock, Ruff, strict mypy, 84 pytest cases, sdist/wheel |

## Contracts and test evidence

Schema 2 is additive with explicit migration; migration failure rolls back and
backup restoration exercises the old credential/audit contract. HTTP denial
reason and policy block are additive. Existing policies remain unbudgeted when
the block is absent; the demo explicitly opts in. Tests exercise each limit with
16 concurrent requests, tenant isolation, delegated agents, new roots/principals,
UTC rollover, restart, lower limits, denied paths, blocked output, exceptions,
both audit boundaries, duplicate settlement, and strict integer validation.
