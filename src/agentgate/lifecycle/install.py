"""Prepare locked local runtimes without changing existing application authority."""

import hashlib
import json
import os
import platform
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from agentgate.lifecycle.processes import Service, available_port, clean_environment, http_json
from agentgate.lifecycle.state import (
    LifecycleError,
    check_file,
    check_path,
    ownership,
    private_dir,
    read_json,
    save_json,
    validate_data,
    validate_environment,
    write_new,
)

MODEL = "llama3.2:1b"
MODEL_DIGEST = "baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878"


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            env=env or clean_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LifecycleError(
            "Preparation command failed; check prerequisites with doctor (child output withheld)"
        ) from error


def verify_ollama() -> None:
    try:
        version = http_json("http://127.0.0.1:11434/api/version")
        models = http_json("http://127.0.0.1:11434/api/tags")
        if not isinstance(version.get("version"), str) or not any(
            entry.get("name") == MODEL and entry.get("digest") == MODEL_DIGEST
            for entry in models.get("models", [])
        ):
            raise ValueError
    except (OSError, ValueError, AttributeError) as error:
        raise LifecycleError(
            "Local Ollama unavailable or model digest differs. Prepare llama3.2:1b on 127.0.0.1:11434; "
            "the launcher never owns or stops Ollama. See manifests/generation-model.json"
        ) from error


def configuration(state: Path) -> dict[str, Any]:
    private_dir(state)
    value = read_json(state / "installation.json")
    if value.get("version") != 1 or value.get("state") != str(state):
        raise LifecycleError(
            "Unknown installation format/location; preserve state for explicit migration"
        )
    if value.get("semantic") not in ("off", "standard", "coreml"):
        raise LifecycleError("Invalid semantic profile")
    value.setdefault("question_set", "content-role-v1")
    if value["question_set"] not in ("content-role-v1", "content-role-v2"):
        raise LifecycleError("Invalid semantic question set")
    # Older configurations had three ports; choose a non-colliding default for
    # this additive field. The installer still refuses an occupied OS port.
    value.setdefault(
        "collector_port",
        next(
            port
            for port in range(8095, 8099)
            if port not in (value.get("port"), value.get("proxy_port"), value.get("worker_port"))
        ),
    )
    for key in ("port", "proxy_port", "worker_port", "collector_port"):
        if type(value.get(key)) is not int or not 1024 <= value[key] <= 65535:
            raise LifecycleError("Invalid configured service port")
    if len({value[k] for k in ("port", "proxy_port", "worker_port", "collector_port")}) != 4:
        raise LifecycleError("Service ports must differ")
    check_file(state / "control.key")
    if (state / "data").exists():
        validate_data(state / "data")
    return value


def runtime(state: Path, name: str) -> Path:
    return state / "runtime" / name / "bin"


def required_sources(root: Path) -> None:
    needed = [
        "requirements/litellm.txt",
        "config/litellm-local.yaml",
        "config/policy-models.yaml",
        "src/agentgate/models.py",
        "src/agentgate/scoped_tools.py",
        "src/agentgate/web/index.html",
    ]
    # Runtime authors own these contracts; an incomplete checkout must never look installed.
    missing = [name for name in needed if not (root / name).is_file()]
    if missing:
        raise LifecycleError(
            "Full application sources unavailable on this checkout: " + ", ".join(missing)
        )


