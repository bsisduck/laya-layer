# First implementation slice

Source of truth: `AgentGate_Full_Project_Architecture.md`, especially §§7, 10,
19–23. This records the initial task and follow-up sequence.

Progress: locked Python environment, document contracts and enforcement, audit,
and denied-path tests are implemented. Both real Laya loaders work on pinned
assets; both now have authenticated worker services connected to document-result decisions.
See `docs/document-slice.md` and `docs/inference-spike.md` for observed evidence.
Organizer timing remains unverified; implementation proceeded on the user's
explicit instruction to proceed, not a claimed organizer confirmation.

1. Resolve the organizer's start-time ambiguity recorded in §2 before competition
   implementation. Confirm judging-weight and cross-category questions separately.
2. Create Python 3.12 packaging and a locked environment. Spike FastAPI, Pydantic,
   official MCP SDK, and HTTP testing compatibility; keep model-runtime dependencies
   in worker environments. Add genuine lint, typing, testing, and build gates.
3. Define request identity, action/decision, audit, and semantic-worker contracts.
   Use dependency injection for the worker, clock, ledger, and upstream calls.
4. Implement the smallest real path: authenticated REST action → deterministic
   policy → registered `documents.read` fixture executor → persisted redacted audit.
5. Prove allowed read and denied execution. Missing credentials, wrong tenant,
   unknown tool, and malformed arguments must produce zero executor side effects.
6. In the initial spike, verify actual standard Laya and native CoreML loading,
   pin model revisions/digests/licenses, and record failures honestly. Do not
   substitute Ollama generation or a stub for either classifier.
7. Extend to model facade/private LiteLLM, MCP, and Hermes only after the shared
   action path works. Keep application integrations separate from Cezar tooling.

Atomic document call budgets are implemented in `tool-budgets.md`.
Workers are implemented in `semantic-workers.md` with real integration evidence.
Next slices: model facade; inference/provider budgets and policy reload; semantic checks and output
filtering; exact-action approvals and outbox; feeds and failure/concurrency tests;
Hermes end-to-end demo; dashboard and offline evidence. Map tests to §20's T01–T48.
Do not create empty adapter directories or count planned tests as passed.
