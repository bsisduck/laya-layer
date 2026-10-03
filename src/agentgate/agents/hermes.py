"""Launch pinned upstream Hermes in an isolated runtime and disposable private home."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agentgate.agents.client import ClientFailure, decode, gateway_origin
from agentgate.agents.direct import private_read

HERMES_COMMIT = "f97608f178d1ffeca59860195ab7da295f7c8e5f"
HERMES_VERSION = "0.21.5"
HERMES_REPOSITORY = "https://github.com/NousResearch/hermes-agent.git"


def verify_source(source: Path) -> None:
    if not (source / ".git").exists():
        raise ClientFailure("hermes_source_unavailable")
    try:
        head = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ClientFailure("hermes_source_unavailable") from error
    if head != HERMES_COMMIT or dirty:
        raise ClientFailure("hermes_source_pin_mismatch")


def prepare(source: Path) -> None:
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.mkdir()
        subprocess.run(["git", "-C", str(source), "init"], check=True)
        subprocess.run(
            ["git", "-C", str(source), "remote", "add", "origin", HERMES_REPOSITORY], check=True
        )
        subprocess.run(
            ["git", "-C", str(source), "fetch", "--depth", "1", "origin", HERMES_COMMIT], check=True
        )
        subprocess.run(["git", "-C", str(source), "switch", "--detach", "FETCH_HEAD"], check=True)
    verify_source(source)
    subprocess.run(
        [
            "uv",
            "sync",
            "--project",
            str(source),
            "--locked",
            "--extra",
            "mcp",
            "--no-dev",
            "--python",
            "3.12",
        ],
        check=True,
    )


def restricted_config(origin: str, token: str, model: str) -> dict[str, Any]:
    return {
        "model": {
            "provider": "custom",
            "default": model,
            "base_url": origin + "/v1",
            "streaming": False,
        },
        "agent": {"api_max_retries": 1, "auto_recovery_cycles": 0},
        "compression": {"enabled": False},
        "tools": {"tool_search": {"enabled": "off"}},
        "memory": {"memory_enabled": False, "user_profile_enabled": False, "nudge_interval": 0},
        "auxiliary": {"background_review": {"enabled": False}},
        "platform_toolsets": {"cli": ["agentgate-restricted"]},
        "mcp_servers": {
            "agentgate": {
                "url": origin + "/mcp",
                "headers": {"Authorization": "Bearer " + token},
                "timeout": 60,
                "connect_timeout": 10,
                "trust": "full",
                "sampling": {"enabled": False},
                "elicitation": {"enabled": False},
                "tools": {
                    "include": ["documents.read", "memory.query", "mail.send"],
                    "prompts": False,
                    "resources": False,
                },
            }
        },
    }


def run_hermes(
    source: Path,
    origin: str,
    token: str,
    prompt: str,
    *,
    model: str = "local-demo",
    max_turns: int = 6,
    max_tokens: int = 256,
) -> dict[str, Any]:
    source = source.resolve()
    verify_source(source)
    origin = gateway_origin(origin)
    if not 2 <= max_turns <= 16 or not 1 <= max_tokens <= 4096:
        raise ClientFailure("invalid_run_bounds")
    python = source / ".venv/bin/python"
    if not python.is_file():
        raise ClientFailure("hermes_runtime_unavailable_run_prepare")
    with tempfile.TemporaryDirectory(prefix="agentgate-hermes-") as temporary:
        home = Path(temporary)
        home.chmod(0o700)
        (home / "config.yaml").write_text(json.dumps(restricted_config(origin, token, model)))
        (home / "config.yaml").chmod(0o600)
        payload = {
            "source": str(source),
            "gateway": origin,
            "token": token,
            "model": model,
            "prompt": prompt,
            "max_turns": max_turns,
            "max_tokens": max_tokens,
        }
        # No inherited provider/operator/proxy credentials, user home, plugins or configuration.
        environment = {
            "HOME": str(home),
            "HERMES_HOME": str(home),
            "PATH": str(python.parent),
            "LANG": "C.UTF-8",
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
        }
        try:
            completed = subprocess.run(
                [str(python), str(Path(__file__).with_name("hermes_runner.py"))],
                input=json.dumps(payload).encode(),
                cwd=home,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=300,
            )
        except subprocess.TimeoutExpired as error:
            raise ClientFailure("hermes_deadline_no_retry") from error
        result_file = home / "result.json"
        if not result_file.is_file():
            raise ClientFailure("hermes_unavailable_or_aborted")
        result = decode(private_read(result_file))
        if completed.returncode != 0 or result.get("status") not in (
            "completed",
            "pending_approval",
        ):
            raise ClientFailure("hermes_" + str(result.get("reason", "failed")))
        result["source_commit"] = HERMES_COMMIT
        result["version"] = HERMES_VERSION
        result["lock_sha256"] = hashlib.sha256((source / "uv.lock").read_bytes()).hexdigest()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(".runtime/hermes-source"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "prepare", help="Online preparation only; fetch exact source and sync upstream lock"
    )
    run = commands.add_parser(
        "run", help="Offline invocation; never installs, updates or falls back"
    )
    run.add_argument("--gateway", required=True)
    run.add_argument("--token-file", type=Path, required=True)
    run.add_argument("--prompt", required=True)
    run.add_argument("--model", default="local-demo")
    run.add_argument("--max-turns", type=int, default=6)
    run.add_argument("--max-tokens", type=int, default=256)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.source.resolve())
            result = {"status": "prepared", "source_commit": HERMES_COMMIT}
        else:
            result = run_hermes(
                args.source,
                args.gateway,
                private_read(args.token_file).strip(),
                args.prompt,
                model=args.model,
                max_turns=args.max_turns,
                max_tokens=args.max_tokens,
            )
        print(json.dumps(result, ensure_ascii=False))
        if result["status"] == "pending_approval":
            raise SystemExit(2)
    except (ClientFailure, OSError, subprocess.SubprocessError) as error:
        reason = str(error) if isinstance(error, ClientFailure) else "hermes_setup_failed"
        print(json.dumps({"status": "failed", "reason": reason}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
