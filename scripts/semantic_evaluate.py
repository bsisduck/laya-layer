"""Run one real backend offline, or compare two minimized frozen-corpus reports."""

import argparse
import asyncio
import fcntl
import json
import os
import platform
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from agentgate.contracts import SemanticResult
from agentgate.semantic_evaluation import (
    Diagnostics,
    Observation,
    digest,
    disagreement,
    distribution,
    load_frozen,
    signature,
    slices,
)
from agentgate.semantics import REVISIONS, SemanticInvalid, SemanticRequest

ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_FILES = (
    "scripts/semantic_evaluate.py",
    "scripts/semantic_evaluation_child.py",
    "src/agentgate/semantic_evaluation.py",
    "src/agentgate/semantics.py",
    "src/agentgate/contracts.py",
)


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def committed_inputs(frozen):
    paths = [*frozen, "evaluation/freeze-v1.json", *EVALUATOR_FILES]
    for path in paths:
        committed = subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{path}"])
        if committed != (ROOT / path).read_bytes():
            raise ValueError("Commit evaluation inputs and runner before inference")
    return {
        "commit": git("rev-parse", "HEAD"),
        "freeze_commit": git("log", "-1", "--format=%H", "--", "evaluation/freeze-v1.json"),
        "frozen_sha256": frozen,
        "evaluator_sha256": {p: digest(ROOT / p) for p in EVALUATOR_FILES},
    }


def active_workers():
    # Advisory check in addition to the evaluation lock. Never kill external PIDs.
    output = subprocess.check_output(["ps", "-axo", "pid=,comm=,args="], text=True)
    pids = []
    for line in output.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3 or int(parts[0]) == os.getpid():
            continue
        pid, command, args = parts
        if ("python" in command.lower() or command.endswith("agentgate")) and any(
            name in args
            for name in (
                "inference_engine.py",
                "semantic-worker",
                "semantic_smoke.py",
                "semantic_evaluation_child.py",
                ".runtime/laya-standard/bin/python",
                ".runtime/laya-coreml/bin/python",
            )
        ):
            pids.append(int(pid))
    return pids


class EvaluationLock:
    def __init__(self, assets_root):
        path = assets_root / ".runtime" / "semantic-evaluation.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a+")

    def __enter__(self):
        try:
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if active_workers():
                raise RuntimeError("Another Laya worker is active")
            return self.stream.fileno()
        except BaseException:
            self.stream.close()
            raise

    def __exit__(self, *_):
        # Child inherits the descriptor, so parent death cannot unlock a live child.
        self.stream.close()


async def frame(process, timeout):
    async with asyncio.timeout(timeout):
        line = await process.stdout.readline()
        if not line:
            raise EOFError("Inference child exited")
        return json.loads(line)


async def stop(process):
    if process is not None and process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        async with asyncio.timeout(5):
            await process.wait()


def timing_summary(observations):
    summary = {}
    for phase, selected in (
        ("cold_first_call", observations[:1]),
        ("warm", [o for o in observations if o.repetition > 0]),
    ):
        selected = [o for o in selected if o.attempted]
        summary[phase] = {
            "attempt_wall_ms": distribution([o.elapsed_ms for o in selected]),
            "complete_call_wall_ms": distribution(
                [o.elapsed_ms for o in selected if o.result and o.result.coverage.complete]
            ),
            "preflight_ms": distribution(
                [o.diagnostics.preflight_ms for o in selected if o.diagnostics]
            ),
            "predict_ms": distribution(
                [
                    o.diagnostics.predict_ms
                    for o in selected
                    if o.diagnostics and o.result.coverage.windows_evaluated
                ]
            ),
        }
        for low, high in ((0, 128), (128, 512), (512, 1024), (1024, 100000)):
            rows = [
                o for o in selected if o.diagnostics and low < o.diagnostics.required_tokens <= high
            ]
            summary[phase][f"required_tokens_{low + 1}_{high}"] = {
                "wall_ms": distribution([o.elapsed_ms for o in rows]),
                "inferred": sum(o.result.coverage.windows_evaluated for o in rows),
            }
    return summary


