"""Asset-verified, real inference loading spike; not a security-accuracy evaluation."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=["laya_standard", "laya_coreml"])
    parser.add_argument(
        "--download", action="store_true", help="Download the pinned assets, then exit"
    )
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    metadata = json.loads((ROOT / "manifests/model-assets.json").read_text())["models"][
        args.backend
    ]
    directory = ROOT / metadata["directory"]
    if args.download:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=metadata["repository"],
            revision=metadata["revision"],
            local_dir=directory,
            allow_patterns=list(metadata["files"]),
            token=False,
        )
    for name, expected in metadata["files"].items():
        path = directory / name
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if path.stat().st_size != expected["bytes"] or digest != expected["sha256"]:
            raise SystemExit(f"Asset verification failed: {name}")
    if args.download:
        print(f"Verified {len(metadata['files'])} pinned files for {args.backend}")
        return

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    report = {
        "kind": "real_inference_loading_spike",
        "backend": args.backend,
        "repository": metadata["repository"],
        "revision": metadata["revision"],
        "assets_verified": True,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "status": "failed",
        "cases": [],
    }
    started = time.perf_counter()
    scratch = None
    try:
        if args.backend == "laya_standard":
            import laya

            report["runtime_version"] = importlib.metadata.version("laya")
            # Laya normalizes tokenizer_config.json in place. Preserve the verified
            # source snapshot and record the derived input actually used by the runtime.
            scratch = tempfile.TemporaryDirectory(prefix="agentgate-laya-")
            runtime_directory = Path(scratch.name) / "checkpoint"
            shutil.copytree(directory, runtime_directory, ignore=shutil.ignore_patterns(".cache"))
            model = laya.load(str(runtime_directory), device="cpu")
            normalized = runtime_directory / "tokenizer/tokenizer_config.json"
            report["normalized_tokenizer_config_sha256"] = hashlib.sha256(
                normalized.read_bytes()
            ).hexdigest()
            report["tokenizer_normalization"] = "upstream Laya normalization on a disposable copy"
            report["compute"] = str(model.device)
        else:
            import laya_coreml

            report["runtime_version"] = importlib.metadata.version("laya-coreml")
            model = laya_coreml.load(str(directory), local_files_only=True, compute_units="cpu_gpu")
            report["compute"] = "cpu_gpu_requested; per-operation placement unmeasured"
        report["load_seconds"] = time.perf_counter() - started
        fixture_bytes = (ROOT / "tests/fixtures/semantic-loading.json").read_bytes()
        report["fixture_sha256"] = hashlib.sha256(fixture_bytes).hexdigest()
        fixtures = json.loads(fixture_bytes)
        for case in fixtures["cases"]:
            before = time.perf_counter()
            if args.backend == "laya_standard":
                result = model.predict(case["state"], fixtures["questions"], max_len=1024)
            else:
                result = model.predict(case["state"], fixtures["questions"])
            choice = result["answers"]["content_role"]["choice"]
            if choice not in fixtures["questions"]["content_role"]["criteria"]:
                raise ValueError("Model returned an unknown choice")
            report["cases"].append(
                {
                    "id": case["id"],
                    "expected": case["expected"],
                    "actual": choice,
                    "matches": choice == case["expected"],
                    "wall_seconds": time.perf_counter() - before,
                    "answers": result["answers"],
                    "usage": result.get("usage"),
                }
            )
        report["status"] = "loaded_and_predicted"
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = str(error)[:1000]
    finally:
        if scratch is not None:
            scratch.cleanup()
    report["total_seconds"] = time.perf_counter() - started
    output = ROOT / "reports/generated" / f"{args.backend}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {"status": report["status"], "report": str(output), "cases": len(report["cases"])}
        )
    )
    if report["status"] != "loaded_and_predicted":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
