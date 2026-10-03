# AgentGate review rules

Current runtime scope: document-only REST enforcement, hashed scoped credentials,
SQLite audit, and local fixture execution. The architecture's other surfaces
remain proposals. Review the implemented boundary without implying broader coverage.

- Confirm the change matches the architecture and the task's acceptance criteria.
- Keep deterministic authorization separate from model confidence. A semantic
  result cannot grant tool, tenant, model, or budget permissions.
- Check both model and tool paths, canonical tool identifiers, authentication,
  tenant scoping, destination validation, and the private upstream boundary.
- Require denied-path assertions on executor/provider calls, outbox rows, and
  ledger effects, not just status codes or dashboard messages.
- Check atomic budget reservations, retries, idempotency, uncertain timeouts,
  policy reload races, and exact-action approval binding.
- Require bounded input/output, deadlines, safe parsing, output inspection, and
  fail-closed behavior when mandatory policy, semantic, budget, or audit checks fail.
- Keep credentials and raw sensitive content out of logs, browsers, artifacts,
  and version control. Exercise redaction on both input and output.
- Preserve native macOS CoreML execution and report its real checkpoint/runtime.
  Fixtures must never appear as real-model evaluation evidence.
- Review dependency versions, provenance, licenses, and reproducible installation.
- Run `make validate` and all checks appropriate to the change. Application code
  requires a real application gate; setup-only success is insufficient.

Security bypass, data leakage, incorrect budget/approval behavior, and failed
required checks are blockers. Fix major correctness and contract issues before
handoff. Document minor issues without widening a focused change unnecessarily.
