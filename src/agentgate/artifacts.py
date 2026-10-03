"""Metadata-only artifact intake policy demonstration; never opens an artifact."""

import argparse
import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, model_validator

from agentgate.app import reject_constant, unique_object
from agentgate.contracts import Contract, Identifier
from agentgate.control_plane import (
    ArtifactMetadata,
    ControlPlane,
    ControlSnapshot,
    ThreatBlocked,
    ThreatFeed,
    canonical_source,
)
from agentgate.policy import Policy
from agentgate.storage import StorageUnavailable, Store


class Manifest(ArtifactMetadata):
    asset_id: Identifier
    revision: Annotated[str, Field(pattern=r"^[a-f0-9]{40}(?:[a-f0-9]{24})?$")]

    @model_validator(mode="after")
    def canonical_https(self) -> "Manifest":
        if not self.source.startswith("https://") or canonical_source(self.source) != self.source:
            raise ValueError("Manifest source must be canonical HTTPS")
        return self


class ApprovedRegistry(Contract):
    registry_id: Identifier
    revision: Annotated[int, Field(ge=1, le=2147483647)]
    manifests: Annotated[tuple[Manifest, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def unique_safe_assets(self) -> "ApprovedRegistry":
        keys = {(item.asset_id, item.revision) for item in self.manifests}
        if len(keys) != len(self.manifests) or any(
            item.serialization not in ("safetensors", "json") for item in self.manifests
        ):
            raise ValueError("Registry requires unique revisions and non-executable serializers")
        return self


def inspect_manifest(
    manifest: Manifest,
    registry: ApprovedRegistry,
    controls: ControlSnapshot,
) -> dict[str, str | bool]:
    manifest = Manifest.model_validate_json(manifest.model_dump_json())
    registry = ApprovedRegistry.model_validate_json(registry.model_dump_json())
    artifact = ArtifactMetadata.model_validate_json(
        manifest.model_dump_json(exclude={"asset_id", "revision"})
    )
    reason = "APPROVED_MANIFEST" if manifest in registry.manifests else "MANIFEST_NOT_APPROVED"
    try:
        controls.inspect("artifact_intake", manifest.model_dump_json(), artifacts=(artifact,))
    except ThreatBlocked:
        reason = "ARTIFACT_THREAT_BLOCKED"
    return {
        "mode": "metadata_policy_simulation",
        "asset_id": manifest.asset_id,
        "allowed": reason == "APPROVED_MANIFEST",
        "reason": reason,
        "registry_version": f"{registry.registry_id}:{registry.revision}",
        "feed_version": controls.feed.version,
        "bytes_verified": False,
        "artifact_downloaded": False,
        "artifact_executed": False,
    }


def read_contract[T: Contract](path: Path, contract: type[T]) -> T:
    with path.open("rb") as stream:
        body = stream.read(65537)
    if len(body) > 65536:
        raise ValueError("Metadata file exceeds 64 KiB")
    json.loads(body, object_pairs_hook=unique_object, parse_constant=reject_constant)
    return contract.model_validate_json(body)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check artifact metadata; no download or execution"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--approved", type=Path, required=True, help="Operator-approved registry")
    feed = parser.add_mutually_exclusive_group(required=True)
    feed.add_argument("--feed", type=Path, help="Explicit data-only feed snapshot")
    feed.add_argument("--state-dir", type=Path, help="Read current activated installation feed")
    args = parser.parse_args()
    try:
        manifest = read_contract(args.manifest, Manifest)
        registry = read_contract(args.approved, ApprovedRegistry)
        if args.state_dir is not None and not (args.state_dir / "agentgate.sqlite3").is_file():
            raise ValueError("Initialized installation state required")
        controls = (
            ControlPlane(Store(args.state_dir / "agentgate.sqlite3")).snapshot()
            if args.state_dir is not None
            else ControlSnapshot(
                Policy(policy_id="artifact-simulation", revision=1),
                read_contract(args.feed, ThreatFeed),
            )
        )
        result = inspect_manifest(manifest, registry, controls)
        print(json.dumps(result))
        raise SystemExit(0 if result["allowed"] else 2)
    except (OSError, ValueError, RecursionError, StorageUnavailable):
        parser.exit(
            1, "Artifact metadata check failed. Inspect the bounded manifest, registry and feed.\n"
        )


if __name__ == "__main__":
    main()
