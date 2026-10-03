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
- [x] 2.3 Complete validation and independent review, then ready the PR.

Evidence: implementation `029bdaf` passes the complete gate (304 tests). Independent Cezar re-review approved that exact head after 15 additional integration probes, including decoded secrets, absolute deadlines, control races, credential revocation and admin model isolation: https://github.com/bsisduck/laya-sec-agent/pull/6#pullrequestreview-5402362145 . Real HTTP gateway/private LiteLLM/Ollama/document/result-summary cycle passed again on this head (2919.4 / 1991.8 / 2165.5 ms fixed-fixture generation/tool/summary observations). Live policy/feed CAS and admin model integration are included. Remaining product stories retain their own release gates; this model PR does not imply complete product delivery.
