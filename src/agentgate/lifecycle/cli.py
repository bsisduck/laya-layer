"""Public local product lifecycle commands."""

import argparse
import json
import os
import platform
import time
from pathlib import Path

from agentgate.lifecycle.install import configuration, install, services, verify_ollama
from agentgate.lifecycle.processes import available_port, control, launch
from agentgate.lifecycle.state import LifecycleError, check_file, ownership


def main() -> None:
    parser = argparse.ArgumentParser(description="Laya Sec Layer local application lifecycle")
    parser.add_argument("command", choices=["install", "start", "status", "stop", "logs", "doctor"])
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/share/laya")
    parser.add_argument("--port", type=int)
    parser.add_argument("--proxy-port", type=int)
    parser.add_argument("--worker-port", type=int)
    parser.add_argument("--semantic", choices=["off", "standard", "coreml"])
    parser.add_argument(
        "--offline", action="store_true", help="Install using only cached packages/assets"
    )
    parser.add_argument(
        "--no-start", action="store_true", help="Prepare installation without starting"
    )
    args = parser.parse_args()
    state = args.state_dir.expanduser().absolute()
    root = Path(__file__).resolve().parents[3]
    os.umask(0o077)
    try:
        if args.command == "install":
            saved = configuration(state) if state.exists() else {}
            args.port = args.port if args.port is not None else saved.get("port", 8080)
            args.proxy_port = (
                args.proxy_port if args.proxy_port is not None else saved.get("proxy_port", 4000)
            )
            args.worker_port = (
                args.worker_port if args.worker_port is not None else saved.get("worker_port", 8091)
            )
            args.semantic = args.semantic or saved.get("semantic", "off")
            install(
                root,
                state,
                port=args.port,
                proxy_port=args.proxy_port,
                worker_port=args.worker_port,
                semantic=args.semantic,
                offline=args.offline,
            )
            if args.no_start:
                print("Installation prepared; run ./laya start with the same state directory.")
                return
            args.command = "start"
        if args.command == "start":
            configured = services(state)
            verify_ollama()
            result = launch(state, configured)
            print(json.dumps(result))
            print(f"Open http://127.0.0.1:{configuration(state)['port']}/")
            print(f"Operator credential file: {state / 'data/operator.token'}")
            print(f"Agent credential file: {state / 'data/client.token'}")
        elif args.command == "status":
            settings = configuration(state)
            try:
                result = control(state, "status")
            except (FileNotFoundError, ConnectionRefusedError):
                with ownership(state):
                    result = {"status": "stopped", "services": {}}
                    for key in ("port", "proxy_port", "worker_port"):
                        available_port(settings[key])
            if result["status"] == "running":
                try:
                    verify_ollama()
                    result["services"]["ollama_shared"] = "ready"
                except LifecycleError:
                    result["services"]["ollama_shared"] = "unavailable"
            print(json.dumps(result))
            if result["status"] != "running" or any(
                v != "ready" for v in result["services"].values()
            ):
                raise SystemExit(1)
        elif args.command == "stop":
            configuration(state)
            try:
                control(state, "stop")
            except (FileNotFoundError, ConnectionRefusedError):
                with ownership(state):
                    print("Already stopped; no processes signalled.")
                    return
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    with ownership(state):
                        print(
                            "Stopped owned services; shared Ollama and other listeners untouched."
                        )
                        return
                except LifecycleError:
                    time.sleep(0.1)
            raise LifecycleError("Stop still pending; no PID-based fallback is permitted")
        elif args.command == "logs":
            configuration(state)
            path = state / "lifecycle.log"
            check_file(path)
            print("".join(path.read_text().splitlines(keepends=True)[-100:]), end="")
        elif args.command == "doctor":
            print(
                f"Host: {platform.system()} {platform.machine()}; Python {platform.python_version()}"
            )
            print("CoreML: native Apple Silicon only; real semantic evaluation is separate")
            if args.semantic == "coreml" and (
                platform.system() != "Darwin" or platform.machine() != "arm64"
            ):
                raise LifecycleError("CoreML unsupported: requires native Apple Silicon macOS")
            configuration(state)
            configured = services(state)
            for service in configured:
                if not Path(service.command[0]).is_file():
                    raise LifecycleError(f"{service.name} runtime unavailable; rerun install")
            verify_ollama()
            print(
                "Prepared runtimes and pinned local Ollama model available; run status for live readiness."
            )
    except (LifecycleError, OSError, ValueError) as error:
        message = (
            str(error)
            if isinstance(error, LifecycleError)
            else "State or service unavailable; inspect permissions and preserved state"
        )
        parser.exit(1, f"Laya: {message}\n")


if __name__ == "__main__":
    main()
