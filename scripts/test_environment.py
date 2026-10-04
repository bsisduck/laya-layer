"""Reusable QA installation using the product's own ownership, cache and lifecycle."""

import argparse
import fcntl
import hashlib
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / ".ai/qa"
STATE = ROOT / ".runtime/qa-install"
DESCRIPTOR = QA / "test-env.json"
sys.path.insert(0, str(ROOT / "src"))


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def fingerprint():
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    digest = hashlib.sha256()
    newest = 0
    for name in sorted(filter(None, files)):
        path = ROOT / os.fsdecode(name)
        if path.is_file():
            digest.update(name)
            digest.update(path.read_bytes())
            newest = max(newest, path.stat().st_mtime)
    return digest.hexdigest(), newest


def product(command, *args, quiet=False):
    subprocess.run(
        [str(ROOT / "laya"), command, "--state-dir", str(STATE), *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL if quiet else None,
        timeout=1000,
    )


def deep_probe(base):
    # Only this isolated QA installation's generated operator credential is used.
    from agentgate.lifecycle.processes import deadline

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(CookieJar()))

    def request(path, method="GET", body=None, csrf=None):
        headers = {"Origin": base, "Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        req = Request(
            base + path,
            method=method,
            headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        with deadline(5), opener.open(req, timeout=5) as response:
            content = response.read(1048577)
            if len(content) > 1048576:
                raise ValueError("QA probe response exceeded bound")
            return json.loads(content)

    assert request("/health/ready")["status"] == "ready"
    mode = request("/admin/config")["mode"]
    session = (
        request("/admin/session/bootstrap", "POST", {})
        if mode == "local"
        else request(
            "/admin/session", "POST", {"token": (STATE / "data/operator.token").read_text().strip()}
        )
    )
    try:
        overview = request("/admin/overview")
        assert overview["services"]["gateway"] == "ready"
        assert overview["services"]["scoped_tools"] == "ready"
    finally:
        request("/admin/session", "DELETE", csrf=session["csrf_token"])


def browser_state(previous):
    if previous.get("installed") and Path(previous.get("command", "")).is_file():
        return previous
    binary = shutil.which("agent-browser")
    if not binary and platform.system() == "Darwin" and platform.machine() == "arm64":
        cached = Path.home() / ".cache/agent-tools/agent-browser/v0.35.2/agent-browser-darwin-arm64"
        if (
            cached.is_file()
            and hashlib.sha256(cached.read_bytes()).hexdigest()
            == "e1e08f3b0a1c711750209e6a25b6f3a9dab7ed6e6a24b55a2556050b991fcc97"
        ):
            binary = str(cached)
    available = False
    if binary:
        result = subprocess.run([binary, "doctor", "--json"], capture_output=True, timeout=30)
        available = result.returncode == 0
    return {
        "provider": "agent-browser",
        "installed": available,
        "command": binary or "",
        "descriptor": ".ai/browsers/agent-browser.md",
        "notes": "Local provider verified by doctor"
        if available
        else "Run provider ensure-installed from its descriptor; API QA remains available",
    }


def main():
    from agentgate.lifecycle.install import configuration
    from agentgate.lifecycle.processes import control
    from agentgate.lifecycle.state import read_json, save_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "down"))
    parser.add_argument("--local-console", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    QA.mkdir(parents=True, exist_ok=True)
    # A separate OS lock prevents bootstrap races; product ownership still controls services.
    lock_dir = QA / "test-env.lock"
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    with (lock_dir / "bootstrap.lock").open("a") as lock:
        until = time.monotonic() + 180
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= until:
                    raise RuntimeError("Another QA bootstrap is still running") from None
                time.sleep(0.2)
        save(
            lock_dir / "owner.json",
            {"pid": os.getpid(), "source": str(ROOT), "acquiredAt": time.time()},
        )
        try:
            previous = json.loads(DESCRIPTOR.read_bytes()) if DESCRIPTOR.exists() else {}
            if previous and previous.get("source") != str(ROOT):
                raise RuntimeError("QA descriptor belongs to another checkout; refusing adoption")
            if args.command == "down":
                if STATE.exists():
                    product("stop")
                previous.update(status="stopped", source=str(ROOT))
                save(DESCRIPTOR, previous)
                print("TEST_ENV_STATUS=stopped")
                return
            started = time.monotonic()
            digest, modified = fingerprint()
            running = False
            if STATE.exists():
                configuration(STATE)
                try:
                    report = control(STATE, "status")
                    running = report["status"] == "running" and all(
                        v == "ready" for v in report["services"].values()
                    )
                except (FileNotFoundError, ConnectionRefusedError):
                    pass
            ttl = int(os.environ.get("TEST_ENV_CACHE_TTL_SECONDS", "600"))
            reusable = (
                running
                and previous.get("fingerprint") == digest
                and modified <= previous.get("startedEpoch", 0)
                and 0 <= time.time() - previous.get("startedEpoch", 0) <= ttl
                and (
                    args.local_console is None
                    or configuration(STATE)["local_console"] == args.local_console
                )
                and not args.force
                and not args.force_rebuild
            )
            if reusable:
                try:
                    os.kill(read_json(STATE / "processes.json")["supervisor_pid"], 0)
                    deep_probe(previous["baseUrl"])
                except (OSError, ValueError, AssertionError):
                    reusable = False
            if reusable:
                descriptor = previous
            else:
                if running:
                    product("stop", quiet=True)
                options = []
                if args.local_console is not None:
                    options.append(
                        "--local-console" if args.local_console else "--no-local-console"
                    )
                if not STATE.exists():
                    with ExitStack() as stack:
                        sockets = [stack.enter_context(socket.socket()) for _ in range(4)]
                        for sock in sockets:
                            sock.bind(("127.0.0.1", 0))
                        for flag, sock in zip(
                            ("--port", "--proxy-port", "--worker-port", "--collector-port"),
                            sockets,
                            strict=True,
                        ):
                            options.extend((flag, str(sock.getsockname()[1])))
                # The product's content fingerprint owns wheel/dependency reuse and migration.
                # Invalidate only the stopped QA install's preparation cache, never authority.
                if args.force_rebuild and STATE.exists():
                    settings = configuration(STATE)
                    settings["source_fingerprint"] = None
                    save_json(STATE / "installation.json", settings)
                product("install", *options)
                settings = configuration(STATE)
                base = f"http://127.0.0.1:{settings['port']}"
                deep_probe(base)
                processes = read_json(STATE / "processes.json")
                os.kill(processes["supervisor_pid"], 0)  # Liveness only; never signal a saved PID.
                descriptor = {
                    "version": 1,
                    "runId": secrets.token_hex(6),
                    "source": str(ROOT),
                    "status": "running",
                    "mode": "discovered",
                    "consoleMode": "local" if settings["local_console"] else "credential",
                    "baseUrl": base,
                    "startedByThisRepo": True,
                    "startScript": ".ai/scripts/test-env-up.sh",
                    "stopScript": ".ai/scripts/test-env-down.sh",
                    "stateDir": str(STATE),
                    "app": {
                        "pid": processes["supervisor_pid"],
                        "port": settings["port"],
                        "healthPath": "/health/ready",
                        "startCommand": "./laya install",
                    },
                    "services": [{"type": "ollama", "ownership": "shared; never stopped"}],
                    "credentials": [
                        {
                            "role": "admin",
                            "username": "operator",
                            "passwordEnv": "TEST_ADMIN_PASSWORD",
                        }
                    ],
                    "credentialsFile": ".ai/qa/test-env.env",
                    "browser": browser_state(previous.get("browser", {})),
                    "testRunner": {"name": "playwright", "config": "tests/frontend"},
                    "platform": platform.system().lower(),
                    "startedAt": datetime.now(UTC).isoformat(),
                    "startedEpoch": time.time(),
                    "fingerprint": digest,
                    "notes": "Uses product install/cache/ownership. Shared Ollama is prepared separately. Semantic evaluation runs separately. No manual server boot needed.",
                }
                if settings["local_console"]:
                    descriptor["credentials"] = []
                    descriptor.pop("credentialsFile", None)
                else:
                    token = (STATE / "data/operator.token").read_text().strip()
                    if not token.replace("_", "").replace("-", "").isalnum():
                        raise ValueError("Invalid QA credential format")
                    save(QA / "test-env.env", f"TEST_ADMIN_PASSWORD='{token}'\n")
            descriptor["lastBootstrapSeconds"] = round(time.monotonic() - started, 3)
            descriptor["lastBootstrapReused"] = reusable
            save(DESCRIPTOR, descriptor)
            save(
                QA / "test-env-build-cache.json",
                {
                    "fingerprint": digest,
                    "source": str(ROOT),
                    "artifact": str(STATE / "runtime/gateway/bin/agentgate"),
                },
            )
            print("TEST_ENV_STATUS=running")
            print("TEST_ENV_BASE_URL=" + descriptor["baseUrl"])
            print("TEST_ENV_DESCRIPTOR=.ai/qa/test-env.json")
            print(f"TEST_ENV_REUSED={int(reusable)}")
            print("BROWSER_PROVIDER=agent-browser")
            print(f"BROWSER_INSTALLED={int(descriptor['browser']['installed'])}")
        finally:
            (lock_dir / "owner.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