async def run_backend(args, dataset, protocol, provenance):
    report = {
        "schema_version": 1,
        "kind": "real_semantic_evaluation",
        "backend": args.backend,
        "started_at": datetime.now(UTC).isoformat(),
        "provenance": provenance,
        "protocol": protocol,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
        },
        "status": "unavailable",
        "runtime": None,
        "observations": [],
        "limits": {
            "concurrency": 1,
            "token_capacity": 1024,
            "content_bytes": 32768,
            "startup_seconds": 45,
            "call_seconds": 5,
            "process_memory_cap_bytes": None,
            "persistent_semantic_budget": False,
        },
    }
    if platform.system() == "Darwin":
        for key in ("hw.memsize", "machdep.cpu.brand_string"):
            report["environment"][key] = subprocess.check_output(
                ["sysctl", "-n", key], text=True
            ).strip()
    started = time.perf_counter()
    observations = []
    process = None
    scratch = tempfile.TemporaryDirectory(prefix="agentgate-evaluation-")
    failure = "not_started"
    failure_status = "unavailable"
    try:
        with EvaluationLock(args.assets_root) as lock_fd:
            try:
                process = await asyncio.create_subprocess_exec(
                    str(args.runtime_python),
                    str(ROOT / "scripts/semantic_evaluation_child.py"),
                    "--backend",
                    args.backend,
                    "--assets-root",
                    str(args.assets_root),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=65536,
                    pass_fds=(lock_fd,),
                    env=os.environ | {"AGENTGATE_ENGINE_SCRATCH": scratch.name},
                )
                ready = await frame(process, protocol["startup_timeout_seconds"])
                if (
                    ready["status"] != "ready"
                    or ready["backend"] != args.backend
                    or ready["checkpoint_revision"] != REVISIONS[args.backend]
                ):
                    raise ValueError("Invalid startup metadata")
                report["runtime"] = ready
                report["cold_startup_wall_ms"] = (time.perf_counter() - started) * 1000
                failure = None
            except (OSError, ValueError, KeyError, EOFError, TimeoutError) as error:
                failure = "startup_" + type(error).__name__
                await stop(process)
            for repetition in range(protocol["warm_repetitions"] + 1):
                for case in dataset.cases:
                    before = time.perf_counter()
                    result, diagnostics = None, None
                    attempted = failure is None
                    if failure is None:
                        try:
                            request = SemanticRequest(
                                request_id=f"{case.id}-p{repetition}",
                                untrusted_content=case.content,
                            )
                            process.stdin.write(request.model_dump_json().encode() + b"\n")
                            async with asyncio.timeout(protocol["case_timeout_seconds"]):
                                await process.stdin.drain()
                                data = await frame(process, protocol["case_timeout_seconds"])
                            result = SemanticResult.model_validate(data["result"])
                            diagnostics = Diagnostics.model_validate(data["diagnostics"])
                            obs = Observation(
                                case_id=case.id,
                                repetition=repetition,
                                backend=args.backend,
                                status=result.status,
                                result=result,
                                diagnostics=diagnostics,
                                elapsed_ms=(time.perf_counter() - before) * 1000,
                            )
                        except (
                            OSError,
                            ValueError,
                            KeyError,
                            EOFError,
                            TimeoutError,
                            SemanticInvalid,
                        ) as error:
                            failure = "call_" + type(error).__name__
                            failure_status = (
                                "invalid_output"
                                if isinstance(error, (ValueError, KeyError, SemanticInvalid))
                                else "unavailable"
                            )
                            await stop(process)
                    if failure is not None:
                        obs = Observation(
                            case_id=case.id,
                            repetition=repetition,
                            backend=args.backend,
                            status=failure_status,
                            attempted=attempted,
                            error_type=failure,
                            elapsed_ms=(time.perf_counter() - before) * 1000,
                        )
                        # Subsequent cases were not attempted after the unhealthy child.
                        failure, failure_status = "worker_unavailable_after_failure", "unavailable"
                    observations.append(obs)
            await stop(process)
    except (OSError, RuntimeError) as error:
        report["error_type"] = type(error).__name__
        observations = [
            Observation(
                case_id=c.id,
                repetition=r,
                backend=args.backend,
                status="unavailable",
                attempted=False,
                error_type=type(error).__name__,
                elapsed_ms=0,
            )
            for r in range(protocol["warm_repetitions"] + 1)
            for c in dataset.cases
        ]
    finally:
        await stop(process)
        scratch.cleanup()
    report["elapsed_seconds"] = time.perf_counter() - started
    report["observations"] = [o.model_dump(mode="json") for o in observations]
    report["metrics"] = slices(dataset, observations)
    report["timings"] = timing_summary(observations)
    first = {o.case_id: o for o in observations if o.repetition == 0}
    report["repeat_disagreements"] = [
        {"case_id": o.case_id, "repetition": o.repetition}
        for o in observations
        if o.repetition and signature(o) != signature(first[o.case_id])
    ]
    report["resources"] = {
        "child_peak_rss_bytes": max(
            (o.diagnostics.peak_rss_bytes for o in observations if o.diagnostics), default=None
        ),
        "scope": "child process high-water RSS and cumulative CPU; excludes external CoreML services; no device/energy measurement",
    }
    errors = any(o.status in ("invalid_output", "unavailable") for o in observations)
    report["status"] = ("failed" if report["runtime"] else "unavailable") if errors else "measured"
    return report


