"""Local operator lifecycle; credentials are file references, never command values."""

import argparse
import asyncio
import json
import signal
import sqlite3
from pathlib import Path

import uvicorn

from agentgate.telemetry import Sender, SenderBusy, telemetry_status
from agentgate.telemetry_collector import Collector, create_collector
from agentgate.telemetry_contract import read_config


async def daemon(sender: Sender) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await sender.run(stop)
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Laya telemetry local operator tools")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("send", "status"):
        command = commands.add_parser(name)
        command.add_argument("--source", type=Path, required=True)
        command.add_argument("--config", type=Path, required=True)
        if name == "send":
            command.add_argument("--token-file", type=Path, required=True)
            command.add_argument("--daemon", action="store_true", help="Retry until SIGINT/SIGTERM")
    collector = commands.add_parser(
        "collector", help="Run the loopback contract lab (not a vendor server)"
    )
    collector.add_argument("--database", type=Path, required=True)
    collector.add_argument("--token-file", type=Path, required=True)
    scope = collector.add_mutually_exclusive_group(required=True)
    scope.add_argument("--tenant")
    scope.add_argument("--unattributed", action="store_true")
    collector.add_argument("--port", type=int, default=8095)
    collector.add_argument("--max-rows", type=int, default=100000)
    args = parser.parse_args()
    try:
        if args.command == "collector":
            app = create_collector(
                Collector(args.database, args.tenant, max_rows=args.max_rows), args.token_file
            )
            uvicorn.run(
                app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning"
            )
            return
        config = read_config(args.config)
        if args.command == "send":
            with Sender(args.source, config, args.token_file) as sender:
                if args.daemon:
                    asyncio.run(daemon(sender))
                else:
                    state = asyncio.run(sender.once())
                    print(json.dumps(telemetry_status(args.source, config)))
                    if state.last_error:
                        raise SystemExit(1)
                    return
        print(json.dumps(telemetry_status(args.source, config)))
    except SenderBusy:
        parser.exit(1, "Telemetry sender already owns this source.\n")
    except (OSError, ValueError, sqlite3.Error, RecursionError):
        parser.exit(
            1, "Telemetry unavailable. Check private files, source, configuration and collector.\n"
        )


if __name__ == "__main__":
    main()
