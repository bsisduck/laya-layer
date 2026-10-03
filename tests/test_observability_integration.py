"""Actual gateway lifespan, HTTP collector, persisted acknowledgments and bounded timings."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from telemetry_http import live_server
from test_admin import ORIGIN
from test_admin import admin as admin
from test_gateway import harness as harness
from test_telemetry import token_file
from test_telemetry_http import received

from agentgate.app import create_app
from agentgate.metrics import LatencyWindow, ResponseTimings
from agentgate.telemetry import sender_running
from agentgate.telemetry_collector import Collector, create_collector
from agentgate.telemetry_contract import TelemetryConfig


def test_sender_lifespan_coexists_with_mcp_and_admin_and_survives_restart(admin, tmp_path):
    token = token_file(tmp_path)
    database = tmp_path / "received.sqlite3"
    with live_server(create_collector(Collector(database, "tenant-a"), token)) as origin:
        config = TelemetryConfig(origin=origin, tenant="tenant-a", poll_seconds=0.05)
        for attempt in range(2):
            app = create_app(
                admin.gateway.service,
                admin_origin=ORIGIN,
                enable_mcp=True,
                telemetry_config=config,
                telemetry_token_file=token,
            )
            with TestClient(app, base_url=ORIGIN) as client:
                assert client.get("/admin/overview").status_code == 401
                session = client.post(
                    "/admin/session", headers={"Origin": ORIGIN}, json={"token": admin.token}
                ).json()
                if attempt == 0:
                    response = client.post(
                        "/admin/playground",
                        headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]},
                        json={"mode": "document", "document_id": "tenant-a-notes"},
                    )
                    assert response.status_code == 200 and response.json()["executed"]
                deadline = time.monotonic() + 5
                while True:
                    report = client.get("/admin/overview").json()
                    delivery = report["telemetry"]
                    if delivery.get("acknowledged_events", 0) == 2:
                        break
                    assert time.monotonic() < deadline, delivery
                    time.sleep(0.02)
                assert delivery["sender_running"] is True
                assert delivery["source_lag_sequences"] == 0
                assert delivery["status"] == "idle"
                assert delivery["last_delivery_ms"] >= 0
                assert report["services"]["mcp"] == "configured"
                assert report["latency"]["count"] == (1 if attempt == 0 else 0)
                if attempt == 0:
                    assert report["latency"]["series"]["operator_playground"]["p95_ms"] > 0
                assert len(received(database)) == 2
                assert token.read_text() not in json.dumps(report)
            assert not sender_running(admin.gateway.store.path)
        assert len(received(database)) == 2  # Restart preserves cursor and acknowledgments.


def test_partial_telemetry_configuration_is_refused(harness, tmp_path):
    with pytest.raises(ValueError, match="together"):
        create_app(harness.service, telemetry_token_file=token_file(tmp_path))
    with pytest.raises(ValueError, match="together"):
        create_app(
            harness.service,
            telemetry_config=TelemetryConfig(origin="http://127.0.0.1:8095", tenant="tenant-a"),
        )


def test_timings_wait_for_final_body_and_exclude_disconnections():
    window = LatencyWindow()
    observed = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        observed.append(window.snapshot()["count"])

    async def chunked(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        assert window.snapshot()["count"] == 0
        await send({"type": "http.response.body", "body": b"last", "more_body": False})

    scope = {"type": "http", "method": "POST", "path": "/v1/chat/completions"}
    asyncio.run(ResponseTimings(chunked, window)(scope, receive, send))
    assert observed == [0, 0, 0]
    assert window.snapshot()["count"] == 1

    async def disconnected(scope, receive, send):
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        raise ConnectionError

    with pytest.raises(ConnectionError):
        asyncio.run(ResponseTimings(disconnected, window)(scope, receive, send))
    assert window.snapshot()["count"] == 1
    for value in range(1000):
        window.record("/v1/chat/completions", value)
        window.record("/v1/actions/arbitrary-private-id", value)
    for value in (-1, float("nan"), float("inf")):
        window.record("/v1/chat/completions", value)
    report = window.snapshot()
    assert report["count"] == 512
    assert report["series"] == {"model_completion": {"count": 512, "p50_ms": 743, "p95_ms": 974}}
    assert "arbitrary-private-id" not in json.dumps(report)