def install(
    root: Path,
    state: Path,
    *,
    port: int,
    proxy_port: int,
    worker_port: int,
    semantic: str,
    offline: bool,
    collector_port: int = 8095,
    question_set: str = "content-role-v1",
) -> None:
    os.umask(0o077)
    if question_set not in ("content-role-v1", "content-role-v2"):
        raise LifecycleError("Invalid semantic question set")
    if len({port, proxy_port, worker_port, collector_port}) != 4 or any(
        not 1024 <= value <= 65535 for value in (port, proxy_port, worker_port, collector_port)
    ):
        raise LifecycleError("Choose four distinct service ports between 1024 and 65535")
    if platform.system() not in ("Darwin", "Linux"):
        raise LifecycleError("Supported hosts are macOS and Linux")
    if semantic == "coreml" and (platform.system() != "Darwin" or platform.machine() != "arm64"):
        raise LifecycleError("CoreML requires native Apple Silicon macOS")
    required_sources(root)
    check_path(state)
    if state.exists():
        settings = configuration(state)
        wanted = (port, proxy_port, worker_port, collector_port, semantic, question_set)
        existing = tuple(
            settings[key]
            for key in (
                "port",
                "proxy_port",
                "worker_port",
                "collector_port",
                "semantic",
                "question_set",
            )
        )
        changed = wanted != existing
    else:
        changed = False
        for value in (port, proxy_port, worker_port, collector_port):
            available_port(value)
        private_dir(state, create=True)
        write_new(state / "control.key", secrets.token_urlsafe(32).encode())
        save_json(
            state / "installation.json",
            {
                "version": 1,
                "state": str(state),
                "root": str(root),
                "port": port,
                "proxy_port": proxy_port,
                "worker_port": worker_port,
                "collector_port": collector_port,
                "semantic": semantic,
                "question_set": question_set,
                "prepared": False,
            },
        )
    settings = configuration(state)
    fingerprint = source_fingerprint(root)
    if (
        not changed
        and settings.get("prepared")
        and settings.get("source_fingerprint") == fingerprint
    ):
        for profile in ("gateway", "litellm"):
            validate_environment(state / "runtime" / profile)
            if not (runtime(state, profile) / "python").is_file():
                raise LifecycleError(
                    "Prepared environment missing; preserve state and repair runtime"
                )
        return
    with ownership(state):
        settings = configuration(state)
        for value in {
            port,
            proxy_port,
            worker_port,
            collector_port,
            settings["collector_port"],
            settings["port"],
            settings["proxy_port"],
            settings["worker_port"],
        }:
            available_port(value)
        verify_ollama()
        settings["prepared"] = False
        save_json(state / "installation.json", settings)
        private_dir(state / "runtime", create=True)
        env = clean_environment()
        env["UV_LINK_MODE"] = "copy"
        validate_environment(state / "runtime/gateway")
        env["UV_PROJECT_ENVIRONMENT"] = str(state / "runtime/gateway")
        flags = ["--offline"] if offline else []
        print("Preparing locked Python 3.12 gateway environment…", flush=True)
        run(
            [
                "uv",
                "sync",
                "--project",
                str(root),
                "--python",
                "3.12",
                "--locked",
                "--no-dev",
                "--no-editable",
                # uv's default local-wheel cache does not track source-only changes.
                "--reinstall-package",
                "agentgate",
                "--extra",
                "mcp",
                *flags,
            ],
            env=env,
        )
        profiles = ["litellm"] + ([f"laya-{semantic}"] if semantic != "off" else [])
        for profile in profiles:
            print(f"Preparing isolated {profile} environment…", flush=True)
            directory = state / "runtime" / profile
            validate_environment(directory)
            if not directory.exists():
                run(["uv", "venv", "--python", "3.12", *flags, str(directory)])
            run(
                [
                    "uv",
                    "pip",
                    "sync",
                    "--python",
                    str(runtime(state, profile) / "python"),
                    *flags,
                    str(root / "requirements" / f"{profile}.txt"),
                    "--link-mode",
                    "copy",
                ]
            )
        data = state / "data"
        gateway = str(runtime(state, "gateway") / "agentgate")
        if not data.exists():
            staging = state / "initializing"
            if staging.exists():
                raise LifecycleError(
                    "Interrupted initialization retained at initializing; inspect before recovery"
                )
            run(
                [
                    str(runtime(state, "gateway") / "python"),
                    "-m",
                    "agentgate.lifecycle.provision",
                    str(staging),
                    str(root / "config/policy-models.yaml"),
                    str(root / "config/litellm-local.yaml"),
                    semantic,
                ]
            )
            os.rename(staging, data)
        else:
            validate_data(data)
            # A stopped SQLite backup is retained before additive runtime migrations.
            import sqlite3

            backup = data / f"before-migrate-{time.time_ns()}.sqlite3"
            write_new(backup, b"")
            with (
                sqlite3.connect(data / "agentgate.sqlite3") as source,
                sqlite3.connect(backup) as target,
            ):
                source.backup(target)
            run([gateway, "--state-dir", str(data), "migrate"])
        run(
            [
                str(runtime(state, "gateway") / "python"),
                "-m",
                "agentgate.lifecycle.provision",
                "--configure-telemetry",
                str(data),
                str(settings["collector_port"]),
                str(collector_port),
            ]
        )
        if semantic != "off":
            prepare_assets(root, state, semantic, offline=offline)
        profile_changed = settings["question_set"] != question_set
        if settings["semantic"] != semantic or profile_changed:
            run(
                [
                    str(runtime(state, "gateway") / "python"),
                    "-m",
                    "agentgate.lifecycle.provision",
                    "--configure-semantic",
                    str(data),
                    semantic,
                    "changed" if profile_changed else "unchanged",
                ]
            )
        settings.update(
            port=port,
            proxy_port=proxy_port,
            worker_port=worker_port,
            collector_port=collector_port,
            semantic=semantic,
            question_set=question_set,
            prepared=True,
            root=str(root),
            installed_at=time.time(),
            source_fingerprint=fingerprint,
        )
        save_json(state / "installation.json", settings)


