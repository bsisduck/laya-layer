"""Own one durable sender for the gateway lifespan, including MCP lifecycle."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from agentgate.telemetry import Sender
from agentgate.telemetry_contract import TelemetryConfig, read_token


def attach_sender(app: FastAPI, source: Path, config: TelemetryConfig, token_file: Path) -> None:
    read_token(token_file)
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        async with previous(application):
            with Sender(source, config, token_file) as sender:
                stop = asyncio.Event()
                task = asyncio.create_task(sender.run(stop))
                app.state.telemetry_task = task
                try:
                    yield
                finally:
                    stop.set()
                    try:
                        await asyncio.wait_for(task, timeout=config.timeout_seconds + 2)
                    except TimeoutError:
                        # Cancellation retains the pending batch and old cursor.
                        pass

    app.router.lifespan_context = lifespan
