# Frozen real semantic evaluation

E04-S01 evaluates the shipped `content-role-v1` document question by importing
`inference_engine.evaluate` in the actual isolated runtime. It does not exercise
HTTP authentication or prove gateway enforcement. Deterministic tests of report
math and invalid subprocess output are separate from these real model runs.

## Reproduce

Run `make setup`. Reuse the isolated runtimes and verified snapshots prepared by
[inference-spike.md](inference-spike.md); this evaluator never downloads assets.
`ASSETS_ROOT` below is the checkout containing `models/` and `.runtime/`, which
may differ from the evaluation worktree. Use a new output filename on every run.

```sh
ASSETS_ROOT=/absolute/path/to/checkout-with-existing-assets
uv run python scripts/semantic_evaluate.py run --backend laya_standard \
  --runtime-python "$ASSETS_ROOT/.runtime/laya-standard/bin/python" \
  --assets-root "$ASSETS_ROOT" --output reports/generated/standard-eval-v1.json
# Wait for standard to exit before starting native Apple CoreML.
uv run python scripts/semantic_evaluate.py run --backend laya_coreml \
  --runtime-python "$ASSETS_ROOT/.runtime/laya-coreml/bin/python" \
  --assets-root "$ASSETS_ROOT" --output reports/generated/coreml-eval-v1.json
uv run python scripts/semantic_evaluate.py compare \
  reports/generated/standard-eval-v1.json reports/generated/coreml-eval-v1.json \
  --output reports/generated/comparison-eval-v1.json
```

Evaluation inputs and the runner must be committed. The runner checks the frozen
SHA-256 manifest and working files against Git before loading. An exclusive lock
under the shared assets root serializes these evaluations; its child inherits the
lock descriptor. A process inventory also refuses observed active Laya workers.
This advisory inventory is not a host-wide scheduler: operators must coordinate
other model workloads. No unrelated PID is terminated. Native CoreML requires
Apple Silicon macOS and requests CPU/GPU; device placement/ANE is unmeasured.

The child verifies every checkpoint asset and installed requirement version,
hashes the installed Laya source/native files, and records tokenizer normalization
on the disposable standard snapshot. Runtime package versions, source hashes,
checkpoint file hashes, engine/question/fixture/requirement hashes, Git revision,
platform, CPU and RAM accompany each report. Original snapshots remain unchanged.

## Frozen protocol and denominators

Freeze commit `b4922c4` precedes held-out inference: 26 deliberately public synthetic
cases, 13 matched EN/PL pairs, separate from the four development/loading cases.
The classes cover ordinary data, benign security quotation, negated instructions,
explicit malicious overrides, malicious paraphrases, longer data/overrides and
intentional over-capacity text. The v1 question and argmax rule remain unchanged;
no tuning was conducted on this corpus. Future tuning needs a new held-out set.
`behavior_instruction` describes content role, not necessarily malicious intent.

Only the first pass contributes to quality. Three further complete corpus passes
measure warm performance and report repeat disagreement; they are not additional
independent examples. First-call latency and process startup are distinct single
cold observations; OS file caches are not purged. Warm percentiles use nearest
rank, with sample counts and actual tokenizer-derived length buckets.

- Conditional accuracy = correct / decisive (`ok`) cases.
- All-case accuracy = correct / all 26 cases, including abstentions and failures.
- FPR = false positive / all labeled task-data cases; FNR = false negative / all
  labeled instruction cases. Neither folds nondecisive cases into FP/FN.
- Conditional FPR/FNR, precision, recall over all positives, positive/negative
  nondecisive counts, and strict benign withholding rate expose the other
  denominators. Undefined rates are JSON null, never zero.
- Coverage includes full-window `unclear` answers; abstention is not missing
  coverage. Incomplete, invalid and unavailable counts remain separate.
- Overall, language, class, and language/class quality slices retain counts.
  Backend comparisons include status/label and decisive-only disagreement, with
  language/class slices. Agreement on failure is not correct classification.

Reports contain case IDs, actual selected labels/scores, coverage/token diagnostics,
phase timings and resources, not source text or credentials. Fixed synthetic
prompts are deliberately committed only in the corpus. Generated reports are
ignored and never silently overwritten. Missing hardware/runtime/assets, startup
failure, invalid output or timeout produce unavailable/failed reports and exit 1.
Low accuracy or expected over-capacity is a measured outcome, not an execution
failure or a clean scan. Later cases after a child failure remain in denominators
as unattempted/unavailable; they are excluded from latency distributions.

## Measurement limits and root integration

One 1,024-token window, 32 KiB content, concurrency one, 45-second startup and
five-second call deadlines bound this harness. It kills/reaps only its own child.
Engine preflight timing and runtime `predict` timing are measured separately;
`predict` includes the library's own tokenization/postprocessing, not solely device
compute. Parent wall time includes serialization/IPC/validation. Child high-water
RSS and cumulative user/system CPU exclude external CoreML services and are not
a whole-system memory/energy measurement. There is no imposed RAM cap.

Persistent semantic-call/token/time accounting (architecture **T28**) remains
missing in the base document path. This harness's sequential admission/deadlines
are not that ledger; root integration must implement and test it separately.
Default semantic inspection stays optional; required failures still fail closed.
No endpoint, policy gate, credential, question version or production threshold is
changed. Any later runtime/question-contract update needs separate root integration
and fresh evaluation. This small authored corpus is not population accuracy,
independent red-team evidence, universal protection, or certification.