def prepare_assets(root: Path, state: Path, semantic: str, *, offline: bool) -> None:
    asset_root = state / "assets"
    private_dir(asset_root, create=True)
    private_dir(asset_root / "manifests", create=True)
    manifest = root / "manifests/model-assets.json"
    destination = asset_root / "manifests/model-assets.json"
    if not destination.exists():
        write_new(destination, manifest.read_bytes())
    elif destination.read_bytes() != manifest.read_bytes():
        raise LifecycleError("Installed asset manifest changed; explicit asset migration required")
    backend = f"laya_{semantic}"
    metadata = json.loads(manifest.read_bytes())["models"][backend]
    for name, expected in metadata["files"].items():
        path = asset_root / metadata["directory"] / name
        check_path(path)
        if not path.exists() and not offline:
            private_dir(path.parent, create=True)
            # Fixed revision/allowlisted manifest; no Hub auth or model loading during installation.
            url = f"https://huggingface.co/{metadata['repository']}/resolve/{metadata['revision']}/{name}"
            import urllib.request

            descriptor, name_on_disk = tempfile.mkstemp(prefix=".download-", dir=path.parent)
            temporary = Path(name_on_disk)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with (
                    os.fdopen(descriptor, "wb") as stream,
                    opener.open(url, timeout=60) as response,
                ):
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > expected["bytes"]:
                            raise LifecycleError("Model download exceeds manifest size")
                        stream.write(chunk)
                with temporary.open("rb") as stream:
                    downloaded = hashlib.file_digest(stream, "sha256").hexdigest()
                if size != expected["bytes"] or downloaded != expected["sha256"]:
                    raise LifecycleError("Downloaded model asset differs from pinned manifest")
                # Exclusive publication: another file is never silently overwritten.
                os.link(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        if not path.is_file():
            raise LifecycleError("Requested model assets unavailable offline")
        check_file(path)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != expected["bytes"] or digest != expected["sha256"]:
            raise LifecycleError("Model asset differs from pinned manifest")


def services(state: Path) -> list[Service]:
    settings = configuration(state)
    if not settings.get("prepared"):
        raise LifecycleError("Installation incomplete; rerun install before start")
    gateway = str(runtime(state, "gateway") / "agentgate")
    data = state / "data"
    port, proxy_port = settings["port"], settings["proxy_port"]
    result = [
        Service(
            "litellm",
            [
                str(runtime(state, "litellm") / "litellm"),
                "--config",
                str(data / "litellm.yaml"),
                "--host",
                "127.0.0.1",
                "--port",
                str(proxy_port),
                "--telemetry",
                "False",
            ],
            proxy_port,
            "/v1/models",
            str(data / "litellm.token"),
        )
    ]
    command = [
        gateway,
        "--state-dir",
        str(data),
        "serve",
        "--port",
        str(port),
        "--admin-origin",
        f"http://127.0.0.1:{port}",
        "--policy",
        str(data / "policy.yaml"),
        "--model-url",
        f"http://127.0.0.1:{proxy_port}/v1",
        "--model-token-file",
        str(data / "litellm.token"),
        "--mcp",
    ]
    semantic = settings["semantic"]
    if semantic != "off":
        verify_assets(state, semantic)
        worker_port = settings["worker_port"]
        backend = f"laya_{semantic}"
        result.append(
            Service(
                "semantic",
                [
                    gateway,
                    "--state-dir",
                    str(data),
                    "semantic-worker",
                    "--backend",
                    backend,
                    "--question-set",
                    settings["question_set"],
                    "--runtime-python",
                    str(runtime(state, f"laya-{semantic}") / "python"),
                    "--root",
                    str(state / "assets"),
                    "--port",
                    str(worker_port),
                ],
                worker_port,
                "/internal/v1/semantic/ready",
                str(data / "worker.token"),
            )
        )
        command.extend(
            [
                "--semantic-url",
                f"http://127.0.0.1:{worker_port}",
                "--semantic-backend",
                backend,
                "--semantic-question-set",
                settings["question_set"],
            ]
        )
    collector_port = settings["collector_port"]
    result.append(
        Service(
            "collector",
            [
                str(runtime(state, "gateway") / "agentgate-telemetry"),
                "collector",
                "--database",
                str(data / "collector.sqlite3"),
                "--token-file",
                str(data / "collector.token"),
                "--tenant",
                "tenant-a",
                "--port",
                str(collector_port),
            ],
            collector_port,
            "/health/live",
        )
    )
    command.extend(
        [
            "--telemetry-config",
            str(data / "telemetry.json"),
            "--telemetry-token-file",
            str(data / "collector.token"),
        ]
    )
    result.append(Service("gateway", command, port, "/health/ready"))
    return result


def source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [root / "pyproject.toml", root / "uv.lock"]
    for directory in ("src/agentgate", "config", "requirements", "manifests"):
        paths.extend(
            path
            for path in (root / directory).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def verify_assets(state: Path, semantic: str) -> None:
    root = state / "assets"
    metadata = read_json(root / "manifests/model-assets.json")["models"][f"laya_{semantic}"]
    for name, expected in metadata["files"].items():
        path = root / metadata["directory"] / name
        check_file(path)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != expected["bytes"] or digest != expected["sha256"]:
            raise LifecycleError(
                "Requested model asset unavailable or differs from pinned manifest"
            )
