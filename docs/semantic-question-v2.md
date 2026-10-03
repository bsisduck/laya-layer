# Explicit two-choice semantic profile

`content-role-v2` uses the exact `neutral2` question from a separate eight-case
development probe (7/8; English quoted warning false positive). The question key,
wording, A/B descriptions and `{operation: documents.read, prompt: content}` state
are preserved in `evaluation/protocol-v2.json`. Those development results selected
the candidate; they are not held-out quality. `evaluation/development-v2.json`
records the synthetic selection examples, observations and original probe hashes.

The engine maps actual A/B probabilities to `task_data` / `behavior_instruction`.
There is no third probability, confidence threshold or calibrated uncertainty.
`task_data` covers ordinary information, allowed tasks and discussed examples;
`behavior_instruction` here means active attempts to override rules, steal data
or redirect execution. That is narrower than the original v1 general content-role
question. Neither label authorizes anything. Auth, tenant ACL, DLP, feeds, approvals,
budgets, durable audit and output withholding remain mandatory controls.

## Selection and compatibility

Both production CLI defaults remain `content-role-v1`. Opt in explicitly on both
sides using the same installed code:

```sh
agentgate --state-dir STATE semantic-worker --backend laya_standard \
  --runtime-python ASSETS/.runtime/laya-standard/bin/python --root ASSETS \
  --question-set content-role-v2
agentgate --state-dir STATE serve --semantic-url http://127.0.0.1:8091 \
  --semantic-backend laya_standard --semantic-question-set content-role-v2
```

The installer can pass those flags explicitly after evaluating suitability. A
client sends its selected `question_set_id` on every request, checks readiness
against it, and validates returned identity/backend/revision/version and exact
score keys. The worker binds its child handshake and every result to its configured
version. A mismatched request is rejected before quota admission/native dispatch;
an invalid response kills the child and keeps the admitted charge. Unknown
versions fail closed. Legacy omitted request/capability versions still mean v1;
v2 peers must explicitly declare v2. Existing audit rows remain readable.

Capacity (1024), content limit (32 KiB), concurrency (one), native job deadline
(five seconds), auth and persistent call ledger are unchanged. V2 cannot abstain
via an invented label; unavailable/invalid/incomplete results still withhold
required inspection. There is no automatic fallback or deadline extension.

## Frozen new evaluation

The v2 corpus contains 28 new synthetic cases in 14 matched EN/PL pairs: ordinary
data, allowed tasks, quotations, negations, direct overrides, malicious paraphrases,
long benign/malicious content and deliberate overflow. Its labels and expected
coverage are frozen before any inference. It shares no exact examples with v1 or
the development eight. Authored holdout is not independent red-team evidence or
population accuracy. First-pass quality and three warm passes stay separate.

Use the shared harness with explicit `--version v2` on both `run` and `compare`.
It verifies committed inputs, protocol, engine and evaluator before loading the
existing pinned assets. Sequential standard then native CoreML uses the existing
shared evaluation lock and process inventory plus operator coordination.

Real results and activation recommendation: pending measurement. Do not treat
protocol tests or setup validation as real inference or AgentGate enforcement.
