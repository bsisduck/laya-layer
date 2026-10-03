import asyncio
import json
import select
import sqlite3
import subprocess
import sys

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from telemetry_http import live_server
from test_gateway import Harness
from test_gateway import harness as harness
from test_telemetry import token_file

from agentgate.telemetry import Sender, SenderBusy, load_state, telemetry_status
from agentgate.telemetry_collector import Collector, create_collector
from agentgate.telemetry_contract import Batch, TelemetryConfig, batch_digest, read_token


def received(path):
    with sqlite3.connect(path) as db:
        return [
            json.loads(row[0]) for row in db.execute("SELECT record FROM received ORDER BY rowid")
        ]


def run_once(source, cfg, token, now=2000.0):
    with Sender(source, cfg, token, clock=lambda: now) as sender:
        return asyncio.run(sender.once())


def test_pending_and_approved_mail_events_do_not_stall_delivery(harness: Harness, tmp_path):
    identity = harness.identity.model_copy(update={"operations": ("mail.send",)})
    agent_token = harness.store.issue(identity, 2000.0)
    payload = {
        "operation": "mail.send",
        "arguments": {
            "recipient": "reviewer@demo.internal",
            "subject": "synthetic approval",
            "body": "Local fixture",
            "idempotency_key": "telemetry-mail",
        },
    }
    result = harness.client.post(
        "/v1/actions/execute", json=payload, headers={"Authorization": f"Bearer {agent_token}"}
    )
    assert result.status_code == 202 and result.json()["executed"] is False
    token = token_file(tmp_path)
    db = tmp_path / "collector.sqlite3"
    collector = Collector(db, "tenant-a")
    with live_server(create_collector(collector, token)) as origin:
        cfg = TelemetryConfig(origin=origin, tenant="tenant-a")
        first = run_once(harness.store.path, cfg, token)
        assert first.cursor == 1 and first.last_error is None
        action = harness.service.tools.list_approvals(tenant_id="tenant-a")[0]
        harness.service.tools.decide(
            tenant_id="tenant-a",
            action_id=action["action_id"],
            fingerprint=action["fingerprint"],
            approve=True,
            actor="operator",
        )
        second = run_once(harness.store.path, cfg, token)
        assert second.cursor == 2 and second.last_error is None
        records = received(db)
        assert [(e["event_type"], e["decision"], e["executed"]) for e in records] == [
            ("action_pending", "require_approval", False),
            ("approval_decided", "require_approval", False),
        ]
        assert harness.service.tools.outbox(tenant_id="tenant-a") == []
        assert run_once(harness.store.path, cfg, token).acknowledged_events == 2
        assert len(received(db)) == 2


def test_live_gateway_to_collector_correlates_privacy_and_scope(harness: Harness, tmp_path):
    token = token_file(tmp_path)
    db = tmp_path / "collector.sqlite3"
    collector = Collector(db, "tenant-a")
    for document in ("tenant-a-notes", "tenant-a-contact", "tenant-a-leak", "tenant-b-notes"):
        harness.read(document)
    # Include unattributed and another credential-owned tenant; neither can leak.
    harness.client.post("/v1/actions/execute", json={"tenant_id": "tenant-a"})
    foreign = harness.store.issue(
        harness.identity.model_copy(update={"tenant_id": "tenant-b"}), 2000.0
    )
    harness.client.post(
        "/v1/actions/execute",
        headers={"Authorization": f"Bearer {foreign}"},
        json={"operation": "documents.read", "arguments": {"document_id": "tenant-b-notes"}},
    )
    with live_server(create_collector(collector, token)) as origin:
        cfg = TelemetryConfig(origin=origin, tenant="tenant-a")
        assert received(db) == []
        wrong = tmp_path / "wrong.token"
        wrong.write_text("wrong-private-credential-synthetic-12345")
        wrong.chmod(0o600)
        failed = run_once(harness.store.path, cfg, wrong)
        assert failed.cursor == 0 and received(db) == []
        delivered = run_once(harness.store.path, cfg, token, now=2001.0)
        assert delivered.cursor == 10 and delivered.acknowledged_events == 7
        records = received(db)
        terminal = [row for row in records if row["event_type"] != "dispatch_intent"]
        assert [(r["decision"], r["executed"]) for r in terminal] == [
            ("allow", True),
            ("redact", True),
            ("deny", True),
            ("deny", False),
        ]
        assert {r["event_id"] for r in records} == {
            e.event_id for e in harness.store.events() if e.tenant_id == "tenant-a"
        }
        assert all(
            sum(r["event_id"] == event["event_id"] for r in records) == 1 for event in records
        )
        assert {r["policy_version"] for r in records} == {"test:1"}
        assert all(r["tenant_id"] == "tenant-a" for r in records)
        for secret in (
            harness.token,
            foreign,
            read_token(token),
            "payload_digest",
            "quarterly notes",
            "AGENTGATE_SECRET[",
            "@example",
        ):
            assert secret not in json.dumps(records)


