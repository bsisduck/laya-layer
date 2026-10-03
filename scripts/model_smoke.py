#!/usr/bin/env python3
"""Actual local HTTP gateway -> private LiteLLM -> Ollama -> governed tool smoke.

Run with uv run --locked python scripts/model_smoke.py --upstream-token-file PATH.
This is explicitly separate from the deterministic suite and makes real inference calls.
"""

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from agentgate.cli import initialize_demo
from agentgate.storage import Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-url", default="http://127.0.0.1:4001/v1")
    parser.add_argument("--upstream-token-file", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("reports/generated/model-smoke.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agentgate-model-") as directory:
        state = Path(directory) / "private"
        initialize_demo(state)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with (Path(directory) / "gateway.log").open("wb") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "agentgate.cli",
                    "--state-dir",
                    str(state),
                    "serve",
                    "--port",
                    str(port),
                    "--policy",
                    str(root / "config/policy-models.yaml"),
                    "--model-url",
                    args.upstream_url,
                    "--model-token-file",
                    str(args.upstream_token_file.resolve()),
                ],
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", timeout=50, trust_env=False
                ) as client:
                    deadline = time.monotonic() + 15
                    while True:
                        try:
                            if client.get("/health/ready").status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError("Gateway did not become ready")
                        time.sleep(0.1)
                    headers = {"Authorization": "Bearer " + (state / "client.token").read_text()}
                    assert client.get("/v1/models").status_code == 401
                    assert (
                        client.get("/v1/models", headers=headers).json()["data"][0]["id"]
                        == "local-demo"
                    )
                    with httpx.Client(timeout=5, trust_env=False) as upstream:
                        assert upstream.get(args.upstream_url + "/models").status_code in (401, 403)
                    timings = {}

                    def complete(messages, **options):
                        started = time.monotonic()
                        response = client.post(
                            "/v1/chat/completions",
                            headers=headers,
                            json={
                                "model": "local-demo",
                                "messages": messages,
                                "max_tokens": 160,
                                **options,
                            },
                        )
                        assert response.status_code == 200, f"Model failed: {response.status_code}"
                        return response.json(), round((time.monotonic() - started) * 1000, 1)

                    result, timings["generation_ms"] = complete(
                        [{"role": "user", "content": "Reply with LOCAL_OK only."}]
                    )
                    assert "LOCAL_OK" in result["choices"][0]["message"]["content"]
                    messages = [
                        {
                            "role": "system",
                            "content": 'You are a tool calling assistant. Call documents_read with arguments {"document_id":"tenant-a-notes"}. Use the exact parameter document_id as a string, not a JSON schema.',
                        },
                        {"role": "user", "content": "Read tenant-a-notes now."},
                    ]
                    tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": "documents_read",
                                "description": "Read a document",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "document_id": {
                                            "type": "string",
                                            "description": "Document identifier, for example tenant-a-notes",
                                        }
                                    },
                                    "required": ["document_id"],
                                },
                            },
                        }
                    ]
                    result, timings["tool_proposal_ms"] = complete(messages, tools=tools)
                    message = result["choices"][0]["message"]
                    call = message["tool_calls"][0]
                    assert call["function"]["name"] == "documents_read"
                    arguments = json.loads(call["function"]["arguments"])
                    assert arguments == {"document_id": "tenant-a-notes"}
                    response = client.post(
                        "/v1/actions/execute",
                        headers=headers,
                        json={
                            "operation": "documents.read",
                            "arguments": arguments,
                        },
                    )
                    assert response.status_code == 200 and response.json()["executed"] is True
                    messages.extend(
                        [
                            message,
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "content": response.json()["result"]["content"],
                            },
                            {
                                "role": "user",
                                "content": "Summarize the returned document in one sentence. Do not call another tool.",
                            },
                        ]
                    )
                    result, timings["tool_result_summary_ms"] = complete(messages)
                    assert result["choices"][0]["message"]["content"]
                    before = len(
                        [
                            e
                            for e in Store(state / "agentgate.sqlite3").events()
                            if e.event_type == "dispatch_intent"
                        ]
                    )
                    for payload in [
                        {"model": "unknown", "messages": [{"role": "user", "content": "hello"}]},
                        {
                            "model": "local-demo",
                            "messages": [{"role": "user", "content": "AGENTGATE_SECRET[fixture]"}],
                        },
                    ]:
                        assert (
                            client.post(
                                "/v1/chat/completions", headers=headers, json=payload
                            ).status_code
                            == 403
                        )
                    events = Store(state / "agentgate.sqlite3").events()
                    assert before == len([e for e in events if e.event_type == "dispatch_intent"])
                    report = {
                        "kind": "real-local-model-and-http-tool-cycle",
                        "status": "pass",
                        "upstream": "private LiteLLM 1.103.2",
                        "model": "llama3.2:1b",
                        "fixture_source_sha256": hashlib.sha256(
                            Path(__file__).read_bytes()
                        ).hexdigest(),
                        "timings": timings,
                        "dispatches": before,
                        "checks": [
                            "unauthenticated gateway denied",
                            "unauthenticated upstream denied",
                            "real generation",
                            "real tool proposal",
                            "governed document execution",
                            "correlated tool result completion",
                            "unknown alias no dispatch",
                            "secret input no dispatch",
                        ],
                        "limitations": [
                            "one fixed successful cycle is not a model quality evaluation",
                            "native loopback trusts local OS user",
                        ],
                    }
                    args.report.write_text(json.dumps(report, indent=2) + "\n")
                    print(json.dumps(report, indent=2))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
