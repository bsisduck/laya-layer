"""Actual subprocess/HTTP lifecycle checks, never model-evaluation substitutes."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentgate.lifecycle.install import configuration, verify_ollama
from agentgate.lifecycle.processes import Service, control, http_json, launch, socket_directory
from agentgate.lifecycle.state import LifecycleError, ownership, private_dir, save_json, write_new


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "private"
    private_dir(path, create=True)
    write_new(path / "control.key", secrets.token_bytes(32).hex().encode())
    save_json(
        path / "installation.json",
        {
            "version": 1,
            "state": str(path),
            "semantic": "off",
            "port": 8080,
            "proxy_port": 4000,
            "worker_port": 8091,
        },
    )
    yield path
    try:
        control(path, "stop")
        wait_stopped(path)
    except (FileNotFoundError, ConnectionRefusedError):
        pass
    directory = socket_directory(path)
    if directory.exists():
        directory.rmdir()


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def fixture_service(tmp_path, name="gateway", *, exit_early=False, port=None):
    port = port or free_port()
    script = tmp_path / f"{name}.py"
    script.write_text(
        "import json, os\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "from pathlib import Path\n"
        "Path(__file__+'.pid').write_text(str(os.getpid()))\n"
        + ("raise SystemExit(4)\n" if exit_early else "")
        + "class Handler(BaseHTTPRequestHandler):\n"
        " def do_GET(self):\n"
        '  self.send_response(200); self.end_headers(); self.wfile.write(b\'{"status":"ready"}\')\n'
        " def log_message(self, *args): pass\n"
        "HTTPServer.allow_reuse_address = True\n"
        f"HTTPServer(('127.0.0.1', {port}), Handler).serve_forever()\n"
    )
    return Service(name, [sys.executable, str(script)], port, "/health/ready")


def wait_stopped(state):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with ownership(state):
                return
        except LifecycleError:
            time.sleep(0.05)
    pytest.fail("Supervisor did not relinquish installation ownership")


def assert_no_listener(port):
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_live_start_idempotence_stop_and_offline_restart(state, tmp_path, monkeypatch):
    service = fixture_service(tmp_path)
    first = launch(state, [service], timeout=3)
    manifest = json.loads((state / "processes.json").read_text())
    assert first["status"] == "running"
    assert http_json(f"http://127.0.0.1:{service.port}/health/ready") == {"status": "ready"}
    assert launch(state, [service], timeout=3) == first
    assert json.loads((state / "processes.json").read_text()) == manifest
    control(state, "stop")
    wait_stopped(state)
    assert_no_listener(service.port)
    # No package manager or downloaded assets needed to run the prepared service.
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    assert launch(state, [service], timeout=3)["services"] == {"gateway": "ready"}
    assert (
        json.loads((state / "processes.json").read_text())["supervisor_pid"]
        != manifest["supervisor_pid"]
    )


def test_pid_mismatch_manifest_never_signals_unrelated_process(state, tmp_path):
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        save_json(
            state / "processes.json",
            {"supervisor_pid": unrelated.pid, "children": [os.getpid(), unrelated.pid]},
        )
        service = fixture_service(tmp_path)
        launch(state, [service], timeout=3)
        # Even replacing the observations while live confers no process authority.
        save_json(
            state / "processes.json", {"supervisor_pid": unrelated.pid, "children": [unrelated.pid]}
        )
        control(state, "stop")
        wait_stopped(state)
        assert unrelated.poll() is None
        assert_no_listener(service.port)
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=3)


def test_port_conflict_keeps_foreign_server_alive(state, tmp_path):
    foreign = fixture_service(tmp_path)
    process = subprocess.Popen(
        foreign.command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                http_json(f"http://127.0.0.1:{foreign.port}/")
                break
            except OSError:
                time.sleep(0.05)
        with pytest.raises(LifecycleError, match="occupied"):
            launch(state, [foreign], timeout=1)
        assert process.poll() is None
        assert http_json(f"http://127.0.0.1:{foreign.port}/")["status"] == "ready"
    finally:
        process.terminate()
        process.wait(timeout=3)


def test_failed_child_rolls_back_only_owned_children(state, tmp_path):
    good = fixture_service(tmp_path)
    bad = fixture_service(tmp_path, "broken", exit_early=True)
    with pytest.raises(LifecycleError, match="Startup failed"):
        launch(state, [good, bad], timeout=1)
    wait_stopped(state)
    assert_no_listener(good.port)
    assert_no_listener(bad.port)
    assert "rolled back" in (state / "lifecycle.log").read_text()


def test_live_health_outage_is_not_reported_ready(state, tmp_path):
    service = fixture_service(tmp_path)
    launch(state, [service], timeout=3)
    # Stop via the fixture's own PID to simulate an unexpected crash (not launcher code).
    pid = int(Path(service.command[1] + ".pid").read_text())
    os.kill(pid, 15)
    wait_stopped(state)
    assert_no_listener(service.port)
    with pytest.raises(FileNotFoundError):
        control(state, "status")


def test_private_permissions_and_symlink_refusal(state, tmp_path):
    assert state.stat().st_mode & 0o777 == 0o700
    assert (state / "control.key").stat().st_mode & 0o777 == 0o600
    linked = tmp_path / "alias"
    linked.symlink_to(state, target_is_directory=True)
    with pytest.raises(LifecycleError, match="symlink"):
        configuration(linked)
    key = state / "control.key"
    original = key.read_bytes()
    key.unlink()
    target = tmp_path / "foreign"
    target.write_bytes(original)
    key.symlink_to(target)
    with pytest.raises(LifecycleError, match="symlink"):
        configuration(state)
    assert target.read_bytes() == original
    key.unlink()
    write_new(key, original)


def test_corrupt_state_not_overwritten(state):
    path = state / "installation.json"
    path.write_text('{"version":')
    with pytest.raises(LifecycleError, match="Corrupt"):
        configuration(state)
    assert path.read_text() == '{"version":'


def test_hardlinked_and_public_keys_rejected(state, tmp_path):
    key = state / "control.key"
    os.link(key, tmp_path / "linked")
    with pytest.raises(LifecycleError, match="hard links"):
        configuration(state)
    (tmp_path / "linked").unlink()
    key.chmod(0o644)
    with pytest.raises(LifecycleError, match="private"):
        configuration(state)
    key.chmod(0o600)


def test_unavailable_or_wrong_ollama_fails_without_starting_services(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError

    monkeypatch.setattr("agentgate.lifecycle.install.http_json", unavailable)
    with pytest.raises(LifecycleError, match="Ollama unavailable"):
        verify_ollama()
    monkeypatch.setattr(
        "agentgate.lifecycle.install.http_json",
        lambda *args: {"version": "1", "models": [{"name": "llama3.2:1b", "digest": "wrong"}]},
    )
    with pytest.raises(LifecycleError, match="digest differs"):
        verify_ollama()
