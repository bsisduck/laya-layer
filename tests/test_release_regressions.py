"""Independent-review regressions for embedding and live collector reconfiguration."""

import asyncio
import json
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from telemetry_http import live_server
from test_admin import ORIGIN
from test_admin import admin as admin
from test_gateway import harness as harness
from test_telemetry_http import received

from agentgate.admin import attach_admin_routes
from agentgate.lifecycle.provision import configure_telemetry
from agentgate.lifecycle.state import private_dir
from agentgate.storage import Store
from agentgate.telemetry import Sender, SenderBusy, load_state, post_batch, telemetry_status
from agentgate.telemetry_collector import Collector, create_collector
from agentgate.telemetry_contract import read_config


def test_standalone_admin_attachment_keeps_unknown_observability_honest(admin):
    app = FastAPI()
    attach_admin_routes(app, admin.gateway.service, origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/admin/overview").status_code == 401
        login = client.post(
            "/admin/session", headers={"Origin": ORIGIN}, json={"token": admin.token}
        )
        assert login.status_code == 200
        result = client.get("/admin/overview")
        assert result.status_code == 200
        assert result.json()["telemetry"] == {"enabled": False, "status": "not_configured"}
        assert result.json()["latency"]["status"] == "not_observed"


def test_collector_port_migration_preserves_lost_ack_batch_and_continues_delivery(
    harness, tmp_path, monkeypatch
):
    data = tmp_path / "installation"
    private_dir(data, create=True)
    store = Store(data / "agentgate.sqlite3")
    store.initialize()
    harness.read()
    original = harness.store.events()
    for event in original:
        store.append(event)
    collector = Collector(data / "collector.sqlite3", "tenant-a")
    configure_telemetry(data, 8095, 8095)
    token = data / "collector.token"
    with live_server(create_collector(collector, token)) as old_origin:
        old_port = urlsplit(old_origin).port
        configure_telemetry(data, 8095, old_port)
        config = read_config(data / "telemetry.json").model_copy(update={"batch_events": 1})
        (data / "telemetry.json").write_text(config.model_dump_json())
        with Sender(store.path, config, token, clock=lambda: 2000) as sender:
            delivered = asyncio.run(sender.once())
        assert delivered.cursor == delivered.acknowledged_events == 1

        async def lost_ack(config, token, batch):
            await post_batch(config, token, batch)
            raise ValueError("synthetic lost acknowledgment after durable ingestion")

        with monkeypatch.context() as patch:
            patch.setattr("agentgate.telemetry.post_batch", lost_ack)
            with Sender(store.path, config, token, clock=lambda: 2000) as sender:
                pending = asyncio.run(sender.once())
        assert pending.cursor == 1 and pending.pending is not None
        assert len(received(collector.path)) == 2
    before = pending.model_dump(exclude={"binding"})
    with live_server(create_collector(collector, token)) as new_origin:
        new_port = urlsplit(new_origin).port
        assert new_port != old_port
        from agentgate.lifecycle import provision

        save = provision.save_json

        def interrupted(path, value):
            if path == data / "telemetry.json":
                raise OSError("synthetic interruption after checkpoint publication")
            return save(path, value)

        with monkeypatch.context() as patch:
            patch.setattr(provision, "save_json", interrupted)
            with pytest.raises(OSError, match="synthetic interruption"):
                configure_telemetry(data, old_port, new_port)
        assert read_config(data / "telemetry.json").origin == old_origin
        configure_telemetry(data, old_port, new_port)
        changed = read_config(data / "telemetry.json")
        assert load_state(store.path, changed).model_dump(exclude={"binding"}) == before
        # Retry the same pending batch at the new port; the same collector deduplicates it.
        with Sender(store.path, changed, token, clock=lambda: 2002) as sender:
            finished = asyncio.run(sender.once())
        assert finished.cursor == finished.acknowledged_events == 2
        assert finished.pending is None and len(received(collector.path)) == 2
        harness.read("tenant-a-contact")
        known = {e.event_id for e in original}
        for event in harness.store.events():
            if event.event_id not in known:
                store.append(event)
        with Sender(store.path, changed, token, clock=lambda: 2003) as sender:
            asyncio.run(sender.once())
            finished = asyncio.run(sender.once())
        assert finished.acknowledged_events == 4 and len(received(collector.path)) == 4
        assert telemetry_status(store.path, changed)["source_lag_sequences"] == 0
        # Idempotent recovery after a config/checkpoint publication interruption.
        configure_telemetry(data, old_port, new_port)
        assert load_state(store.path, changed) == finished
        saved_config = (data / "telemetry.json").read_bytes()
        saved_checkpoint = store.path.with_suffix(".telemetry.json").read_bytes()
        with Sender(store.path, changed, token):
            with pytest.raises(SenderBusy):
                configure_telemetry(data, new_port, old_port)
        assert (data / "telemetry.json").read_bytes() == saved_config
        assert store.path.with_suffix(".telemetry.json").read_bytes() == saved_checkpoint
    assert "synthetic lost acknowledgment" not in json.dumps(finished.model_dump())
