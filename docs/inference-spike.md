# Laya loading spike

At the time of this loading spike, the gateway did not call a semantic worker.
This historical spike establishes
whether actual inference can load on the development Mac, with model files kept
outside version control. It is not a security-accuracy benchmark or an implemented
worker service.

Two isolated Python 3.12 environments are pinned by
`requirements/laya-standard.txt` and `requirements/laya-coreml.txt`. The standard
runtime is Laya 0.3.24; the Apple runtime is Laya-CoreML 0.2.0. Asset repository
revisions, sizes, SHA-256 digests, and declared model-card licenses are in
`manifests/model-assets.json`. Every listed asset is verified before inference.

```sh
uv venv --python 3.12 .runtime/laya-standard
uv pip sync --python .runtime/laya-standard/bin/python requirements/laya-standard.txt
uv venv --python 3.12 .runtime/laya-coreml
uv pip sync --python .runtime/laya-coreml/bin/python requirements/laya-coreml.txt
.runtime/laya-standard/bin/python scripts/semantic_smoke.py laya_standard --download
.runtime/laya-coreml/bin/python scripts/semantic_smoke.py laya_coreml --download
.runtime/laya-standard/bin/python scripts/semantic_smoke.py laya_standard
.runtime/laya-coreml/bin/python scripts/semantic_smoke.py laya_coreml
```

Downloads use explicit revisions and no implicit Hugging Face token. Inference
uses local assets with Hub/Transformers offline mode. The standard model uses CPU;
CoreML requests CPU/GPU, without claiming per-operation placement or ANE execution.
The same four short PL/EN cases and labels are fixed in
`tests/fixtures/semantic-loading.json`. Matching a label is recorded, not assumed.
`loaded_and_predicted` means loading and valid typed answers worked, not that every
classification was correct. Generated reports live in ignored `reports/generated/`.

## Observed results — 3 October 2026

Both runtimes loaded and returned typed predictions on native arm64 macOS, using
Python 3.12.9. The standard runtime used CPU; CoreML requested CPU/GPU. Each file
matched its recorded SHA-256 before loading. This was actual inference, with no
classifier stub and no external generation model.

| Case | Label fixed before inference | Standard Laya | Native CoreML |
|---|---|---|---|
| English report data | `task_data` | `unclear` | `unclear` |
| English instruction override | `behavior_instruction` | `behavior_instruction` | `behavior_instruction` |
| Polish report data | `task_data` | `unclear` | `unclear` |
| Polish instruction override | `behavior_instruction` | `behavior_instruction` | `behavior_instruction` |

Each backend matched 2/4 expected labels; the backends agreed on 4/4 cases. These
four deliberately small loading fixtures do not measure guardrail accuracy. Do
not relabel the benign cases to turn these results into four successes. Next:
refine the task/question contract, then evaluate on a separately frozen dataset
with benign security discussion, paraphrases, negation, long input, and PL/EN slices.

The standard library rewrites its tokenizer configuration to normalize special
tokens. The first run exposed that behavior. The smoke runner now loads a
disposable copy, records the normalized tokenizer digest, and preserves the
original verified snapshot. No model weights or generated outputs are committed.

FastAPI 0.142.2, Pydantic 2.13.5 and official MCP SDK 2.3.0 also installed together.
SDK server/schema construction succeeded using `mcp.server.mcpserver.MCPServer`;
the old `FastMCP` import is rejected by SDK v2. This is a dependency/API spike,
not transport or authentication evidence for an AgentGate MCP endpoint.

Sources: [standard Laya](https://github.com/NandhaKishorM/laya),
[CoreML usage](https://github.com/mizorewww/laya-coreml/blob/main/docs/USAGE.md),
[official MCP SDK](https://github.com/modelcontextprotocol/python-sdk).

The subsequent [frozen v1 evaluation](semantic-evaluation.md) reports 26 paired
EN/PL cases through the actual engine, including poor benign handling and a
CoreML warm-call timeout. Its labels and protocol were committed before inference.
