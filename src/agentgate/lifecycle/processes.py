"""A local supervisor signals only unreaped Popen children, never recorded PIDs.

The control socket authenticates a random installation secret. Saved PIDs are
observations only. A stale/corrupt manifest never grants permission to kill.
"""

import hashlib
import hmac
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agentgate.lifecycle.state import (
    LifecycleError,
    check_file,
    ownership,
    private_dir,
    read_json,
    save_json,
    write_new,
)


@dataclass(frozen=True)
class Service:
    name: str
    command: list[str]
    port: int
    health_path: str
    token_file: str | None = None


def clean_environment() -> dict[str, str]:
    # No inherited cloud keys, proxy variables, PYTHONPATH, tracing or user dotenv.
    env = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "LANG") if key in os.environ}
    env.update(
        PYTHONUNBUFFERED="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        DO_NOT_TRACK="1",
    )
    return env


def http_json(url: str, token: str | None = None, *, timeout: float = 1) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers)

    # Proxies and redirects must never turn local credential probes into remote requests.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        data = response.read(65537)
        if len(data) > 65536:
            raise ValueError("Oversized health response")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("Invalid health response")
        return result


def healthy(service: Service) -> bool:
    try:
        token = None
        if service.token_file:
            check_file(Path(service.token_file))
            token = Path(service.token_file).read_text().strip()
        result = http_json(f"http://127.0.0.1:{service.port}{service.health_path}", token)
        if service.name == "gateway":
            return result.get("status") == "ready"
        if service.name == "litellm":
            return any(row.get("id") == "local-demo" for row in result.get("data", []))
        return result.get("backend") in ("laya_standard", "laya_coreml")
    except (OSError, ValueError, LifecycleError):
        return False


def available_port(port: int) -> None:
    if not 1024 <= port <= 65535:
        raise LifecycleError("Ports must be between 1024 and 65535")
    try:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
    except OSError as error:
        raise LifecycleError(
            f"Port {port} is occupied; leave its owner running and choose another port"
        ) from error


def socket_directory(state: Path) -> Path:
    # macOS sockaddr_un has a short pathname limit; never put sockets under long checkouts.
    suffix = hashlib.sha256(str(state).encode()).hexdigest()[:20]
    return Path("/tmp").resolve() / f"laya-{os.getuid()}-{suffix}"


def control(state: Path, command: str) -> dict[str, Any]:
    private_dir(state)
    check_file(state / "control.key")
    directory = socket_directory(state)
    private_dir(directory)
    path = directory / "control.sock"
    info = path.lstat()
    import stat

    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise LifecycleError("Unsafe lifecycle socket")
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(5)
        client.connect(str(path))
        client.sendall(
            json.dumps({"key": (state / "control.key").read_text(), "command": command}).encode()
            + b"\n"
        )
        response = bytearray()
        while b"\n" not in response and len(response) <= 65536:
            part = client.recv(4096)
            if not part:
                break
            response.extend(part)
        if not response:
            raise ConnectionResetError("Lifecycle owner exited")
        result = json.loads(response)
        if not isinstance(result, dict) or result.get("installation") != str(state):
            raise LifecycleError("Unexpected lifecycle owner")
        return result


def record(state: Path, message: str) -> None:
    # Only fixed lifecycle diagnostics, never upstream stdout, headers or request bodies.
    path = state / "lifecycle.log"
    if not path.exists():
        write_new(path, b"")
    check_file(path)
    if path.stat().st_size > 131072:
        backup = state / "lifecycle.previous.log"
        if backup.exists():
            check_file(backup)
        os.replace(path, backup)
        write_new(path, b"")
    with path.open("a") as stream:
        stream.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {message}\n")


def stop_children(children: list[subprocess.Popen[bytes]]) -> None:
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 8
    for child in reversed(children):
        try:
            child.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            # An unreaped direct child cannot have its PID reused by the OS.
            child.kill()
            child.wait(timeout=3)


