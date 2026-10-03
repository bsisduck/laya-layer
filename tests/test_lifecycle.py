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


def test_supervisor_crash_does_not_orphan_owned_service(state, tmp_path):
    service = fixture_service(tmp_path)
    launch(state, [service], timeout=3)
    pid = json.loads((state / "processes.json").read_text())["supervisor_pid"]
    os.kill(pid, 9)  # actual supervisor death, not a graceful stop
    wait_stopped(state)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", service.port)) != 0:
                break
        time.sleep(0.05)
    assert_no_listener(service.port)
    # Stale socket/observations can be recovered only with the exclusive lock.
    assert launch(state, [service], timeout=3)["status"] == "running"


def test_fresh_provision_and_migration_keep_credentials_audit_and_spend(tmp_path):
    from agentgate.contracts import ActionRequest
    from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
    from agentgate.lifecycle.provision import initialize
    from agentgate.lifecycle.state import validate_data
    from agentgate.policy import load_policy
    from agentgate.service import ActionService
    from agentgate.storage import Store, credential_digest

    directory = tmp_path / "install"
    policy = Path(__file__).resolve().parents[1] / "config/policy.yaml"
    proxy = tmp_path / "proxy.yaml"
    proxy.write_text("model_list: []\n")  # isolated lifecycle fixture, no inference
    initialize(directory, policy, proxy, "off")
    validate_data(directory)
    keys = {p.name: p.read_bytes() for p in directory.glob("*.token")}
    store = Store(directory / "agentgate.sqlite3")
    token = keys["client.token"].decode()
    identity = store.resolve(credential_digest(token), time.time())
    assert identity.root_run_id == "run-demo"
    assert set(identity.operations) == {
        "documents.read",
        "memory.query",
        "mail.send",
        "chat.completions",
    }
    documents = demo_documents()
    service = ActionService(
        store,
        load_policy(policy),
        DocumentRegistry(documents),
        FixtureExecutor(documents),
        (directory / "audit.key").read_bytes(),
    )
    # Observe real document execution and its persisted accounting before migration.
    context = service.new_context()
    service.authenticate(context, token)
    response = service.execute(
        context,
        ActionRequest(operation="documents.read", arguments={"document_id": "tenant-a-notes"}),
    )
    assert response.executed
    counters = store.budget_counters()
    events = [e.model_dump() for e in store.events()]
    store.initialize()
    assert store.budget_counters() == counters
    assert [e.model_dump() for e in store.events()] == events
    assert store.resolve(credential_digest(token), time.time()) == identity
    with pytest.raises(FileExistsError):
        initialize(directory, policy, proxy, "off")
    assert {p.name: p.read_bytes() for p in directory.glob("*.token")} == keys


