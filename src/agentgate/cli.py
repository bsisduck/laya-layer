"""Local demo provisioning; credentials are never emitted to stdout."""

import argparse
import json
import os
import secrets
import time
from pathlib import Path

import httpx
import uvicorn

from agentgate.app import create_app
from agentgate.contracts import Identity
from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
from agentgate.policy import load_policy
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
    token = store.issue(
        Identity(
            principal_id="analyst-demo",
            tenant_id="tenant-a",
            agent_id="demo-reader",
            root_run_id="run-demo",
            roles=("analyst",),
            operations=("documents.read",),
        ),
        time.time() + 3600,
    )
    private_file(directory / "client.token", token.encode("ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentGate document enforcement demo")
    parser.add_argument("--state-dir", type=Path, default=Path(".agentgate"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "init-demo", help="Create private local state and a one-hour scoped credential"
    )
    serve = commands.add_parser("serve", help="Serve the document-only gateway on loopback")
    serve.add_argument("--policy", type=Path, default=Path("config/policy.yaml"))
    serve.add_argument("--port", type=int, default=8000)
    read = commands.add_parser(
        "demo-read", help="Call the gateway with the local scoped credential"
    )
    read.add_argument("document_id", nargs="?", default="tenant-a-notes")
    read.add_argument("--port", type=int, default=8000)
    audit = commands.add_parser("audit", help="Print minimized local audit events")
    audit.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    try:
        if args.command == "init-demo":
            initialize_demo(args.state_dir)
            print(
                "Demo initialized. Scoped credential stored in the private client.token file; expires in one hour."
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
            )
            uvicorn.run(create_app(service), host="127.0.0.1", port=args.port, access_log=False)
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
    except (OSError, ValueError, StorageUnavailable, httpx.HTTPError):
        parser.exit(
            1,
            "AgentGate command failed. Check local initialization, policy, service, and state permissions.\n",
        )


if __name__ == "__main__":
    main()