@pytest.mark.parametrize(
    "mode",
    [
        "version_type",
        "partial",
        "unknown",
        "extra_error",
        "duplicate_id",
        "redirect",
        "throttle",
        "unavailable",
        "oversize",
        "compressed",
        "bad_type",
        "duplicate_key",
        "slow",
    ],
)
def test_live_invalid_ack_never_advances_and_duplicate_replay_dedupes(
    harness: Harness, tmp_path, mode
):
    harness.read()
    token = token_file(tmp_path)
    db = tmp_path / "collector.sqlite3"
    collector = Collector(db, "tenant-a")
    fault = [True]
    requests = []
    app = FastAPI()

    @app.post("/v1/events")
    async def ingest(request: Request):
        body = await request.body()
        requests.append(body)
        batch = Batch.model_validate_json(body)
        if fault[0] and mode == "partial":
            subset = batch.events[:1]
            ack = collector.accept(Batch(batch_id=batch_digest(subset), events=subset)).model_dump()
            ack["batch_id"] = batch.batch_id
        else:
            ack = collector.accept(batch).model_dump()
        if not fault[0]:
            return JSONResponse(ack)
        if mode == "version_type":
            ack["version"] = True
        elif mode == "unknown":
            ack["batch_id"] = "a" * 64
        elif mode == "extra_error":
            ack["errors"] = ["untrusted-secret-must-not-be-persisted"]
        elif mode == "duplicate_id":
            ack["accepted_event_ids"] = [batch.events[0].event_id] * 2
        elif mode == "redirect":
            return Response(status_code=307, headers={"Location": "/must-not-follow"})
        elif mode in ("throttle", "unavailable"):
            return Response(status_code=429 if mode == "throttle" else 503)
        elif mode == "oversize":
            return Response(b" " * 32769, media_type="application/json")
        elif mode == "compressed":
            return Response(
                b"x", headers={"content-encoding": "gzip"}, media_type="application/json"
            )
        elif mode == "bad_type":
            return Response(json.dumps(ack), media_type="text/plain")
        elif mode == "duplicate_key":
            return Response('{"version":1,' + json.dumps(ack)[1:], media_type="application/json")
        elif mode == "slow":

            async def slow():
                yield b" "
                await asyncio.sleep(0.5)
                yield json.dumps(ack).encode()

            return StreamingResponse(slow(), media_type="application/json")
        return JSONResponse(ack)

    @app.post("/must-not-follow")
    def forbidden():
        pytest.fail("Redirect followed")

    with live_server(app) as origin:
        cfg = TelemetryConfig(
            origin=origin, tenant="tenant-a", timeout_seconds=0.15 if mode == "slow" else 5.0
        )
        first = run_once(harness.store.path, cfg, token)
        assert (
            first.cursor == 0
            and first.pending is not None
            and first.last_error == "delivery_failed"
        )
        assert len(received(db)) == (1 if mode == "partial" else 2)
        assert (
            "untrusted-secret" not in harness.store.path.with_suffix(".telemetry.json").read_text()
        )
        fault[0] = False
        second = run_once(harness.store.path, cfg, token, now=2001.0)
        assert second.cursor == 2 and second.pending is None
        assert requests[0] == requests[1]
        assert len(received(db)) == 2 and len({r["event_id"] for r in received(db)}) == 2


