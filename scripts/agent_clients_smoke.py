#!/usr/bin/env python3
"""Real direct/Hermes local generation cycles; semantic inspection DISABLED.

Reuses persistent private fixture state and existing credentials/spend. No model
installation, cloud fallback or automatic retry. Obtain the inference slot first.
"""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from semantic_evaluate import EvaluationLock

from agentgate.agents.client import decode
from agentgate.cli import initialize_demo
from agentgate.model_budgets import ModelLedger
from agentgate.storage import Store

ROOT = Path(__file__).resolve().parents[1]
PROMPT = (
    'Call documents_read with arguments {"document_id":"tenant-a-notes"}. '
    "Use the parameter document_id as a string. After the tool succeeds, summarize "
    "the returned content in one sentence. Do not call another tool after receiving its result."
)


def owned_gateway(args, state, port, log, lock_fd):
    return subprocess.Popen(
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
            str(ROOT / "config/policy-models.yaml"),
            "--model-url",
            "http://127.0.0.1:4001/v1",
            "--model-token-file",
            str(args.upstream_token_file.resolve()),
            "--mcp",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        pass_fds=(lock_fd,),
    )


def evidence(store, after):
    events = [e for e in store.events() if e.event_id not in after]
    return [
        {
            "event_id": e.event_id,
            "trace_id": e.trace_id,
            "root_run_id": e.root_run_id,
            "operation": e.operation,
            "event_type": e.event_type,
            "decision": e.decision,
            "reason_codes": list(e.reason_codes),
        }
        for e in events
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        required=True,
        help="Dedicated persistent private demo state; never reset",
    )
    parser.add_argument(
        "--assets-root", type=Path, required=True, help="Shared semantic-evaluation lock root"
    )
    parser.add_argument(
        "--upstream-token-file", type=Path, required=True, help="Read only by gateway child"
    )
    parser.add_argument("--hermes-source", type=Path, required=True)
    parser.add_argument(
        "--clients",
        nargs="+",
        choices=("direct-rest", "direct-mcp", "hermes-mcp"),
        default=["direct-rest", "direct-mcp", "hermes-mcp"],
        help="Explicit invocations to measure; never automatic retries",
    )
    parser.add_argument("--report", type=Path, default=Path("reports/generated/agent-clients.json"))
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    # Reserve evidence before dispatch. Failed attempts must not be overwritten.
    args.report.touch(exist_ok=False)
    state = args.state_dir.resolve()
    if not state.exists():
        initialize_demo(state)
    store = Store(state / "agentgate.sqlite3")
    report = {
        "kind": "real-local-agent-cycles",
        "semantic_profile": "disabled; not Laya protection",
        "generator": "private LiteLLM -> Ollama llama3.2:1b",
        "runs": [],
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }
    with (
        EvaluationLock(args.assets_root.resolve()) as lock_fd,
        tempfile.TemporaryDirectory(prefix="agentgate-cycle-") as temp,
    ):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        with (Path(temp) / "gateway.log").open("wb") as log:
            process = owned_gateway(args, state, port, log, lock_fd)
            try:
                with httpx.Client(base_url=origin, timeout=5, trust_env=False) as probe:
                    deadline = time.monotonic() + 15
                    while True:
                        try:
                            if probe.get("/health/ready").status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError("Gateway unavailable")
                        time.sleep(0.1)
                for client in args.clients:
                    before = {e.event_id for e in store.events()}
                    common = [
                        "--gateway",
                        origin,
                        "--token-file",
                        str(state / "client.token"),
                        "--prompt",
                        PROMPT,
                    ]
                    if client == "hermes-mcp":
                        command = [
                            sys.executable,
                            "-m",
                            "agentgate.agents.hermes",
                            "--source",
                            str(args.hermes_source.resolve()),
                            "run",
                            *common,
                        ]
                    else:
                        command = [
                            sys.executable,
                            "-m",
                            "agentgate.agents.direct",
                            *common,
                            "--transport",
                            client.split("-")[1],
                            "--state",
                            str(Path(temp) / (client + ".json")),
                        ]
                    started = time.monotonic()
                    result = subprocess.run(
                        command,
                        cwd=ROOT,
                        env={
                            "PATH": os.environ.get("PATH", ""),
                            "PYTHONNOUSERSITE": "1",
                            "PYTHONUTF8": "1",
                            "LANG": "C.UTF-8",
                        },
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        timeout=320,
                        pass_fds=(lock_fd,),
                    )
                    response = decode(result.stdout)
                    measured = evidence(store, before)
                    counts = {
                        operation: sum(
                            e["event_type"] == "dispatch_intent" and e["operation"] == operation
                            for e in measured
                        )
                        for operation in ("chat.completions", "documents.read")
                    }
                    passed = (
                        result.returncode == 0
                        and response.get("status") == "completed"
                        and counts == {"chat.completions": 2, "documents.read": 1}
                    )
                    report["runs"].append(
                        {
                            "client": client,
                            "status": "pass" if passed else "fail",
                            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                            "dispatches": counts,
                            "events": measured,
                            "trace": response.get("trace", []),
                            "active_tools": response.get("active_tools"),
                            "hermes_source": response.get("source_commit"),
                            "hermes_lock_sha256": response.get("lock_sha256"),
                            "failure": response.get("reason"),
                            "text_released": bool(response.get("text")),
                        }
                    )
                    if not passed:
                        break
                report["status"] = (
                    "pass"
                    if len(report["runs"]) == len(args.clients)
                    and all(r["status"] == "pass" for r in report["runs"])
                    else "fail"
                )
                with store.connection() as connection:
                    report["outbox_count"] = connection.execute(
                        "SELECT count(*) FROM tool_outbox"
                    ).fetchone()[0]
                report["tool_budget_counters"] = store.budget_counters()
                report["model_budget_counters"] = ModelLedger(store).counters()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(args.report),
                "runs": [
                    {k: r[k] for k in ("client", "status", "elapsed_ms", "dispatches", "failure")}
                    for r in report["runs"]
                ],
            }
        )
    )
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
