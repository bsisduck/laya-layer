"""Reproducible synthetic HTTP contract lab; emits measurements, never credentials.

Run: uv run --locked python scripts/telemetry_benchmark.py --samples 100
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import secrets
import sqlite3
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from threading import Event, Thread

import httpx

from agentgate.app import create_app
from agentgate.contracts import Identity
from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
from agentgate.policy import Policy
from agentgate.service import ActionService
from agentgate.storage import Store
from agentgate.telemetry import Sender, telemetry_status
from agentgate.telemetry_collector import Collector, create_collector
from agentgate.telemetry_contract import TelemetryConfig

# Reuse repository-native ephemeral HTTP startup/teardown, with real TCP sockets.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from telemetry_http import live_server  # noqa: E402


def distribution(values):
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "p50_ms": round(statistics.median(ordered), 4),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 4),
        "max_ms": round(ordered[-1], 4),
    }


def measure(root, samples, warmup, enabled):
    directory = root / ("with-sender" if enabled else "without-sender")
    directory.mkdir(mode=0o700)
    store = Store(directory / "audit.sqlite3")
    store.initialize()
    token = store.issue(
        Identity(
            principal_id="bench",
            tenant_id="tenant-a",
            agent_id="bench",
            root_run_id="bench",
            roles=("analyst",),
            operations=("documents.read",),
        ),
        time.time() + 600,
    )
    documents = demo_documents()
    service = ActionService(
        store,
        Policy(policy_id="benchmark", revision=1),
        DocumentRegistry(documents),
        FixtureExecutor(documents),
        secrets.token_bytes(32),
    )
    token_path = directory / "collector.token"
    token_path.write_text(secrets.token_urlsafe(32))
    token_path.chmod(0o600)
    collector_path = directory / "collector.sqlite3"
    collector = Collector(collector_path, "tenant-a")
    stop = Event()
    worker_failures = []
    ack_ages = []
    batch_times = []
    with (
        live_server(create_collector(collector, token_path)) as origin,
        live_server(create_app(service)) as gateway,
    ):
        cfg = TelemetryConfig(origin=origin, tenant="tenant-a", poll_seconds=0.05)

        def background():
            async def work():
                with Sender(store.path, cfg, token_path) as sender:
                    acknowledged = 0
                    while not stop.is_set():
                        state = await sender.once()
                        if state.acknowledged_events > acknowledged:
                            ack_ages.append(state.last_event_age_ms)
                            batch_times.append(state.last_delivery_ms)
                            acknowledged = state.acknowledged_events
                        if state.last_error:
                            raise RuntimeError("Benchmark delivery failed")
                        await asyncio.sleep(cfg.poll_seconds)

            try:
                asyncio.run(work())
            except Exception:
                worker_failures.append("sender_failed")

        worker = Thread(target=background, daemon=True)
        if enabled:
            worker.start()
        latencies = []
        cold_ms = None
        failures = 0
        try:
            with httpx.Client(trust_env=False, timeout=5) as client:
                for index in range(samples + warmup):
                    start = time.perf_counter()
                    result = client.post(
                        gateway + "/v1/actions/execute",
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "operation": "documents.read",
                            "arguments": {"document_id": "tenant-a-notes"},
                        },
                    )
                    elapsed = (time.perf_counter() - start) * 1000
                    if index == 0:
                        cold_ms = elapsed
                    if result.status_code != 200 or result.json().get("decision") != "allow":
                        failures += 1
                    if index >= warmup:
                        latencies.append(elapsed)
            if enabled:
                deadline = time.monotonic() + 10
                while telemetry_status(store.path, cfg).get("source_lag_sequences") != 0:
                    if time.monotonic() > deadline or worker_failures:
                        raise RuntimeError("Benchmark did not drain")
                    stop.wait(0.01)
        finally:
            stop.set()
            if enabled:
                worker.join(10)
                if worker.is_alive() or worker_failures:
                    raise RuntimeError("Benchmark sender did not stop cleanly")
        status = telemetry_status(store.path, cfg)
    with sqlite3.connect(collector_path) as db:
        rows = db.execute("SELECT record, received_at FROM received").fetchall()
    expected = 2 * (samples + warmup) if enabled else 0
    if failures or len(rows) != expected:
        raise RuntimeError("Benchmark request or collector count mismatch")
    ages = [
        (received_at - datetime.fromisoformat(json.loads(record)["timestamp"]).timestamp()) * 1000
        for record, received_at in rows
    ]
    return {
        "gateway_http": distribution(latencies),
        "cold_first_request_ms": round(cold_ms, 4),
        "request_failures": failures,
        "collector_rows": len(rows),
        "source_events": 2 * (samples + warmup),
        "delivery_source_to_insert": distribution(ages) if ages else None,
        "delivery_latest_event_to_ack": distribution(ack_ages) if ack_ages else None,
        "sender_batch_wall_time": distribution(batch_times) if batch_times else None,
        "status": status,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    args = parser.parse_args()
    if not 10 <= args.samples <= 10000 or not 1 <= args.warmup <= 1000:
        parser.error("Use 10..10000 samples and 1..1000 warmups")
    documents = demo_documents()
    executor = FixtureExecutor(documents)
    direct = []
    for index in range(args.samples + args.warmup):
        start = time.perf_counter()
        executor.read("tenant-a-notes", "tenant-a")
        elapsed = (time.perf_counter() - start) * 1000
        if index >= args.warmup:
            direct.append(elapsed)
    with tempfile.TemporaryDirectory(prefix="laya-telemetry-benchmark-") as name:
        root = Path(name)
        disabled = measure(root, args.samples, args.warmup, False)
        enabled = measure(root, args.samples, args.warmup, True)
    base = distribution(direct)
    report = {
        "measured_at": datetime.now(UTC).isoformat(),
        "source_sha256": hashlib.sha256(
            b"".join(
                p.read_bytes()
                for p in sorted(
                    (Path(__file__).resolve().parents[1] / "src/agentgate").glob("*.py")
                )
            )
        ).hexdigest(),
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
            "httpx": version("httpx"),
            "uvicorn": version("uvicorn"),
        },
        "workload": {
            "samples_per_mode": args.samples,
            "warmups_per_mode": args.warmup,
            "concurrency": 1,
            "semantic": "disabled; no model/checkpoint/tokenization",
            "operation": "documents.read tenant-a-notes",
            "order": ["direct", "gateway_without_sender", "gateway_with_sender"],
            "poll_seconds": 0.05,
            "batch_max_events": 100,
        },
        "direct_fixture": base,
        "without_sender": disabled,
        "with_sender": enabled,
        "gateway_minus_direct_ms": {
            key: round(disabled["gateway_http"][key] - base[key], 4) for key in ("p50_ms", "p95_ms")
        },
        "sender_enabled_minus_disabled_ms": {
            key: round(enabled["gateway_http"][key] - disabled["gateway_http"][key], 4)
            for key in ("p50_ms", "p95_ms")
        },
        "limits": "Sequential local microbenchmark; deltas are distribution differences, not paired causal estimates. Gateway includes loopback HTTP, controls and SQLite audit. Delivery includes warmups; insert timestamps precede SQLite commit; latest-event-to-ack samples include durable collector acknowledgment, one per batch. No semantic inference, model performance, vendor or bank deployment measured.",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
