# Authenticated document-result semantic workers

Source: architecture §§10, 11.5, 14. Implement one explicit stage: document-result
inspection after deterministic authorization/DLP and before output release.
The `content-role-v1` question classifies task data, behavior instruction, or
unclear. It is not a calibrated maliciousness score or task/action mismatch check.

Use the pinned real standard and CoreML loaders in their separate environments.
A loopback HTTP supervisor authenticates a dedicated service token and supervises
one model subprocess. Admit at most one evaluation; reject busy calls, do not
queue unbounded work. Bound body/response sizes, token capacity, startup and job
time. Kill and reap the subprocess on timeout/protocol failure; fail readiness
until restarted. No automatic retry or fallback.

Preflight the same tokenization and question rendering used by each pinned
runtime. Reject truncation, option collapse, or marker removal before inference;
validate actual output diagnostics too. Preserve source model hashes, copy the
standard tokenizer snapshot before its upstream normalization, disable downloads.

Validate request ID, backend, revision, question-set version, labels, finite
probabilities, coverage, usage, and measured wall time in the supervisor and
gateway adapter. Persist only normalized evidence; never raw content or token.
Strict mode withholds instruction, abstention, incomplete, invalid, or unavailable
results. Low risk never overrides deterministic rules. Explicit observe mode
records complete labels without blocking on them; operational failures still deny.

Tests: authenticated HTTP boundary, malformed/oversized input and output, unknown
labels/revisions, false complete claims, actual killed subprocess on deadline,
bounded concurrency, no evaluation on deterministic/budget denial, output release
and audit linkage. Separately run both real backends through HTTP and gateway;
record actual labels without changing expected fixtures to fit predictions.

Call-count tool budgets bound document invocations. Persistent inference-token,
time, and per-principal analysis budgets are a subsequent slice; report this gap.
