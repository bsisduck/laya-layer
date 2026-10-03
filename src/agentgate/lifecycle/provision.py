"""Executed by the installed gateway environment, never by the bootstrap Python."""

import os
import secrets
import sys
import time
from pathlib import Path

from agentgate.admin import bootstrap_operator
from agentgate.contracts import Identity
from agentgate.lifecycle.state import private_dir, write_new
from agentgate.policy import load_policy
from agentgate.storage import Store


def initialize(directory: Path, policy_path: Path, proxy_path: Path, semantic: str) -> None:
    os.umask(0o077)
    directory.mkdir(mode=0o700, exist_ok=False)
    private_dir(directory)
    policy = load_policy(policy_path).model_copy(update={"semantic_required": semantic != "off"})
    # JSON is a YAML subset, and keeps the installed configuration independent of checkout files.
    write_new(directory / "policy.yaml", policy.model_dump_json(indent=2).encode())
    write_new(directory / "litellm.yaml", proxy_path.read_bytes())
    store = Store(directory / "agentgate.sqlite3")
    store.initialize()
    write_new(directory / "audit.key", secrets.token_bytes(32))
    write_new(directory / "worker.token", secrets.token_urlsafe(32).encode())
    write_new(directory / "litellm.token", ("sk-" + secrets.token_urlsafe(32)).encode())
    token = store.issue(
        Identity(
            principal_id="analyst-demo",
            tenant_id="tenant-a",
            agent_id="demo-client",
            root_run_id="run-demo",
            roles=("analyst",),
            operations=("documents.read", "memory.query", "mail.send", "chat.completions"),
        ),
        time.time() + 86400,
    )
    write_new(directory / "client.token", token.encode())
    with store.connection() as connection:
        connection.executemany(
            "INSERT INTO memory_entries VALUES (?, ?, 'internal', ?)",
            [
                ("tenant-a", "demo-notes", "Quarterly memory notes for tenant A."),
                ("tenant-b", "demo-notes", "Quarterly private memory notes for tenant B."),
            ],
        )
    bootstrap_operator(directory, policy)


def configure_semantic(directory: Path, semantic: str) -> None:
    from agentgate.control_plane import ControlPlane

    controls = ControlPlane(Store(directory / "agentgate.sqlite3"))
    snapshot = controls.snapshot()
    required = semantic != "off"
    if snapshot.policy.semantic_required != required:
        policy = snapshot.policy.model_copy(
            update={
                "semantic_required": required,
                "revision": snapshot.policy.revision + 1,
            }
        )
        controls.activate_policy(policy, snapshot.policy.version)


if __name__ == "__main__":
    if sys.argv[1] == "--configure-semantic":
        configure_semantic(Path(sys.argv[2]), sys.argv[3])
    else:
        initialize(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