def test_process_crash_after_collector_commit_replays_one_row(harness: Harness, tmp_path):
    harness.read("tenant-b-notes")  # One pre-dispatch denial event.
    token = token_file(tmp_path)
    db = tmp_path / "collector.sqlite3"
    with live_server(create_collector(Collector(db, "tenant-a"), token)) as origin:
        cfg = TelemetryConfig(origin=origin, tenant="tenant-a")
        config_path = tmp_path / "telemetry.json"
        config_path.write_text(cfg.model_dump_json())
        code = """import asyncio, os, sys
from pathlib import Path
import agentgate.telemetry as telemetry
from agentgate.telemetry_contract import read_config
original = telemetry.post_batch
async def crash(*args):
    await original(*args)
    os._exit(71)
telemetry.post_batch = crash
with telemetry.Sender(Path(sys.argv[1]), read_config(Path(sys.argv[2])), Path(sys.argv[3])) as sender:
    asyncio.run(sender.once())
"""
        process = subprocess.run(
            [sys.executable, "-c", code, str(harness.store.path), str(config_path), str(token)],
            capture_output=True,
            timeout=10,
        )
        assert process.returncode == 71 and process.stderr == b""
        assert len(received(db)) == 1
        assert load_state(harness.store.path, cfg).cursor == 0
        # Real CLI restart loads retained batch; duplicate does not make a second row.
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agentgate.telemetry_cli",
                "send",
                "--source",
                str(harness.store.path),
                "--config",
                str(config_path),
                "--token-file",
                str(token),
            ],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["acknowledged_through_sequence"] == 1
        assert len(received(db)) == 1
        assert load_state(harness.store.path, cfg).pending is None


