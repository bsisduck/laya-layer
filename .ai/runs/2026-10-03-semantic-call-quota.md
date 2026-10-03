# Durable local semantic-call quota

Source: architecture T28, full-stack delivery E04-S02 (#16).

Close the measured acceptance gap with a daily installation-wide worker quota. A separate private SQLite ledger records each admission before native work; one irreversible call debit is conservative on unknown outcomes. Existing per-call deadline and one-native-process concurrency remain authoritative. This is a local resource limit, not tenant billing. Standard/CoreML share the same installation counter.

## Progress

- [x] 1. Add atomic durable quota and production worker admission.
- [x] 2. Expose operator configuration/status and document restart/failure behavior.
- [ ] 3. Prove zero extra inference on exhaustion/races/storage errors, run the gate, obtain independent review.

Issue: #25. PR: #26. Twelve new admission tests passed, including real subprocess effects and independent-process final-capacity race. Full gate and independent review pending.
