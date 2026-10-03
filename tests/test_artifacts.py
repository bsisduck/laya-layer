import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentgate.artifacts import ApprovedRegistry, Manifest, inspect_manifest, read_contract
from agentgate.control_plane import ControlPlane, ControlSnapshot, Indicator, ThreatFeed
from agentgate.policy import Policy
from agentgate.storage import Store

FIXTURES = Path("config/artifact-demo")


def inputs():
    return (
        read_contract(FIXTURES / "approved.json", Manifest),
        read_contract(FIXTURES / "registry.json", ApprovedRegistry),
        ControlSnapshot(Policy(policy_id="test", revision=1), ThreatFeed()),
    )


def test_exact_manifest_passes_without_download_deserialization_or_execution(monkeypatch):
    manifest, registry, controls = inputs()

    def forbidden(*args, **kwargs):
        pytest.fail("Metadata inspection must perform no external work")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    result = inspect_manifest(manifest, registry, controls)
    assert result["allowed"] is True
    assert result["mode"] == "metadata_policy_simulation"
    assert (
        result["bytes_verified"]
        is result["artifact_downloaded"]
        is result["artifact_executed"]
        is False
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "c" * 64),
        ("source", "https://unapproved.example.invalid/model.safetensors"),
        ("revision", "d" * 40),
        ("asset_id", "other-asset"),
        ("serialization", "json"),
    ],
)
def test_changed_manifest_component_denies(field, value):
    manifest, registry, controls = inputs()
    result = inspect_manifest(manifest.model_copy(update={field: value}), registry, controls)
    assert result["allowed"] is False and result["reason"] == "MANIFEST_NOT_APPROVED"


@pytest.mark.parametrize("serialization", ["pickle", "joblib", "torch_pickle"])
def test_executable_serializers_cannot_be_approved(serialization):
    manifest, registry, controls = inputs()
    unsafe = manifest.model_copy(update={"serialization": serialization})
    assert inspect_manifest(unsafe, registry, controls)["reason"] == "ARTIFACT_THREAT_BLOCKED"
    with pytest.raises(ValidationError):
        inspect_manifest(unsafe, registry.model_copy(update={"manifests": (unsafe,)}), controls)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("blocked_sha256", "b" * 64),
        ("blocked_source", "https://models.example.invalid/approved/model.safetensors"),
        ("blocked_domain", "example.invalid"),
    ],
)
def test_feed_revokes_an_exact_approved_tuple(kind, value):
    manifest, registry, controls = inputs()
    feed = ThreatFeed(
        revision=2,
        indicators=(
            Indicator(
                id="revoked",
                kind=kind,
                value=value,
                stages=("artifact_intake",),
            ),
        ),
    )
    result = inspect_manifest(manifest, registry, ControlSnapshot(controls.policy, feed))
    assert result["allowed"] is False and result["feed_version"] == "local:2"


@pytest.mark.parametrize(
    "body",
    [
        b'{"asset_id":"first","asset_id":"second"}',
        b'{"revision":NaN}',
        b"[" * 2000 + b"]" * 2000,
        b" " * 65537,
    ],
)
def test_invalid_or_unbounded_metadata_is_rejected(tmp_path, body):
    path = tmp_path / "invalid.json"
    path.write_bytes(body)
    with pytest.raises((ValueError, RecursionError)):
        read_contract(path, Manifest)


def run_cli(manifest, *extra):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "agentgate.artifacts",
            str(manifest),
            "--approved",
            str(FIXTURES / "registry.json"),
            *map(str, extra),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_cli_has_truthful_exit_codes_and_requires_explicit_feed():
    for name, code in [
        ("approved.json", 0),
        ("changed-digest.json", 2),
        ("unapproved-source.json", 2),
        ("unsafe-serializer.json", 2),
    ]:
        result = run_cli(FIXTURES / name, "--feed", FIXTURES / "feed.json")
        assert result.returncode == code, result.stderr
        assert json.loads(result.stdout)["artifact_executed"] is False
    assert run_cli(FIXTURES / "approved.json").returncode != 0


def test_cli_uses_active_feed_without_mutating_installation(tmp_path):
    store = Store(tmp_path / "agentgate.sqlite3")
    store.initialize()
    controls = ControlPlane(store)
    controls.initialize(Policy(policy_id="test", revision=1))
    assert run_cli(FIXTURES / "approved.json", "--state-dir", tmp_path).returncode == 0
    controls.activate_feed(
        ThreatFeed(
            revision=2,
            indicators=(
                Indicator(
                    id="revoked",
                    kind="blocked_sha256",
                    value="b" * 64,
                    stages=("artifact_intake",),
                ),
            ),
        ),
        "local:1",
    )
    events = controls.events()
    denied = run_cli(FIXTURES / "approved.json", "--state-dir", tmp_path)
    assert denied.returncode == 2
    assert json.loads(denied.stdout)["feed_version"] == "local:2"
    assert controls.events() == events and store.events() == []


def test_registry_rejects_ambiguous_revision_or_unknown_loader():
    manifest, registry, controls = inputs()
    with pytest.raises(ValidationError):
        ApprovedRegistry.model_validate_json(
            registry.model_copy(
                update={
                    "manifests": (manifest, manifest.model_copy(update={"sha256": "c" * 64})),
                }
            ).model_dump_json()
        )
    with pytest.raises(ValidationError):
        inspect_manifest(
            manifest.model_copy(update={"serialization": "python_import"}), registry, controls
        )