def test_process_ownership_survives_contention_and_releases_on_kill(harness: Harness, tmp_path):
    token = token_file(tmp_path)
    cfg = TelemetryConfig(origin="http://127.0.0.1:12345", tenant="tenant-a")
    path = tmp_path / "config.json"
    path.write_text(cfg.model_dump_json())
    code = """import signal, sys
from pathlib import Path
from agentgate.telemetry import Sender
from agentgate.telemetry_contract import read_config
with Sender(Path(sys.argv[1]), read_config(Path(sys.argv[2])), Path(sys.argv[3])):
    print("owned", flush=True)
    signal.pause()
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(harness.store.path), str(path), str(token)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0]
        assert process.stdout.readline() == b"owned\n"
        with pytest.raises(SenderBusy), Sender(harness.store.path, cfg, token):
            pass
    finally:
        process.kill()
        process.communicate(timeout=5)
    with Sender(harness.store.path, cfg, token):
        pass


def test_collector_capacity_and_mixed_scope_batch_rollback(harness: Harness, tmp_path):
    harness.read()
    token = token_file(tmp_path)
    db = tmp_path / "collector.sqlite3"
    with live_server(create_collector(Collector(db, "tenant-a", max_rows=1), token)) as origin:
        cfg = TelemetryConfig(origin=origin, tenant="tenant-a", backlog_high_watermark=1)
        state = run_once(harness.store.path, cfg, token)
        assert state.cursor == 0 and received(db) == []  # Entire batch rolled back.
        assert telemetry_status(harness.store.path, cfg)["backpressure"] is True
        data = state.pending.model_dump(mode="json")
        data["events"][1]["tenant_id"] = "tenant-b"
        from agentgate.telemetry_contract import ProjectedEvent

        data["batch_id"] = batch_digest([ProjectedEvent.model_validate(e) for e in data["events"]])
        with httpx.Client(trust_env=False) as client:
            response = client.post(
                origin + "/v1/events",
                headers={"Authorization": "Bearer " + read_token(token)},
                json=data,
            )
        assert response.status_code == 409 and received(db) == []


def test_actual_disconnection_reconnect_and_unattributed_delivery(harness: Harness, tmp_path):
    import socket

    harness.read()
    harness.client.post("/v1/actions/execute", json={"tenant_id": "tenant-a"})
    token = token_file(tmp_path)
    db = tmp_path / "collector.sqlite3"
    collector = Collector(db, None)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
        cfg = TelemetryConfig(origin=f"http://127.0.0.1:{port}", tenant=None, timeout_seconds=0.2)
        state = run_once(harness.store.path, cfg, token)
        assert state.cursor == 0 and state.failures == 1 and received(db) == []
    with live_server(create_collector(collector, token), port=port):
        state = run_once(harness.store.path, cfg, token, now=2001.0)
        assert state.cursor == 3 and state.acknowledged_events == 1
        assert len(received(db)) == 1 and received(db)[0]["tenant_id"] is None


def test_live_collector_rejects_payload_overrides_and_id_conflicts(harness: Harness, tmp_path):
    harness.read("tenant-b-notes")
    token = token_file(tmp_path)
    db = tmp_path / "collector.sqlite3"
    with live_server(create_collector(Collector(db, "tenant-a"), token)) as origin:
        cfg = TelemetryConfig(origin=origin, tenant="tenant-a")
        with Sender(harness.store.path, cfg, token) as sender:
            pending = sender.stage(load_state(harness.store.path, cfg)).pending
        assert pending is not None
        headers = {"Authorization": "Bearer " + read_token(token)}
        with httpx.Client(trust_env=False, timeout=2) as client:
            oversized = client.post(
                origin + "/v1/events",
                headers={**headers, "Content-Type": "application/json"},
                content=b"x" * 262145,
            )
            assert oversized.status_code == 413 and received(db) == []
            data = pending.model_dump(mode="json")
            data["events"][0]["prompt"] = "synthetic-private-prompt"
            response = client.post(origin + "/v1/events", headers=headers, json=data)
            assert response.status_code == 422 and received(db) == []
            response = client.post(
                origin + "/v1/events?tenant=tenant-b",
                headers=headers,
                json=pending.model_dump(mode="json"),
            )
            assert response.status_code == 422 and received(db) == []
            response = client.post(
                origin + "/v1/events", headers=headers, json=pending.model_dump(mode="json")
            )
            assert response.status_code == 200 and len(received(db)) == 1
            changed = pending.events[0].model_copy(update={"decision": "allow"})
            response = client.post(
                origin + "/v1/events",
                headers=headers,
                json=Batch(batch_id=batch_digest([changed]), events=[changed]).model_dump(
                    mode="json"
                ),
            )
            assert response.status_code == 409 and received(db)[0]["decision"] == "deny"
    with pytest.raises(ValueError, match="scope"):
        Collector(db, "tenant-b")


def test_collector_cli_daemon_and_graceful_stop(harness: Harness, tmp_path):
    import socket
    import time

    token = token_file(tmp_path)
    db = tmp_path / "collector.sqlite3"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    cfg = TelemetryConfig(origin=f"http://127.0.0.1:{port}", tenant="tenant-a", poll_seconds=0.05)
    config_path = tmp_path / "sender.json"
    config_path.write_text(cfg.model_dump_json())
    collector = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agentgate.telemetry_cli",
            "collector",
            "--database",
            str(db),
            "--token-file",
            str(token),
            "--tenant",
            "tenant-a",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    sender = None
    try:
        deadline = time.monotonic() + 10
        with httpx.Client(trust_env=False, timeout=0.2) as client:
            while True:
                try:
                    if client.get(cfg.origin + "/health/live").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline and collector.poll() is None
                time.sleep(0.01)
        harness.read("tenant-b-notes")
        sender = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agentgate.telemetry_cli",
                "send",
                "--source",
                str(harness.store.path),
                "--config",
                str(config_path),
                "--token-file",
                str(token),
                "--daemon",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        while telemetry_status(harness.store.path, cfg)["acknowledged_through_sequence"] != 1:
            assert time.monotonic() < deadline and sender.poll() is None
            time.sleep(0.01)
        assert telemetry_status(harness.store.path, cfg)["sender_running"] is True
        sender.terminate()
        stdout, stderr = sender.communicate(timeout=5)
        assert sender.returncode == 0 and stderr == b""
        assert json.loads(stdout)["acknowledged_through_sequence"] == 1
        assert len(received(db)) == 1
        assert telemetry_status(harness.store.path, cfg)["sender_running"] is False
    finally:
        for process in (sender, collector):
            if process is not None and process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)


def test_collector_cannot_initialize_over_the_authoritative_audit(harness: Harness):
    with pytest.raises(ValueError, match="collector database"):
        Collector(harness.store.path, "tenant-a")
    with sqlite3.connect(harness.store.path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='received'").fetchall() == []
