"""Prepare locked local runtimes without changing existing application authority."""

import hashlib
import json
import os
import platform
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any

from agentgate.lifecycle.processes import Service, clean_environment, http_json
from agentgate.lifecycle.state import (
    LifecycleError,
    check_file,
    check_path,
    ownership,
    private_dir,
    read_json,
    save_json,
    validate_data,
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
    for key in ("port", "proxy_port", "worker_port"):
        if type(value.get(key)) is not int or not 1024 <= value[key] <= 65535:
            raise LifecycleError("Invalid configured service port")
    if len({value[k] for k in ("port", "proxy_port", "worker_port")}) != 3:
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
) -> None:
    os.umask(0o077)
    if platform.system() not in ("Darwin", "Linux"):
        raise LifecycleError("Supported hosts are macOS and Linux")
    if semantic == "coreml" and (platform.system() != "Darwin" or platform.machine() != "arm64"):
        raise LifecycleError("CoreML requires native Apple Silicon macOS")
    required_sources(root)
    check_path(state)
    if state.exists():
        settings = configuration(state)
        wanted = (port, proxy_port, worker_port, semantic)
        existing = tuple(settings[key] for key in ("port", "proxy_port", "worker_port", "semantic"))
        if wanted != existing:
            raise LifecycleError(
                "Existing installation configuration differs; reuse its original options"
            )
    else:
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
                "semantic": semantic,
                "prepared": False,
            },
        )
    with ownership(state):
        settings = configuration(state)
        verify_ollama()
        private_dir(state / "runtime", create=True)
        env = clean_environment()
        env["UV_PROJECT_ENVIRONMENT"] = str(state / "runtime/gateway")
        flags = ["--offline"] if offline else []
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
                "--extra",
                "mcp",
                *flags,
            ],
            env=env,
        )
        profiles = ["litellm"] + ([f"laya-{semantic}"] if semantic != "off" else [])
        for profile in profiles:
            directory = state / "runtime" / profile
            check_path(directory)
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
            run([gateway, "--state-dir", str(staging), "init-demo"])
            write_new(staging / "litellm.token", ("sk-" + secrets.token_urlsafe(32)).encode())
            write_new(staging / "policy.yaml", (root / "config/policy-models.yaml").read_bytes())
            write_new(staging / "litellm.yaml", (root / "config/litellm-local.yaml").read_bytes())
            run(
                [
                    gateway,
                    "--state-dir",
                    str(staging),
                    "init-operator",
                    "--policy",
                    str(staging / "policy.yaml"),
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
        if semantic != "off":
            prepare_assets(root, state, semantic, offline=offline)
        settings.update(prepared=True, root=str(root), installed_at=time.time())
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

            with urllib.request.urlopen(url, timeout=60) as response:
                temporary = path.with_name(path.name + ".download")
                write_new(temporary, b"")
                size = 0
                with temporary.open("wb") as stream:
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > expected["bytes"]:
                            raise LifecycleError("Model download exceeds manifest size")
                        stream.write(chunk)
                os.rename(temporary, path)
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
            ["--semantic-url", f"http://127.0.0.1:{worker_port}", "--semantic-backend", backend]
        )
    result.append(Service("gateway", command, port, "/health/ready"))
    return result