def compare(paths):
    dataset, protocol, frozen = load_frozen(ROOT)
    reports = [json.loads(path.read_bytes()) for path in paths]
    if {r["backend"] for r in reports} != set(REVISIONS):
        raise ValueError("Comparison requires one report from each backend")
    for report in reports:
        if (
            report["schema_version"] != 1
            or report["kind"] != "real_semantic_evaluation"
            or report["protocol"] != protocol
            or report["provenance"]["frozen_sha256"] != frozen
        ):
            raise ValueError("Incompatible evaluation provenance")
        if report["provenance"]["evaluator_sha256"] != reports[0]["provenance"]["evaluator_sha256"]:
            raise ValueError("Different evaluator implementations")
    rows = [
        [Observation.model_validate(o) for o in r["observations"] if o["repetition"] == 0]
        for r in reports
    ]
    if any(o.backend != r["backend"] for r, obs in zip(reports, rows, strict=True) for o in obs):
        raise ValueError("Wrong backend in observations")
    comparisons = {"all": disagreement(dataset, *rows)}
    for field in ("language", "case_class"):
        for value in sorted({getattr(c, field) for c in dataset.cases}):
            selected = [c for c in dataset.cases if getattr(c, field) == value]
            subset = dataset.model_copy(update={"cases": selected})
            ids = {c.id for c in selected}
            comparisons[f"{field}:{value}"] = disagreement(
                subset, *[[o for o in group if o.case_id in ids] for group in rows]
            )
    return {
        "schema_version": 1,
        "kind": "real_semantic_comparison",
        "reports_sha256": {r["backend"]: digest(p) for r, p in zip(reports, paths, strict=True)},
        "provenance": reports[0]["provenance"],
        "metrics": {
            r["backend"]: slices(dataset, obs) for r, obs in zip(reports, rows, strict=True)
        },
        "disagreement": comparisons["all"],
        "disagreement_slices": comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--backend", choices=list(REVISIONS), required=True)
    run.add_argument("--runtime-python", type=Path, required=True)
    run.add_argument("--assets-root", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    comparison = commands.add_parser("compare")
    comparison.add_argument("reports", type=Path, nargs=2)
    comparison.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Reserve the output before expensive work. Never silently replace evidence.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        if args.command == "run":
            dataset, protocol, frozen = load_frozen(ROOT)
            provenance = committed_inputs(frozen)
            args.assets_root = args.assets_root.resolve()
            args.runtime_python = args.runtime_python.absolute()
            report = asyncio.run(run_backend(args, dataset, protocol, provenance))
        else:
            report = compare(args.reports)
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report.get("status", "compared"), "output": str(args.output)}))
    if report.get("status") in ("failed", "unavailable"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
