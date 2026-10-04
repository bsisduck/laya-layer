"""Public local product lifecycle commands."""

import argparse
import json
import os
import platform
import subprocess
import time
from pathlib import Path

from agentgate.lifecycle.install import configuration, install, runtime, services, verify_ollama
from agentgate.lifecycle.processes import available_port, clean_environment, control, launch
from agentgate.lifecycle.state import LifecycleError, check_file, ownership


def main() -> None:
    parser = argparse.ArgumentParser(description="Laya Sec Layer local application lifecycle")
    parser.add_argument(
        "command",
        choices=[
            "install",
            "start",
            "status",
            "stop",
            "logs",
            "doctor",
            "renew-agent",
            "renew-playground",
        ],
    )
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/share/laya")
    parser.add_argument("--port", type=int)
    parser.add_argument("--proxy-port", type=int)
    parser.add_argument("--worker-port", type=int)
    parser.add_argument("--collector-port", type=int)
    parser.add_argument(
        "--local-console",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Install a trusted loopback console without credential entry (default: credential mode)",
    )
    parser.add_argument("--semantic", choices=["off", "standard", "coreml"])
    parser.add_argument("--question-set", choices=["content-role-v1", "content-role-v2"])
    parser.add_argument(
        "--offline", action="store_true", help="Install using only cached packages/assets"
    )
    parser.add_argument(
        "--no-start", action="store_true", help="Prepare installation without starting"
    )
    parser.add_argument(
        "--scope", choices=["tools", "model"], default="tools", help="Playground authority to renew"
    )
    args = parser.parse_args()
    state = args.state_dir.expanduser().absolute()
    root = Path(__file__).resolve().parents[3]
    os.umask(0o077)
    try:
        if args.local_console is not None and args.command != "install":
            raise LifecycleError("Local console mode can only be selected during install")
        if args.command == "install":
            saved = configuration(state) if state.exists() else {}
            args.port = args.port if args.port is not None else saved.get("port", 8080)
            args.proxy_port = (
                args.proxy_port if args.proxy_port is not None else saved.get("proxy_port", 4000)
            )
            args.worker_port = (
                args.worker_port if args.worker_port is not None else saved.get("worker_port", 8091)
            )
            args.collector_port = (
                args.collector_port
                if args.collector_port is not None
                else saved.get("collector_port", 8095)
            )
            args.semantic = args.semantic or saved.get("semantic", "off")
            args.question_set = args.question_set or saved.get("question_set", "content-role-v1")
            install(
                root,
                state,
                port=args.port,
                proxy_port=args.proxy_port,
                worker_port=args.worker_port,
                collector_port=args.collector_port,
                semantic=args.semantic,
                question_set=args.question_set,
                offline=args.offline,
                local_console=args.local_console,
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
            if configuration(state)["local_console"]:
                print("Local console / trusted computer: automatic bounded operator sessions.")
            else:
                print(f"Operator credential file: {state / 'data/operator.token'}")
            print(f"Agent credential file: {state / 'data/client.token'}")
        elif args.command == "status":
            settings = configuration(state)
            try:
                result = control(state, "status")
            except (FileNotFoundError, ConnectionRefusedError):
                with ownership(state):
                    result = {"status": "stopped", "services": {}}
                    for key in ("port", "proxy_port", "worker_port", "collector_port"):
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
        elif args.command in ("renew-agent", "renew-playground"):
            settings = configuration(state)
            with ownership(state):
                for key in ("port", "proxy_port", "worker_port", "collector_port"):
                    available_port(settings[key])
                scope = "agent" if args.command == "renew-agent" else args.scope
                result_code = subprocess.run(
                    [
                        str(runtime(state, "gateway") / "python"),
                        "-m",
                        "agentgate.lifecycle.renewal",
                        str(state / "data"),
                        scope,
                    ],
                    env=clean_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                ).returncode
                if result_code:
                    reason = {
                        4: "credential is still active",
                        5: "revoked credentials cannot be renewed",
                        6: "credential is missing or unissued",
                        8: "stale or conflicting renewal",
                    }.get(
                        result_code, "runtime hook or recovery unavailable; preserve private state"
                    )
                    raise LifecycleError(f"Renewal refused: {reason}")
            print(
                "Expired credential renewed with preserved identity and root budget; prior approvals remain invalid."
            )
            if args.command == "renew-agent":
                print(f"Agent credential file: {state / 'data/client.token'}")
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
            settings = configuration(state)
            if args.semantic is not None and args.semantic != settings["semantic"]:
                raise LifecycleError(
                    "Requested semantic backend is not prepared for this installation"
                )
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
