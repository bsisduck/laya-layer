import asyncio
import json
import os
import sqlite3

import pytest
from test_gateway import Harness
from test_gateway import harness as harness

from agentgate.telemetry import Sender, SenderBusy, load_state, telemetry_status
from agentgate.telemetry_contract import TelemetryConfig, read_token


def config(**updates):
    return TelemetryConfig(origin="http://127.0.0.1:18998", tenant="tenant-a", **updates)


def token_file(tmp_path):
    path = tmp_path / "collector.token"
    path.write_text("synthetic-test-credential-not-used-elsewhere")
    path.chmod(0o600)
    return path


def test_persistent_pending_batch_retries_without_cursor_advance(
    harness: Harness, tmp_path, monkeypatch
):
    harness.read()
    cfg = config(batch_events=1)
    clock = [1000.0]
    seen = []

    async def fail(config, token, batch):
        seen.append(batch.model_dump())
        raise ValueError("untrusted response must not be logged")

    monkeypatch.setattr("agentgate.telemetry.post_batch", fail)
    with Sender(harness.store.path, cfg, token_file(tmp_path), clock=lambda: clock[0]) as sender:
        state = asyncio.run(sender.once())
        assert state.cursor == 0 and state.pending_through == 1 and state.failures == 1
        assert state.next_attempt_at == 1001.0
    assert telemetry_status(harness.store.path, cfg)["source_lag_sequences"] == 2
    with Sender(
        harness.store.path, cfg, tmp_path / "collector.token", clock=lambda: clock[0]
    ) as sender:
        asyncio.run(sender.once())  # Persisted backoff survives restart.
        assert len(seen) == 1
        clock[0] = 1001.0
        harness.read()  # New audit records cannot change the retained batch.
        state = asyncio.run(sender.once())
        assert state.failures == 2 and state.next_attempt_at == 1003.0
    assert seen[0] == seen[1]

    async def success(config, token, batch):
        seen.append(batch.model_dump())

    monkeypatch.setattr("agentgate.telemetry.post_batch", success)
    clock[0] = 1003.0
    with Sender(
        harness.store.path, cfg, tmp_path / "collector.token", clock=lambda: clock[0]
    ) as sender:
        state = asyncio.run(sender.once())
    assert state.cursor == 1 and state.pending is None and state.failures == 0
    assert state.acknowledged_events == 1 and state.last_delivery_ms >= 0
    assert seen[-1] == seen[0]
    assert load_state(harness.store.path, cfg) == state
    saved = harness.store.path.with_suffix(".telemetry.json").read_text()
    assert "untrusted response" not in saved and "synthetic-test-credential" not in saved


def test_source_lock_and_configuration_binding(harness: Harness, tmp_path):
    path = token_file(tmp_path)
    cfg = config()
    with Sender(harness.store.path, cfg, path) as sender:
        with pytest.raises(SenderBusy), Sender(harness.store.path, cfg, path):
            pass
        asyncio.run(sender.once())
    with Sender(harness.store.path, cfg.model_copy(update={"tenant": "tenant-b"}), path) as sender:
        with pytest.raises(ValueError, match="binding"):
            asyncio.run(sender.once())


def test_gap_is_not_skipped_and_other_tenant_rows_can_be_scanned(harness: Harness, tmp_path):
    harness.read()
    cfg = config()
    with sqlite3.connect(harness.store.path) as db:
        db.execute("DELETE FROM audit_events WHERE sequence=1")
    with Sender(harness.store.path, cfg, token_file(tmp_path)) as sender:
        state = asyncio.run(sender.once())
    assert state.cursor == 0 and state.last_error == "source_invalid"


