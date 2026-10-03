"""Local demo provisioning; credentials are never emitted to stdout."""

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

import httpx
import uvicorn

from agentgate.app import create_app
from agentgate.audit_export import export_page
from agentgate.contracts import Identity
from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
from agentgate.policy import load_policy
from agentgate.semantics import SemanticClient
from agentgate.service import ActionService
from agentgate.storage import StorageUnavailable, Store


def private_file(path: Path, content: bytes) -> None:
    with open(path, "xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write(content)


def initialize_demo(directory: Path) -> None:
    # Refuse reuse, rather than rotate keys or invalidate existing audit correlation silently.
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    store = Store(directory / "agentgate.sqlite3")
    store.initialize()
    private_file(directory / "audit.key", secrets.token_bytes(32))
    private_file(directory / "worker.token", secrets.token_urlsafe(32).encode())
    token = store.issue(
        Identity(
            principal_id="analyst-demo",
            tenant_id="tenant-a",
            agent_id="demo-reader",
            root_run_id="run-demo",
            roles=("analyst",),
            operations=("documents.read", "memory.query", "mail.send", "chat.completions"),
        ),
        time.time() + 3600,
    )
    private_file(directory / "client.token", token.encode("ascii"))
    with store.connection() as connection:
        connection.executemany(
            "INSERT INTO memory_entries VALUES (?, ?, 'internal', ?)",
            [
                ("tenant-a", "demo-notes", "Quarterly memory notes for tenant A."),
                ("tenant-b", "demo-notes", "Quarterly private memory notes for tenant B."),
            ],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentGate scoped tool enforcement demo")
    parser.add_argument("--state-dir", type=Path, default=Path(".agentgate"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "init-demo", help="Create private local state and a one-hour scoped credential"
    )
    serve = commands.add_parser(
        "serve", help="Serve the governed model and tool gateway on loopback"
    )
    operator = commands.add_parser("init-operator", help="Create a private operator token once")
    operator.add_argument("--policy", type=Path, default=Path("config/policy.yaml"))
    serve.add_argument(
        "--admin-origin", help="Exact operator browser origin; defaults to loopback URL"
    )
    serve.add_argument("--policy", type=Path, default=Path("config/policy.yaml"))
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--mcp", action="store_true", help="Enable /mcp (install the mcp extra)")
    serve.add_argument("--semantic-url")
    serve.add_argument("--model-url", help="Private loopback LiteLLM base URL, including /v1")
    serve.add_argument("--model-token-file", type=Path, help="Private upstream credential file")
    serve.add_argument(
        "--semantic-backend", choices=["laya_standard", "laya_coreml"], default="laya_standard"
    )
    worker = commands.add_parser("semantic-worker", help="Serve a supervised local Laya backend")
    worker.add_argument("--backend", choices=["laya_standard", "laya_coreml"], required=True)
    worker.add_argument("--runtime-python", type=Path, required=True)
    worker.add_argument("--root", type=Path, default=Path.cwd())
    worker.add_argument("--port", type=int, default=8091)
    read = commands.add_parser(
        "demo-read", help="Call the gateway with the local scoped credential"
    )
    read.add_argument("document_id", nargs="?", default="tenant-a-notes")
    read.add_argument("--port", type=int, default=8000)
    audit = commands.add_parser("audit", help="Print minimized local audit events")
    audit.add_argument("--limit", type=int, default=20)
    export = commands.add_parser(
        "audit-export", help="Export one bounded page for a local operator"
    )
    scope = export.add_mutually_exclusive_group(required=True)
    scope.add_argument("--tenant")
    scope.add_argument("--unattributed", action="store_true")
    export.add_argument("--format", choices=["jsonl", "ecs", "splunk-hec"], default="jsonl")
    export.add_argument("--after-sequence", type=int, default=0)
    export.add_argument("--through-sequence", type=int)
    export.add_argument("--limit", type=int, default=100)
    budgets = commands.add_parser("budgets", help="Print bounded local tool-budget counters")
    budgets.add_argument("--limit", type=int, default=100)
    commands.add_parser(
        "migrate", help="Upgrade existing state after stopping and backing up the gateway"
    )
    args = parser.parse_args()
    try:
        if args.command == "init-demo":
            initialize_demo(args.state_dir)
            print(
                "Demo initialized. Scoped credential stored in the private client.token file; expires in one hour."
            )
        elif args.command == "init-operator":
            from agentgate.admin import bootstrap_operator

            bootstrap_operator(args.state_dir, load_policy(args.policy))
            print(
                "Operator initialized. Credential stored in private operator.token; never shared with agents."
            )
        elif args.command == "serve":
            policy = load_policy(args.policy)
            store = Store(args.state_dir / "agentgate.sqlite3")
            if not store.ready():
                raise StorageUnavailable
            documents = demo_documents()
            service = ActionService(
                store,
                policy,
                DocumentRegistry(documents),
                FixtureExecutor(documents),
                (args.state_dir / "audit.key").read_bytes(),
                semantic=SemanticClient(
                    args.semantic_url,
                    (args.state_dir / "worker.token").read_text().strip(),
                    args.semantic_backend,
                )
                if args.semantic_url
                else None,
            )
            models = None
            if bool(args.model_url) != bool(args.model_token_file):
                raise ValueError("Model URL and token file must be configured together")
            if args.model_url:
                from agentgate.models import ModelService, PrivateProvider

                models = ModelService(
                    service,
                    PrivateProvider(args.model_url, args.model_token_file.read_text().strip()),
                )
            uvicorn.run(
                create_app(
                    service,
                    models=models,
                    enable_mcp=args.mcp,
                    admin_origin=args.admin_origin or f"http://127.0.0.1:{args.port}",
                ),
                host="127.0.0.1",
                port=args.port,
                access_log=False,
            )
        elif args.command == "semantic-worker":
            from agentgate.semantic_worker import Supervisor, create_worker

            command = [
                str(args.runtime_python.absolute()),
                str(Path(__file__).with_name("inference_engine.py")),
                "--backend",
                args.backend,
                "--root",
                str(args.root.absolute()),
            ]
            supervisor = Supervisor(command, args.backend)
            app = create_worker(supervisor, (args.state_dir / "worker.token").read_text().strip())
            uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
        elif args.command == "demo-read":
            token = (args.state_dir / "client.token").read_text().strip()
            with httpx.Client(timeout=10, trust_env=False) as client:
                result = client.post(
                    f"http://127.0.0.1:{args.port}/v1/actions/execute",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "operation": "documents.read",
                        "arguments": {"document_id": args.document_id},
                    },
                )
            print(json.dumps(result.json(), indent=2))
            if result.is_error:
                raise SystemExit(1)
        elif args.command == "audit":
            for event in Store(args.state_dir / "agentgate.sqlite3").events(args.limit):
                print(event.model_dump_json())
        elif args.command == "audit-export":
            page = export_page(
                args.state_dir / "agentgate.sqlite3",
                tenant=args.tenant,
                format=args.format,
                after_sequence=args.after_sequence,
                through_sequence=args.through_sequence,
                limit=args.limit,
            )
            if page.lines:
                sys.stdout.write("\n".join(page.lines) + "\n")
            sys.stdout.flush()
            print(json.dumps(page.metadata()), file=sys.stderr)
        elif args.command == "budgets":
            for counter in Store(args.state_dir / "agentgate.sqlite3").budget_counters(args.limit):
                print(json.dumps(counter))
        elif args.command == "migrate":
            path = args.state_dir / "agentgate.sqlite3"
            if not path.is_file():
                raise StorageUnavailable
            Store(path).initialize()
            print(
                "State upgraded to schema 2 plus scoped tools; credentials, audit and budget spend retained."
            )
    except BrokenPipeError:
        # Avoid a second failing flush during interpreter shutdown. No export
        # checkpoint has been emitted when the data stream fails.
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
        parser.exit(1, "AgentGate output pipe closed before completion.\n")
    except (OSError, ValueError, StorageUnavailable, httpx.HTTPError):
        parser.exit(
            1,
            "AgentGate command failed. Check local initialization, policy, service, and state permissions.\n",
        )


if __name__ == "__main__":
    main()
