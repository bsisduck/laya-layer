# T45 fragmented-upstream verification

Issue: #34. Base: fresh `origin/main` `0010602ff1bf68d6ca089788f83b6162bdf22dd5`.
Test implementation validated at `fdbc416884f2e31bd48cede1cab9dce67f78c270`.
Scope: `tests/test_model_stream_boundary.py`; no product, contract or dependency changes.

Two cases use a real HTTP gateway consumer and production PrivateProvider/ModelService:
- Loopback upstream StreamingResponse with confirmed chunked transfer; emission/consumption barriers validate four actual byte partitions (allowing TCP subdivision), including splits inside the secret prefix, value and closing bracket.
- Deterministic split transport with exact observed fragments; this companion case is a transport fixture, not real upstream HTTP.
At each barrier (including before EOF), no gateway headers/body or consumer bytes are released. Exactly one upstream request uses `stream:false` for client `stream:true`.
Both end with `403 SECRET_IN_OUTPUT`, `executed:true`, no assistant content or SSE; correlated durable dispatch/output-blocked audit precedes headers. One settled attempt accounts 1 call / 23 fixture-reported tokens / 0 micro-USD in each of three scopes, with no reserved capacity or raw marker persistence.

| Validation | Result |
|---|---|
| `make setup` | PASS |
| `uv run --locked --extra mcp pytest tests/test_models.py tests/test_model_stream_boundary.py` | 60 passed |
| `make validate` | PASS: workflow/config, lock, Ruff, strict mypy, 595 passed / 10 skipped, source + wheel build |

OM code self-review verdict: approve for this scoped test diff; no blocker/major findings or contract changes. Root review remains separate. Existing skips: 9 unconfigured upstream Hermes cases and 1 missing operator-renewal module. No heavy inference or real semantic evaluation ran; optional ANE remains an unimplemented documented gap. These are synthetic deterministic enforcement/HTTP results, not model-quality or complete-product evidence.
