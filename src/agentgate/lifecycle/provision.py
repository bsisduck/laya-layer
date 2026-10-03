"""Executed by the installed gateway environment, never by the bootstrap Python."""

import os
import secrets
import sys
import time
from pathlib import Path

from agentgate.admin import bootstrap_operator
from agentgate.contracts import Identity
from agentgate.lifecycle.state import LifecycleError, check_file, private_dir, save_json, write_new
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


def configure_semantic(directory: Path, semantic: str, *, profile_changed: bool = False) -> None:
    from agentgate.control_plane import ControlPlane

    controls = ControlPlane(Store(directory / "agentgate.sqlite3"))
    snapshot = controls.snapshot()
    required = semantic != "off"
    if snapshot.policy.semantic_required != required or profile_changed:
        policy = snapshot.policy.model_copy(
            update={
                "semantic_required": required,
                "revision": snapshot.policy.revision + 1,
            }
        )
        controls.activate_policy(policy, snapshot.policy.version)


def configure_telemetry(directory: Path, previous_port: int, port: int) -> None:
    from agentgate.telemetry import (
        binding,
        load_state,
        lock_source,
        save_state,
        source_position,
        state_path,
    )
    from agentgate.telemetry_contract import TelemetryConfig, read_config

    token_file = directory / "collector.token"
    if not token_file.exists() and not token_file.is_symlink():
        write_new(token_file, secrets.token_urlsafe(32).encode())
    check_file(token_file)
    destination = directory / "telemetry.json"
    config = TelemetryConfig(origin=f"http://127.0.0.1:{port}", tenant="tenant-a")
    if destination.exists() or destination.is_symlink():
        previous = read_config(destination)
        if previous.tenant != "tenant-a" or previous.origin not in {
            f"http://127.0.0.1:{previous_port}",
            config.origin,
        }:
            raise LifecycleError(
                "Custom telemetry target cannot be overwritten by the local lab installer"
            )
        config = previous.model_copy(update={"origin": config.origin})
    source = directory / "agentgate.sqlite3"
    if previous_port != port and state_path(source).exists():
        # Both endpoints are this installation's same private collector database,
        # tenant and key. This is a port move, never a general destination reset.
        check_file(directory / "collector.sqlite3")
        check_file(state_path(source))
        with lock_source(source):
            old_config = config.model_copy(update={"origin": f"http://127.0.0.1:{previous_port}"})
            try:
                delivery = load_state(source, old_config)
            except ValueError:
                # A crash may have published the new binding before config/metadata.
                # Accept only the exact new binding; unknown targets still fail closed.
                delivery = load_state(source, config)
            source_position(source, delivery)
            save_state(source, delivery.model_copy(update={"binding": binding(source, config)}))
            save_json(destination, config.model_dump(mode="json"))
    else:
        save_json(destination, config.model_dump(mode="json"))


if __name__ == "__main__":
    if sys.argv[1] == "--configure-telemetry":
        configure_telemetry(Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
    elif sys.argv[1] == "--configure-semantic":
        configure_semantic(
            Path(sys.argv[2]), sys.argv[3], profile_changed=sys.argv[4:5] == ["changed"]
        )
    else:
        initialize(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
