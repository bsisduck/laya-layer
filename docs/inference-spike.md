# Laya loading spike

The gateway does not yet call a semantic worker. This separate spike establishes
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

Observed loading results are recorded after the two runs complete.
