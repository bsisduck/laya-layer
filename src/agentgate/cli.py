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
from agentgate.inference_engine import PROFILES, QUESTION_SET
from agentgate.policy import load_policy
from agentgate.semantic_quota import QuotaUnavailable
from agentgate.semantics import SemanticClient
from agentgate.service import ActionService
from agentgate.storage import CredentialInvalid, StorageUnavailable, Store


def private_file(path: Path, content: bytes) -> None:
    with open(path, "xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


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
    serve.add_argument(
        "--local-console",
        action="store_true",
        help="Trust this loopback computer for automatic operator sessions",
    )
    serve.add_argument("--policy", type=Path, default=Path("config/policy.yaml"))
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--mcp", action="store_true", help="Enable /mcp (install the mcp extra)")
    serve.add_argument("--semantic-url")
    serve.add_argument("--semantic-question-set", choices=list(PROFILES), default=QUESTION_SET)
    serve.add_argument("--model-url", help="Private loopback LiteLLM base URL, including /v1")
    serve.add_argument("--model-token-file", type=Path, help="Private upstream credential file")
    serve.add_argument(
        "--telemetry-config", type=Path, help="Trusted local collector configuration"
    )
    serve.add_argument(
        "--telemetry-token-file", type=Path, help="Private collector credential file"
    )
    serve.add_argument(
        "--semantic-backend", choices=["laya_standard", "laya_coreml"], default="laya_standard"
    )
    worker = commands.add_parser("semantic-worker", help="Serve a supervised local Laya backend")
    worker.add_argument("--backend", choices=["laya_standard", "laya_coreml"], required=True)
    worker.add_argument("--runtime-python", type=Path, required=True)
    worker.add_argument("--root", type=Path, default=Path.cwd())
    worker.add_argument("--port", type=int, default=8091)
    worker.add_argument("--question-set", choices=list(PROFILES), default=QUESTION_SET)
    worker.add_argument(
        "--daily-calls",
        type=int,
        default=1000,
        help="Installation-wide UTC-day semantic call cap; lowering is immediate",
    )
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
    human = commands.add_parser(
        "provision-local-human",
        help="Provision an operator-owned LOCAL DEMO subject (not corporate IAM)",
    )
    human.add_argument("--record-file", type=Path, required=True)
    human.add_argument("--expected-revision", type=int)
    child = commands.add_parser(
        "delegate-local", help="Issue a private one-hop LOCAL DEMO child (not JWT exchange)"
    )
    child.add_argument("--parent-token-file", type=Path, required=True)
    child.add_argument("--subject", required=True)
    child.add_argument("--output-token-file", type=Path, required=True)
    child.add_argument("--lifetime", type=int, default=300)
    child.add_argument("--policy", type=Path, default=Path("config/delegated-policy.yaml"))
    revoke = commands.add_parser(
        "revoke-local-credential", help="Revoke a local parent or child credential"
    )
    revoke.add_argument("--token-file", type=Path, required=True)
    issuer = commands.add_parser(
        "import-issuer-trust", help="CAS-import bounded PUBLIC pinned issuer trust"
    )
    issuer.add_argument("--config-file", type=Path, required=True)
    issuer.add_argument("--expected-generation", type=int, required=True)
    exchange = commands.add_parser(
        "exchange-person-token",
        help="Exchange to a private child file on loopback; no browser login",
    )
    exchange.add_argument("--gateway", required=True)
    exchange.add_argument("--parent-token-file", type=Path, required=True)
    exchange.add_argument("--access-token-file", type=Path, required=True)
    exchange.add_argument("--output-token-file", type=Path, required=True)
    revoke = commands.add_parser(
        "revoke-human", help="CAS-revoke a local or issuer human without clearing its tombstone"
    )
    revoke.add_argument("--subject", required=True)
    revoke.add_argument("--expected-revision", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.command == "import-issuer-trust":
            from agentgate.issuer_cli import import_file

            generation = import_file(args.state_dir, args.config_file, args.expected_generation)
            print(
                f"Public issuer trust activated at generation {generation}; prior issuer children invalidated."
            )
        elif args.command == "exchange-person-token":
            from agentgate.issuer_cli import exchange_file

            exchange_file(
                args.gateway, args.parent_token_file, args.access_token_file, args.output_token_file
            )
            print(
                "Short-lived child stored once in the private output file; issuer profile assertion verified."
            )
        elif args.command == "revoke-human":
            from agentgate.issuer_cli import revoke_file

            revoke_file(args.state_dir, args.subject, args.expected_revision)
            print("Human authority revoked; exchange cannot clear the tombstone.")
        elif args.command == "init-demo":
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
        elif args.command == "provision-local-human":
            from agentgate.authority import provision_subject
            from agentgate.authority_contracts import HumanSubject

            with args.record_file.open("rb") as source:
                raw = source.read(16385)
            if len(raw) > 16384:
                raise ValueError("Subject record exceeds bound")
            record = HumanSubject.model_validate_json(raw)
            provision_subject(
                Store(args.state_dir / "agentgate.sqlite3"),
                record,
                expected_revision=args.expected_revision,
            )
            print(
                "Local-demo subject provisioned by the trusted operator; corporate IAM is not verified."
            )
        elif args.command == "delegate-local":
            from agentgate.authority import issue_child
            from agentgate.control_plane import ControlPlane

            store = Store(args.state_dir / "agentgate.sqlite3")
            if not store.ready():
                raise StorageUnavailable
            # Live installations use their active controls, never a stale policy file.
            with store.connection() as db:
                live = (
                    db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='active_controls'"
                    ).fetchone()
                    is not None
                )
            snapshot = ControlPlane(store).snapshot() if live else None
            created = False

            def persist(token: str) -> None:
                nonlocal created
                private_file(args.output_token_file, token.encode("ascii"))
                created = True

            try:
                issue_child(
                    store,
                    args.parent_token_file.read_text().strip(),
                    args.subject,
                    snapshot.policy if snapshot else load_policy(args.policy),
                    now=time.time(),
                    lifetime=args.lifetime,
                    persist=persist,
                    before_issue=snapshot.assert_current if snapshot else None,
                )
            except Exception:
                if created:
                    args.output_token_file.unlink()
                raise
            print(
                "Local-demo delegated credential created in the new private file; maximum lifetime 300 seconds."
            )
        elif args.command == "revoke-local-credential":
            Store(args.state_dir / "agentgate.sqlite3").revoke(args.token_file.read_text().strip())
            print("Local credential revoked; undispatched descendants are invalid.")
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
                    question_set_id=args.semantic_question_set,
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
            telemetry_config = None
            if args.telemetry_config:
                from agentgate.telemetry_contract import read_config

                telemetry_config = read_config(args.telemetry_config)
            uvicorn.run(
                create_app(
                    service,
                    models=models,
                    enable_mcp=args.mcp,
                    admin_origin=args.admin_origin or f"http://127.0.0.1:{args.port}",
                    local_console=args.local_console,
                    serving_address=("127.0.0.1", args.port),
                    telemetry_config=telemetry_config,
                    telemetry_token_file=args.telemetry_token_file,
                ),
                host="127.0.0.1",
                port=args.port,
                access_log=False,
                proxy_headers=False,
            )
        elif args.command == "semantic-worker":
            from agentgate.semantic_quota import SemanticQuota
            from agentgate.semantic_worker import Supervisor, create_worker

            command = [
                str(args.runtime_python.absolute()),
                str(Path(__file__).with_name("inference_engine.py")),
                "--backend",
                args.backend,
                "--root",
                str(args.root.absolute()),
                "--question-set",
                args.question_set,
            ]
            supervisor = Supervisor(
                command,
                args.backend,
                question_set_id=args.question_set,
                quota=SemanticQuota(
                    args.state_dir / "semantic-quota.sqlite3",
                    args.daily_calls,
                ),
            )
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
                "State upgraded to schema 2 plus scoped tools and authority-v1; credentials, audit and budget spend retained."
            )
    except BrokenPipeError:
        # Avoid a second failing flush during interpreter shutdown. No export
        # checkpoint has been emitted when the data stream fails.
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
        parser.exit(1, "AgentGate output pipe closed before completion.\n")
    except (
        OSError,
        ValueError,
        CredentialInvalid,
        StorageUnavailable,
        QuotaUnavailable,
        httpx.HTTPError,
    ):
        parser.exit(
            1,
            "AgentGate command failed. Check local initialization, policy, service, and state permissions.\n",
        )


if __name__ == "__main__":
    main()
