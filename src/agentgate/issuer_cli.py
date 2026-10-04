"""Trusted offline import and private loopback exchange client."""

import json
import re
import time
from pathlib import Path

import httpx

from agentgate.app import parse_json
from agentgate.cli import private_file
from agentgate.issuer_exchange import revoke_subject
from agentgate.issuer_trust import MAX_TOKEN_BYTES, MAX_TRUST_BYTES, TrustConfig, import_trust
from agentgate.storage import Store


def import_file(state_dir: Path, path: Path, expected_generation: int) -> int:
    with path.open("rb") as source:
        raw = source.read(MAX_TRUST_BYTES + 1)
    if len(raw) > MAX_TRUST_BYTES:
        raise ValueError("Trust configuration exceeds bound")
    parsed = parse_json(raw, 8)
    config = TrustConfig.model_validate_json(json.dumps(parsed))
    store = Store(state_dir / "agentgate.sqlite3")
    if not store.ready():
        raise ValueError("Migration required")
    return import_trust(store, config, expected_generation, time.time)


def exchange_file(gateway: str, parent_file: Path, assertion_file: Path, output: Path) -> None:
    from agentgate.agents.client import ClientFailure, gateway_origin

    try:
        origin = gateway_origin(gateway)
    except ClientFailure as error:
        raise ValueError("Explicit loopback origin required") from error
    if output.exists():
        raise ValueError("Refuse to overwrite child credential")
    with parent_file.open("r") as source:
        parent = source.read(512).strip()
    with assertion_file.open("r", encoding="utf-8") as source:
        assertion = source.read(MAX_TOKEN_BYTES + 1).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", parent) or len(assertion.encode()) > MAX_TOKEN_BYTES:
        raise ValueError("Invalid bounded token file")
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        with client.stream(
            "POST",
            origin + "/v1/authority/exchange",
            headers={"Authorization": "Bearer " + parent, "Accept-Encoding": "identity"},
            json={"access_token": assertion},
        ) as response:
            if (
                response.status_code != 200
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                raise ValueError("Exchange denied")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 2048:
                    raise ValueError("Exchange response exceeds bound")
    result = parse_json(bytes(body), 4)
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("token"), str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{43}", result["token"])
    ):
        raise ValueError("Invalid exchange response")
    private_file(output, result["token"].encode("ascii"))


def revoke_file(state_dir: Path, subject_id: str, expected_revision: int) -> None:
    revoke_subject(Store(state_dir / "agentgate.sqlite3"), subject_id, expected_revision)
