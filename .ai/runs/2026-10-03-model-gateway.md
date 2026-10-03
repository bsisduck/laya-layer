# Private model gateway and resource ledger

Source doc: .ai/specs/full-stack-delivery.md
Scope: E01-S02. Governed Chat Completions with fixed local aliases, bounded inspected input/output, buffered SSE, server-owned identity and atomic call/token/micro-unit reservations. No client upstream override, hidden retry or paid calls.

## Decisions and risks

Local proxy integration uses an isolated pinned LiteLLM environment. The local model must demonstrate correctly shaped tool arguments. Native loopback protects credentials, not access by other trusted same-user processes. Reserve a conservative bound for input plus output; do not claim invoice guarantees. Unknown/malformed/oversized usage retains the full reservation. Root resource scope is tenant+root, so delegated principals share limits.

## Progress

PR: #6
Issue: #9

### Phase 1: Runtime and contracts
- [x] 1.1 Add strict model request/config and atomic resource ledger.
- [x] 1.2 Add authenticated model facade, inspection and buffered SSE.

### Phase 2: Verification and integration
- [x] 2.1 Prove denied paths, races, timeout retention and output withholding.
- [x] 2.2 Run real local LiteLLM generation/tool integration and document evidence.
- [ ] 2.3 Complete validation and independent review, then ready the PR.

Evidence: c83e2d0 introduced the runtime; full gate now passes 204 tests. Real HTTP gateway/private LiteLLM/Ollama/document-tool/result-summary cycle passed, documented in docs/model-gateway.md. Integration with PR17 snapshot/feed contract and independent review remain before release.
