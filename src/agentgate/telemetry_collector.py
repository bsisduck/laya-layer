"""Authenticated loopback contract lab with durable event-ID deduplication.

This is not Splunk HEC or an Elastic/OpenSearch vendor deployment.
"""

import os
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from agentgate.app import read_body
from agentgate.service import GateError
from agentgate.telemetry_contract import (
    MAX_BATCH_BYTES,
    Acknowledgment,
    Batch,
    decode_json,
    read_token,
)


class CollectorConflict(Exception):
    pass


class CollectorFull(Exception):
    pass


class Collector:
    def __init__(self, path: Path, tenant: str | None, *, max_rows: int = 100000) -> None:
        if not 1 <= max_rows <= 1000000:
            raise ValueError("Invalid collector capacity")
        self.path = path
        self.tenant = tenant
        self.max_rows = max_rows
        # Existing files are operator-owned. New stores start private before SQLite opens.
        with open(path, "ab", opener=lambda name, flags: os.open(name, flags, 0o600)):
            pass
        connection = sqlite3.connect(path, timeout=1)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS received ("
                "event_id TEXT PRIMARY KEY, record TEXT NOT NULL, received_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS scope (id INTEGER PRIMARY KEY CHECK(id=1), tenant TEXT)"
            )
            connection.execute("INSERT OR IGNORE INTO scope VALUES (1, ?)", (tenant,))
            if connection.execute("SELECT tenant FROM scope WHERE id=1").fetchone()[0] != tenant:
                raise ValueError("Collector scope changed")
            connection.commit()
        finally:
            connection.close()

    def accept(self, batch: Batch) -> Acknowledgment:
        if any(event.tenant_id != self.tenant for event in batch.events):
            raise CollectorConflict
        connection = sqlite3.connect(self.path, timeout=1)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("SELECT count(*) FROM received").fetchone()[0]
            for event in batch.events:
                record = event.model_dump_json()
                existing = connection.execute(
                    "SELECT record FROM received WHERE event_id=?", (event.event_id,)
                ).fetchone()
                if existing is not None:
                    if existing[0] != record:
                        raise CollectorConflict
                    continue
                if count >= self.max_rows:
                    raise CollectorFull
                connection.execute(
                    "INSERT INTO received(event_id, record, received_at) VALUES (?, ?, ?)",
                    (event.event_id, record, time.time()),
                )
                count += 1
            connection.commit()
            # Ack is constructed only AFTER the entire transaction is durable.
            return Acknowledgment(
                version=1,
                batch_id=batch.batch_id,
                accepted_event_ids=[event.event_id for event in batch.events],
            )
        finally:
            connection.close()


def create_collector(collector: Collector, token_file: Path) -> FastAPI:
    read_token(token_file)  # Fail startup with invalid/missing private credentials.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live", "kind": "local-contract-lab-v1"}

    @app.post("/v1/events")
    async def ingest(request: Request) -> JSONResponse:
        try:
            expected = "Bearer " + read_token(token_file)
            supplied = request.headers.get("authorization", "")
            if len(request.headers.getlist("authorization")) != 1 or not secrets.compare_digest(
                supplied.encode(), expected.encode()
            ):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
            if request.query_params:
                raise ValueError("Query overrides forbidden")
            body = await read_body(request, MAX_BATCH_BYTES, 5.0)
            batch = Batch.model_validate(decode_json(body))
            acknowledgment = await run_in_threadpool(collector.accept, batch)
            return JSONResponse(acknowledgment.model_dump(mode="json"))
        except CollectorConflict:
            return JSONResponse({"detail": "scope or replay conflict"}, status_code=409)
        except CollectorFull:
            return JSONResponse({"detail": "collector capacity exhausted"}, status_code=507)
        except GateError as error:
            return JSONResponse({"detail": "invalid request"}, status_code=error.status_code)
        except (ValueError, RecursionError):
            return JSONResponse({"detail": "invalid request"}, status_code=422)
        except (sqlite3.Error, OSError):
            return JSONResponse({"detail": "collector unavailable"}, status_code=503)

    return app