@pytest.fixture
def installation_fixture(tmp_path, monkeypatch):
    """Only dependency downloads/upstream discovery are fixtures; provisioning is real."""
    from agentgate.lifecycle import install as installer

    root = tmp_path / "checkout"
    root.mkdir()
    files = {
        "pyproject.toml": "fixture",
        "uv.lock": "fixture",
        "requirements/litellm.txt": "fixture",
        "src/agentgate/models.py": "fixture",
        "src/agentgate/scoped_tools.py": "fixture",
        "src/agentgate/web/index.html": "fixture",
        "config/litellm-local.yaml": "model_list: []",
        "config/policy-models.yaml": (
            Path(__file__).resolve().parents[1] / "config/policy.yaml"
        ).read_text(),
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    state = tmp_path / "installed"
    real_run = installer.run

    def dependency_fixture(command, *, env=None):
        if command[0] != "uv":
            prefix = (
                [sys.executable, "-m", "agentgate.cli"]
                if Path(command[0]).name == "agentgate"
                else [sys.executable]
            )
            return real_run([*prefix, *command[1:]], env=env)
        if command[1] == "sync":
            directory = Path(env["UV_PROJECT_ENVIRONMENT"])
        elif command[1] == "venv":
            directory = Path(command[-1])
        else:
            return
        private_dir(directory, create=True)
        private_dir(directory / "bin", create=True)
        if (directory / "bin/python").exists():
            return
        (directory / "bin/python").symlink_to(sys.executable)
        cli = directory / "bin/agentgate"
        write_new(cli, f"#!{sys.executable}\nfrom agentgate.cli import main\nmain()\n".encode())
        cli.chmod(0o700)

    monkeypatch.setattr(installer, "run", dependency_fixture)
    monkeypatch.setattr(installer, "verify_ollama", lambda: None)
    options = {
        "port": free_port(),
        "proxy_port": free_port(),
        "worker_port": free_port(),
        "semantic": "off",
        "offline": True,
    }
    return installer, root, state, options


def test_repeated_install_preserves_private_authority(installation_fixture):
    installer, root, state, options = installation_fixture
    installer.install(root, state, **options)
    before = {p.name: p.read_bytes() for p in (state / "data").iterdir()}
    installer.install(root, state, **options)
    assert before == {p.name: p.read_bytes() for p in (state / "data").iterdir()}
    assert configuration(state)["prepared"] is True
    assert "sk-" not in (state / "installation.json").read_text()


def test_source_only_upgrade_rebuilds_actual_installed_wheel(installation_fixture, monkeypatch):
    """Use real offline uv/wheels; only the unrelated proxy/upstream remain fixtures."""
    import shutil

    from agentgate.lifecycle.processes import clean_environment

    installer, root, state, options = installation_fixture
    repository = Path(__file__).resolve().parents[1]
    for name in ("pyproject.toml", "uv.lock", "README.md"):
        shutil.copyfile(repository / name, root / name)
    shutil.copytree(
        repository / "src",
        root / "src",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    dependency_fixture = installer.run
    # make setup prepares this cache; CI deliberately locates it outside HOME.
    # Keep the offline wheel probe on that cache without inheriting provider env.
    cache = subprocess.check_output(["uv", "cache", "dir"], text=True, timeout=10).strip()

    def actual_gateway_sync(command, *, env=None):
        if command[:2] == ["uv", "sync"]:
            result = subprocess.run(
                command,
                env=env | {"UV_CACHE_DIR": cache},
                capture_output=True,
                text=True,
                timeout=90,
            )
            assert result.returncode == 0, result.stderr
        else:
            dependency_fixture(command, env=env)

    monkeypatch.setattr(installer, "run", actual_gateway_sync)

    def installed_asset():
        return subprocess.check_output(
            [
                str(state / "runtime/gateway/bin/python"),
                "-c",
                "from importlib.resources import files; "
                "print(files('agentgate').joinpath('web/app.js').read_text(), end='')",
            ],
            cwd=state,
            env=clean_environment(),
            timeout=10,
        )

    installer.install(root, state, **options)
    asset = root / "src/agentgate/web/app.js"
    assert installed_asset() == asset.read_bytes()
    authority = (state / "data/client.token").read_bytes()
    metadata = [(root / name).read_bytes() for name in ("pyproject.toml", "uv.lock")]
    asset.write_bytes(asset.read_bytes() + b"\n// source-only upgrade regression\n")
    installer.install(root, state, **options)
    assert installed_asset() == asset.read_bytes()
    assert authority == (state / "data/client.token").read_bytes()
    assert metadata == [(root / name).read_bytes() for name in ("pyproject.toml", "uv.lock")]

    def unexpected_preparation(*args, **kwargs):
        pytest.fail("Unchanged fingerprint must not reinstall any package")

    monkeypatch.setattr(installer, "run", unexpected_preparation)
    installer.install(root, state, **options)
    assert installed_asset() == asset.read_bytes()


def test_install_refuses_unknown_state_without_writes(installation_fixture):
    installer, root, state, options = installation_fixture
    private_dir(state, create=True)
    write_new(state / "existing.key", b"preserved-authority")
    with pytest.raises(FileNotFoundError):
        installer.install(root, state, **options)
    assert list(state.iterdir()) == [state / "existing.key"]
    assert (state / "existing.key").read_bytes() == b"preserved-authority"


def test_installed_environment_symlink_cannot_overwrite_foreign_state(
    installation_fixture, tmp_path
):
    installer, root, state, options = installation_fixture
    installer.install(root, state, **options)
    foreign = tmp_path / "foreign-packages"
    private_dir(foreign, create=True)
    write_new(foreign / "sentinel", b"untouched")
    (state / "runtime/gateway/lib").symlink_to(foreign, target_is_directory=True)
    with pytest.raises(LifecycleError, match="Unsafe symlink"):
        installer.install(root, state, **options)
    assert (foreign / "sentinel").read_bytes() == b"untouched"


def test_slow_health_headers_have_an_absolute_deadline(tmp_path):
    from threading import Thread

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def slow_peer():
        with listener, listener.accept()[0] as connection:
            connection.recv(1024)
            try:
                for byte in b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n":
                    connection.sendall(bytes([byte]))
                    time.sleep(0.03)
            except OSError:
                pass

    thread = Thread(target=slow_peer, daemon=True)
    thread.start()
    started = time.monotonic()
    with pytest.raises((TimeoutError, OSError)):
        http_json(f"http://127.0.0.1:{port}/", timeout=0.2)
    assert time.monotonic() - started < 0.8
    thread.join(timeout=2)


def test_upgrade_retains_keys_ledger_and_semantic_quota(installation_fixture):
    import sqlite3

    installer, root, state, options = installation_fixture
    installer.install(root, state, **options)
    data = state / "data"
    keys = {p.name: p.read_bytes() for p in data.glob("*.token")}
    with sqlite3.connect(data / "semantic-quota.sqlite3") as quota:
        quota.execute("CREATE TABLE fixture_quota (spent INTEGER)")
        quota.execute("INSERT INTO fixture_quota VALUES (47)")
    # Immutable spent data independent of the launcher's own implementation.
    with sqlite3.connect(data / "agentgate.sqlite3") as ledger:
        credentials = ledger.execute("SELECT * FROM credentials").fetchall()
    (root / "uv.lock").write_text("fixture updated runtime")
    installer.install(root, state, **options)
    assert {p.name: p.read_bytes() for p in data.glob("*.token")} == keys
    with sqlite3.connect(data / "agentgate.sqlite3") as ledger:
        assert ledger.execute("SELECT * FROM credentials").fetchall() == credentials
    with sqlite3.connect(data / "semantic-quota.sqlite3") as quota:
        assert quota.execute("SELECT spent FROM fixture_quota").fetchone() == (47,)
    backups = list(data.glob("before-migrate-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT * FROM credentials").fetchall() == credentials


def test_invalid_ports_do_not_create_partial_installation(installation_fixture):
    installer, root, state, options = installation_fixture
    with pytest.raises(LifecycleError, match="distinct"):
        installer.install(root, state, **(options | {"port": 80}))
    assert not state.exists()


def test_port_reconfiguration_preserves_existing_authority(installation_fixture):
    installer, root, state, options = installation_fixture
    installer.install(root, state, **options)
    token = (state / "data/client.token").read_bytes()
    new_port = free_port()
    installer.install(root, state, **(options | {"port": new_port}))
    assert configuration(state)["port"] == new_port
    assert (state / "data/client.token").read_bytes() == token


def test_semantic_activation_retains_policy_and_root(installation_fixture):
    from agentgate.control_plane import ControlPlane
    from agentgate.lifecycle.provision import configure_semantic
    from agentgate.storage import Store

    installer, root, state, options = installation_fixture
    installer.install(root, state, **options)
    store = Store(state / "data/agentgate.sqlite3")
    controls = ControlPlane(store)
    before = controls.snapshot()
    with store.connection() as connection:
        identities = connection.execute("SELECT digest, identity FROM credentials").fetchall()
    configure_semantic(state / "data", "standard")
    after = controls.snapshot()
    assert after.policy.semantic_required
    assert after.policy.revision == before.policy.revision + 1
    assert after.policy.tool_budgets == before.policy.tool_budgets
    assert after.policy.output == before.policy.output
    with store.connection() as connection:
        assert (
            connection.execute("SELECT digest, identity FROM credentials").fetchall() == identities
        )
    configure_semantic(state / "data", "coreml")
    assert controls.snapshot().policy.version == after.policy.version


def test_clean_environment_excludes_cloud_keys_proxies_and_dotenv(monkeypatch):
    from agentgate.lifecycle.processes import clean_environment

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-must-not-be-inherited")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-must-not-be-inherited")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("PYTHONPATH", "/untrusted-modules")
    result = clean_environment()
    assert (
        not {"OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "HTTPS_PROXY", "PYTHONPATH"} & result.keys()
    )
    assert result["PYTHON_DOTENV_DISABLED"] == "1"
    assert result["LITELLM_MODE"] == "PRODUCTION"


def test_optional_asset_missing_or_corrupt_is_not_ready(state):
    import hashlib

    from agentgate.lifecycle.install import verify_assets

    content = b"fixture bytes; not a real model"
    private_dir(state / "assets/manifests", create=True)
    save_json(
        state / "assets/manifests/model-assets.json",
        {
            "models": {
                "laya_standard": {
                    "directory": "models/standard",
                    "files": {
                        "asset": {
                            "bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                    },
                }
            }
        },
    )
    with pytest.raises(FileNotFoundError):
        verify_assets(state, "standard")
    private_dir(state / "assets/models/standard", create=True)
    path = state / "assets/models/standard/asset"
    write_new(path, content)
    verify_assets(state, "standard")
    path.write_bytes(b"corrupt")
    with pytest.raises(LifecycleError, match="differs"):
        verify_assets(state, "standard")


def test_control_protocol_handles_fragmentation_without_unbounded_wait():
    from threading import Thread

    from agentgate.lifecycle.processes import receive_json

    left, right = socket.socketpair()

    def fragmented_sender():
        with right:
            for part in (b'{"sta', b'tus": "rea', b'dy"}\n'):
                right.sendall(part)
                time.sleep(0.02)

    thread = Thread(target=fragmented_sender, daemon=True)
    thread.start()
    with left:
        assert receive_json(left, 100, 1) == {"status": "ready"}
    thread.join(timeout=2)


def test_linux_coreml_request_is_explicitly_unsupported(installation_fixture, monkeypatch):
    installer, root, state, options = installation_fixture
    monkeypatch.setattr(installer.platform, "system", lambda: "Linux")
    with pytest.raises(LifecycleError, match="CoreML requires"):
        installer.install(root, state, **(options | {"semantic": "coreml"}))
    assert not state.exists()
