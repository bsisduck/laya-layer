# Local semantic inference admission

The production `agentgate semantic-worker` command always opens a private
`semantic-quota.sqlite3` in its state directory. `--daily-calls` defaults to 1000
and accepts 1–1000000. Standard and CoreML workers sharing that installation use
one counter per UTC day. This is a local resource cap, not tenant billing.

Authentication, request validation, worker readiness and the no-queue concurrency
check happen before quota admission. An atomic SQLite transaction commits one
call debit before bytes reach the native process. Exhaustion returns HTTP429 with
zero further native dispatch; missing or unwritable accounting returns HTTP503.
Timeouts, process crashes and uncertain outcomes never refund admission. Restart
retains spend. Changing backend or raising configuration cannot raise an already
established daily ceiling; the next UTC day uses the new setting. A lower setting
is applied on the next admission attempt. Existing per-call input/deadline and
native concurrency bounds remain in force.

The independent database avoids holding the gateway's transaction open while
trying to write quota records to that same database. It contains UTC dates,
counts and ceilings only. Preserve it with installation state; deleting state
would discard its authority and is not a supported way to restart or renew.

`GET /internal/v1/semantic/budget` requires the private worker credential and
returns measured calls/limit/remaining. The operator overview includes this under
`budgets.semantic`; the browser never receives the worker credential. If the
worker cannot report it, status is unavailable, not zero. Gateway semantic quota
denials use `SEMANTIC_BUDGET_EXCEEDED`/HTTP429. A document may already have been
read before output inspection exhausts the semantic quota; its output is withheld
and the audit retains actual execution evidence. A model input denial prevents
model dispatch; a model output denial retains incurred model accounting.

The low-level `Supervisor` constructor has an optional quota for isolated engine
fixtures and explicit offline evaluation. That internal testing seam is not a
production CLI bypass. Evaluation reports must identify their own resource
protocol instead of claiming runtime quota enforcement.

Validation in `tests/test_semantic_quota.py` uses observable Python child
processes, real SQLite and independent racing processes. It proves admission and
zero-extra-dispatch behavior, not Laya classification quality. Real-model quality
is measured separately by the semantic evaluation story.