def supervise(state: Path, services: list[Service], timeout: float) -> None:
    os.umask(0o077)
    children: list[subprocess.Popen[bytes]] = []
    stopping = False

    def request_stop(signum: int, frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    with ownership(state):
        directory = socket_directory(state)
        private_dir(directory, create=True)
        address = directory / "control.sock"
        if address.exists() or address.is_symlink():
            import stat

            if not stat.S_ISSOCK(address.lstat().st_mode):
                raise LifecycleError("Refusing to overwrite a non-socket lifecycle path")
            address.unlink()
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(address))
            os.chmod(address, 0o600)
            server.listen(4)
            server.settimeout(0.2)
            try:
                for service in services:
                    available_port(service.port)
                env = clean_environment()
                if (state / "data/litellm.token").exists():
                    check_file(state / "data/litellm.token")
                    env["LITELLM_MASTER_KEY"] = (state / "data/litellm.token").read_text().strip()
                for service in services:
                    if stopping:
                        raise LifecycleError("Startup interrupted")
                    child = subprocess.Popen(
                        service.command,
                        cwd=state,
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    children.append(child)
                    record(state, f"{service.name} started")
                    deadline = time.monotonic() + timeout
                    while not healthy(service):
                        if stopping or child.poll() is not None or time.monotonic() >= deadline:
                            raise LifecycleError(
                                f"{service.name} failed readiness; owned children rolled back"
                            )
                        time.sleep(0.1)
                save_json(
                    state / "processes.json",
                    {
                        "supervisor_pid": os.getpid(),
                        "children": [c.pid for c in children],
                        "services": [asdict(s) for s in services],
                    },
                )
                record(state, "Application ready")
                while not stopping:
                    if any(child.poll() is not None for child in children):
                        raise LifecycleError(
                            "Owned service exited; stopping the remaining owned children"
                        )
                    try:
                        client, _ = server.accept()
                    except TimeoutError:
                        continue
                    with client:
                        client.settimeout(1)
                        try:
                            raw = client.recv(4096)
                            body = json.loads(raw)
                            if not hmac.compare_digest(
                                str(body.get("key", "")), (state / "control.key").read_text()
                            ):
                                continue
                            command = body.get("command")
                            if command not in ("status", "stop"):
                                continue
                            states = {
                                s.name: "ready" if healthy(s) else "unavailable" for s in services
                            }
                            stopping = command == "stop"
                            result = {
                                "installation": str(state),
                                "status": "stopping" if stopping else "running",
                                "services": states,
                            }
                            client.sendall(json.dumps(result).encode() + b"\n")
                        except (OSError, ValueError, AttributeError):
                            continue
            except LifecycleError as error:
                record(state, str(error))
            finally:
                stop_children(children)
                record(state, "Application stopped; shared services untouched")
                address.unlink(missing_ok=True)


def launch(state: Path, services: list[Service], timeout: float = 60) -> dict[str, Any]:
    try:
        return control(state, "status")
    except (FileNotFoundError, ConnectionRefusedError):
        pass
    with ownership(state):
        for service in services:
            available_port(service.port)
        save_json(
            state / "launch.json", {"services": [asdict(s) for s in services], "timeout": timeout}
        )
    command = [sys.executable, str(Path(__file__).resolve()), str(state)]
    process = subprocess.Popen(
        command,
        cwd=state,
        env=clean_environment(),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout * len(services) + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LifecycleError(
                "Startup failed. Read ./laya logs; existing services were not taken over"
            )
        try:
            result = control(state, "status")
            return result
        except (FileNotFoundError, ConnectionRefusedError, ConnectionResetError, TimeoutError):
            time.sleep(0.1)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=15)
    raise LifecycleError("Startup timed out; owned services stopped")


if __name__ == "__main__":
    # The source launcher also works before the application wheel is installed.
    state_path = Path(sys.argv[1])
    launch_data = read_json(state_path / "launch.json")
    supervise(state_path, [Service(**s) for s in launch_data["services"]], launch_data["timeout"])
