"""Stopped-installation renewal with recoverable private token publication."""

import importlib
import inspect
import os
import sys
import time
from pathlib import Path
from typing import Any

from agentgate.lifecycle.state import LifecycleError, check_file, validate_data, write_new


def sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def recover_agent_file(store: Any, directory: Path) -> bool:
    from agentgate.storage import credential_digest

    pending = directory / "client.token.next"
    if not pending.exists() and not pending.is_symlink():
        return False
    check_file(pending)
    current = directory / "client.token"
    check_file(current)
    old_digest = credential_digest(current.read_text().strip())
    new_digest = credential_digest(pending.read_text().strip())
    with store.connection() as db:
        old = db.execute("SELECT * FROM credentials WHERE digest=?", (old_digest,)).fetchone()
        new = db.execute("SELECT * FROM credentials WHERE digest=?", (new_digest,)).fetchone()
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='credential_renewals' AND type='table'"
        ).fetchone()
        record = (
            db.execute(
                "SELECT 1 FROM credential_renewals WHERE old_digest=? AND new_digest=? AND purpose='agent'",
                (old_digest, new_digest),
            ).fetchone()
            if exists
            else None
        )
    if (
        old
        and new
        and record
        and old["revoked"]
        and not new["revoked"]
        and old["identity"] == new["identity"]
    ):
        os.replace(pending, current)
        sync_directory(directory)
        return True
    if old and not old["revoked"] and new is None and record is None:
        # Publication started but the DB transaction never committed. Old authority
        # remains exactly as it was; removing an unregistered token revives nothing.
        pending.unlink()
        sync_directory(directory)
        return False
    raise LifecycleError(
        "Renewal recovery is ambiguous/revoked; preserve files and database for inspection"
    )


def renew_agent(directory: Path, *, now: float | None = None) -> None:
    from agentgate.storage import Store, credential_digest

    validate_data(directory)
    module = importlib.import_module("agentgate.admin_credentials")
    if "persist" not in inspect.signature(module.renew_agent_credential).parameters:
        raise LifecycleError(
            "Installed renewal helper lacks recoverable file publication; update the runtime"
        )
    store = Store(directory / "agentgate.sqlite3")
    recovered = recover_agent_file(store, directory)
    current = directory / "client.token"
    check_file(current)
    token = current.read_text().strip()
    now = time.time() if now is None else now
    if recovered:
        with store.connection() as db:
            row = db.execute(
                "SELECT expires_at,revoked FROM credentials WHERE digest=?",
                (credential_digest(token),),
            ).fetchone()
        if row and not row["revoked"] and row["expires_at"] > now:
            return

    def persist(replacement: str) -> None:
        write_new(directory / "client.token.next", replacement.encode("ascii"))
        sync_directory(directory)

    module.renew_agent_credential(store, token, now=now, expires_at=now + 86400, persist=persist)
    if not recover_agent_file(store, directory):
        raise LifecycleError("Renewal did not publish a matching committed authority")


def renew_playground(directory: Path, scope: str) -> None:
    from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
    from agentgate.policy import load_policy
    from agentgate.service import ActionService
    from agentgate.storage import Store

    validate_data(directory)
    module = importlib.import_module("agentgate.admin_credentials")
    documents = demo_documents()
    service = ActionService(
        Store(directory / "agentgate.sqlite3"),
        load_policy(directory / "policy.yaml"),
        DocumentRegistry(documents),
        FixtureExecutor(documents),
        (directory / "audit.key").read_bytes(),
    )
    status = module.playground_credential_status(service, model=scope == "model")
    module.renew_playground_credential(
        service, model=scope == "model", expected_epoch=status["epoch"]
    )


def main() -> None:
    try:
        directory = Path(sys.argv[1])
        if sys.argv[2] == "agent":
            renew_agent(directory)
        else:
            renew_playground(directory, sys.argv[2])
    except Exception as error:
        # Parent maps only these numeric statuses to fixed diagnostics. Never print
        # exception repr, token, raw database rows or traceback to subprocess logs.
        code = {"active": 4, "revoked": 5, "missing": 6, "conflict": 8}.get(
            getattr(error, "reason", ""), 7
        )
        raise SystemExit(code) from None


if __name__ == "__main__":
    main()