def test_unmatched_scope_advances_without_delivery(harness: Harness, tmp_path, monkeypatch):
    harness.read()
    cfg = config().model_copy(update={"tenant": "absent"})

    async def forbidden(*args):
        pytest.fail("Must not deliver another tenant's rows")

    monkeypatch.setattr("agentgate.telemetry.post_batch", forbidden)
    with Sender(harness.store.path, cfg, token_file(tmp_path)) as sender:
        state = asyncio.run(sender.once())
    assert state.cursor == 2 and state.acknowledged_events == 0


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:1234",
        "http://external.example",
        "https://user:secret@host",
        "https://host/path",
        "https://host?url=x",
        "https://host#x",
        "https://host:0",
        "https://host:65536",
        "http://127.0.0.1:12/",
        "file:///tmp/foo",
        "https://host\n",
    ],
)
def test_rejects_non_origin_and_plaintext_remote_destination(origin):
    with pytest.raises(ValueError):
        TelemetryConfig(origin=origin, tenant="tenant-a")


def test_private_secret_and_status_do_not_read_or_emit_credentials(harness: Harness, tmp_path):
    path = token_file(tmp_path)
    assert read_token(path)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        read_token(path)
    harness.read()
    status = telemetry_status(harness.store.path, config(backlog_high_watermark=1))
    assert status["backpressure"] is True and status["status"] == "backpressure"
    assert "tenant-a" not in json.dumps(status)
    assert not harness.store.path.with_suffix(".telemetry.json").exists()


def test_corrupt_state_and_replaced_source_fail_closed(harness: Harness, tmp_path):
    cfg = config()
    with Sender(harness.store.path, cfg, token_file(tmp_path)) as sender:
        asyncio.run(sender.once())
    replacement = tmp_path / "replacement.sqlite3"
    with sqlite3.connect(harness.store.path) as src, sqlite3.connect(replacement) as dest:
        src.backup(dest)
    os.replace(replacement, harness.store.path)
    assert telemetry_status(harness.store.path, cfg)["status"] == "unavailable"


def test_batch_byte_bound_and_fixed_crash_scratch_slot(harness: Harness, tmp_path, monkeypatch):
    from agentgate.telemetry import state_path

    for _ in range(10):
        harness.read()
    cfg = config(batch_bytes=4096)

    async def failed(*args):
        raise ValueError("offline")

    monkeypatch.setattr("agentgate.telemetry.post_batch", failed)
    with Sender(harness.store.path, cfg, token_file(tmp_path)) as sender:
        state = asyncio.run(sender.once())
    assert len(state.pending.model_dump_json().encode()) <= 4096
    assert len(state.pending.events) < 20 and state.cursor == 0
    # Repeated writes/crashes reuse one scratch slot, never an unbounded temp spool.
    scratch = state_path(harness.store.path).with_suffix(".tmp")
    scratch.write_text("interrupted write")
    scratch.chmod(0o644)
    from agentgate.telemetry import save_state

    save_state(harness.store.path, state)
    assert not scratch.exists() and not list(tmp_path.glob(".telemetry-*"))
    assert state_path(harness.store.path).stat().st_mode & 0o077 == 0


def test_invalid_stored_event_blocks_without_network(harness: Harness, tmp_path, monkeypatch):
    harness.read()
    with sqlite3.connect(harness.store.path) as db:
        db.execute(
            "UPDATE audit_events SET event=? WHERE sequence=1", ('{"raw":"' + "x" * 65536 + '"}',)
        )

    async def forbidden(*args):
        pytest.fail("Malformed source must not be delivered")

    monkeypatch.setattr("agentgate.telemetry.post_batch", forbidden)
    with Sender(harness.store.path, config(), token_file(tmp_path)) as sender:
        state = asyncio.run(sender.once())
    assert state.cursor == 0 and state.last_error == "source_invalid"


def test_same_sender_rejects_overlapping_iterations(harness: Harness, tmp_path, monkeypatch):
    harness.read()

    async def exercise(sender):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def waiting(*args):
            entered.set()
            await release.wait()

        monkeypatch.setattr("agentgate.telemetry.post_batch", waiting)
        task = asyncio.create_task(sender.once())
        await entered.wait()
        try:
            with pytest.raises(SenderBusy):
                await sender.once()
        finally:
            release.set()
            await task

    with Sender(harness.store.path, config(), token_file(tmp_path)) as sender:
        asyncio.run(exercise(sender))
