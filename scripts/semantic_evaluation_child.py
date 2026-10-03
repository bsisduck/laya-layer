"""Private measured adapter for the actual frozen engine in an isolated runtime."""

import argparse
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentgate.inference_engine import PROFILES, QUESTION_SET, evaluate  # noqa: E402


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resources():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "peak_rss_bytes": int(usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024)),
        "cpu_user_seconds": usage.ru_utime,
        "cpu_system_seconds": usage.ru_stime,
    }


class MeasuredCommon:
    def __init__(self, common):
        self.common = common
        self.diagnostics = {}

    def __getattr__(self, name):
        return getattr(self.common, name)

    def build_sequence(self, *args, **kwargs):
        started = time.perf_counter()
        result = self.common.build_sequence(*args, **kwargs)
        ids, _, _, stats = result
        self.diagnostics = {
            "state_tokens": stats["state_tokens"],
            "state_tokens_used": stats["state_tokens_used"],
            "state_tokens_dropped": stats["state_tokens_dropped"],
            "rendered_tokens": len(ids),
            "required_tokens": len(ids) + stats["state_tokens_dropped"],
            "preflight_ms": (time.perf_counter() - started) * 1000,
        }
        return result


class MeasuredModel:
    def __init__(self, model):
        self.model = model
        self.predict_ms = 0.0

    def __getattr__(self, name):
        return getattr(self.model, name)

    def predict(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return self.model.predict(*args, **kwargs)
        finally:
            self.predict_ms = (time.perf_counter() - started) * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["laya_standard", "laya_coreml"], required=True)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--question-set", choices=list(PROFILES), default=QUESTION_SET)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stdout = sys.stdout
    os.environ.update(
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
    )
    start = time.perf_counter()
    with contextlib.redirect_stdout(sys.stderr):
        if args.backend == "laya_coreml" and (
            sys.platform != "darwin" or platform.machine() != "arm64"
        ):
            raise ValueError("CoreML requires native Apple Silicon macOS")
        metadata = json.loads((root / "manifests/model-assets.json").read_bytes())["models"][
            args.backend
        ]
        directory = args.assets_root / metadata["directory"]
        for name, expected in metadata["files"].items():
            path = directory / name
            if path.stat().st_size != expected["bytes"] or digest(path) != expected["sha256"]:
                raise ValueError("Asset digest mismatch")
        verified_ms = (time.perf_counter() - start) * 1000
        requirement = "laya-standard.txt" if args.backend == "laya_standard" else "laya-coreml.txt"
        versions = {}
        for line in (root / "requirements" / requirement).read_text().splitlines():
            name, expected_version = line.split("==")
            versions[name] = importlib.metadata.version(name)
            if versions[name] != expected_version:
                raise ValueError("Runtime differs from locked requirements")
        package = "laya" if args.backend == "laya_standard" else "laya-coreml"
        dist = importlib.metadata.distribution(package)
        runtime_files = {
            str(f): digest(Path(dist.locate_file(f)))
            for f in dist.files
            if f.suffix in (".py", ".so", ".dylib") and ".." not in f.parts
        }
        if not runtime_files:
            raise ValueError("Missing runtime source provenance")
        load_start = time.perf_counter()
        normalized = None
        if args.backend == "laya_standard":
            runtime = Path(os.environ["AGENTGATE_ENGINE_SCRATCH"]) / "checkpoint"
            shutil.copytree(directory, runtime, ignore=shutil.ignore_patterns(".cache"))
            model = importlib.import_module("laya").load(str(runtime), device="cpu")
            normalized = digest(runtime / "tokenizer/tokenizer_config.json")
            common = importlib.import_module("laya.common")
        else:
            model = importlib.import_module("laya_coreml").load(
                str(directory), local_files_only=True, compute_units="cpu_gpu"
            )
            common = importlib.import_module("laya_coreml.common")
        if model.cfg["max_len"] != 1024:
            raise ValueError("Unexpected capacity")
        ready = {
            "status": "ready",
            "question_set_id": args.question_set,
            "backend": args.backend,
            "checkpoint_revision": metadata["revision"],
            "assets_verified": len(metadata["files"]),
            "assets_sha256": {name: entry["sha256"] for name, entry in metadata["files"].items()},
            "runtime_versions": versions,
            "runtime_files_sha256": runtime_files,
            "runtime_sha256": hashlib.sha256(
                json.dumps(runtime_files, sort_keys=True).encode()
            ).hexdigest(),
            "normalized_tokenizer_sha256": normalized,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "compute": "cpu" if args.backend == "laya_standard" else "cpu_gpu_requested",
            "asset_verification_ms": verified_ms,
            "load_ms": (time.perf_counter() - load_start) * 1000,
            "startup_resources": resources(),
        }
        print(json.dumps(ready, allow_nan=False), file=stdout, flush=True)
        measured_model, measured_common = MeasuredModel(model), MeasuredCommon(common)
        for line in sys.stdin.buffer:
            if len(line) > 65536:
                raise ValueError("Oversized frame")
            request = json.loads(line)
            if request.get("question_set_id", QUESTION_SET) != args.question_set:
                raise ValueError("Mismatched question profile")
            measured_model.predict_ms = 0.0
            result = evaluate(
                measured_model, measured_common, request, args.backend, metadata["revision"]
            )
            response = {
                "result": result,
                "diagnostics": measured_common.diagnostics
                | resources()
                | {"predict_ms": measured_model.predict_ms},
            }
            print(json.dumps(response, allow_nan=False), file=stdout, flush=True)


if __name__ == "__main__":
    main()
