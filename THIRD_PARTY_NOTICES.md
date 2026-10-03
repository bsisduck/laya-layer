# Third-party components

AgentGate is unreleased. Dependency packages and model weights are not vendored
into this repository. Preserve their licenses/notices when distributing them.
The project architecture and enforcement implementation do not claim upstream
inference engines, weights, routing frameworks, or development tooling as original work.

| Component | Source and declared license |
|---|---|
| Laya 0.3.24 | [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya), Apache-2.0 |
| Multilingual standard weights | [convaiinnovations/laya-multilingual](https://huggingface.co/convaiinnovations/laya-multilingual), model card Apache-2.0 |
| Laya-CoreML 0.2.0 | [mizorewww/laya-coreml](https://github.com/mizorewww/laya-coreml), Apache-2.0 |
| Multilingual CoreML export | [aac6fef/laya-multilingual-coreml](https://huggingface.co/aac6fef/laya-multilingual-coreml), Apache-2.0; bundled LICENSE/NOTICE downloaded and hashed |
| Cezar / Open Mercato skills | [Cezar](https://github.com/open-mercato/cezar), [skills](https://github.com/open-mercato/skills), MIT |

`uv.lock`, `package-lock.json`, and the isolated inference requirement files
record dependency versions. `manifests/model-assets.json` records exact model
revisions and asset SHA-256 digests, including the CoreML license/notice files.
Inspect all dependency license obligations again before a release; this list
records the primary integration components rather than a complete legal inventory.
