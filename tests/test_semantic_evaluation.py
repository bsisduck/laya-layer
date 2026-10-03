"""Deterministic evaluator checks. Synthetic outputs here are not real-model evidence."""

import asyncio
import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentgate.semantic_evaluation import (
    Case,
    Dataset,
    Observation,
    disagreement,
    distribution,
    load_frozen,
    metrics,
    slices,
)
from agentgate.semantics import REVISIONS

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "semantic_evaluate", ROOT / "scripts/semantic_evaluate.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def case(cid, expected="task_data"):
    return Case(
        id=cid,
        pair_id="pair",
        language="en",
        case_class="benign_data",
        expected=expected,
        expected_coverage="complete",
        content="Fixed synthetic text.",
    )


def observation(cid, label="task_data", status="ok", backend="laya_standard"):
    data = dict(case_id=cid, repetition=0, backend=backend, status=status, elapsed_ms=10.0)
    if status == "unavailable":
        return Observation(**data)
    complete = status in ("ok", "abstain")
    scores = {"task_data": 0.1, "behavior_instruction": 0.1, "unclear": 0.1}
    scores[label] = 0.8
    data["result"] = dict(
        request_id=f"{cid}-p0",
        backend=backend,
        checkpoint_revision=REVISIONS[backend],
        question_set_id="content-role-v1",
        status=status,
        selected_labels={"content_role": label} if complete else {},
        raw_scores=scores if complete else {},
        coverage=dict(
            complete=complete,
            windows_evaluated=int(complete),
            input_truncated=not complete,
            options_collapsed=False,
        ),
        usage=dict(input_tokens=100 if complete else 0, output_tokens=0, inference_wall_ms=8),
    )
    data["diagnostics"] = dict(
        state_tokens=30 if complete else 1500,
        state_tokens_used=30 if complete else 900,
        state_tokens_dropped=0 if complete else 600,
        rendered_tokens=100 if complete else 1024,
        required_tokens=100 if complete else 1624,
        preflight_ms=1,
        predict_ms=7 if complete else 0,
        peak_rss_bytes=123,
        cpu_user_seconds=1,
        cpu_system_seconds=0.5,
    )
    return Observation.model_validate(data)


def test_metric_denominators_and_nondecisive_results():
    cases = [case(str(i), "behavior_instruction" if i % 2 == 0 else "task_data") for i in range(8)]
    rows = [
        observation("0", "behavior_instruction"),
        observation("1"),
        observation("2"),
        observation("3", "behavior_instruction"),
        observation("4", "unclear", "abstain"),
        observation("5", "unclear", "abstain"),
        observation("6", status="unavailable"),
        observation("7", status="incomplete"),
    ]
    result = metrics(cases, rows)
    assert result["confusion"] == dict(tp=1, tn=1, fp=1, fn=1)
    assert result["n"] == 8 and result["decisive"] == 4 and result["complete"] == 6
    assert result["conditional_accuracy"] == 0.5
    assert (
        result["all_case_accuracy"]
        == result["false_positive_rate"]
        == result["false_negative_rate"]
        == 0.25
    )
    assert result["recall_all_positive"] == 0.25 and result["precision"] == 0.5
    assert result["positive_nondecisive"] == result["negative_nondecisive"] == 2
    assert result["strict_benign_withhold_rate"] == 0.75
    assert (
        metrics([case("a")], [observation("a", status="unavailable")])["conditional_accuracy"]
        is None
    )
    assert metrics([case("a")], [observation("a")])["false_negative_rate"] is None
    with pytest.raises(ValueError):
        metrics(cases, rows + [rows[0]])
    with pytest.raises(ValueError):
        metrics(cases, rows[:-1])
    with pytest.raises(ValueError):
        metrics([case("a")], [observation("a").model_copy(update={"repetition": 1})])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["result"]["raw_scores"].update(task_data=float("nan")),
        lambda d: d["result"]["usage"].update(inference_wall_ms=float("inf")),
        lambda d: d["diagnostics"].update(predict_ms=float("nan")),
        lambda d: d["result"].update(request_id="wrong"),
        lambda d: d["result"]["coverage"].update(input_truncated=True),
        lambda d: d["result"]["usage"].update(input_tokens=1025),
        lambda d: d["diagnostics"].update(state_tokens_dropped=1),
        lambda d: d["result"]["raw_scores"].update(task_data=0.01),
        lambda d: d.update(status="abstain"),
    ],
)
def test_reject_invalid_measurements(mutation):
    data = observation("a").model_dump()
    mutation(data)
    with pytest.raises((ValueError, runner.SemanticInvalid)):
        Observation.model_validate(data)


def test_corpus_and_freeze_validation(tmp_path):
    dataset, _, frozen = load_frozen(ROOT)
    assert len(dataset.cases) == 26
    loading = json.loads((ROOT / "tests/fixtures/semantic-loading.json").read_text())
    assert not {c.content for c in dataset.cases} & {c["state"] for c in loading["cases"]}
    for path in [*frozen, "evaluation/freeze-v1.json"]:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    assert load_frozen(tmp_path)[0] == dataset
    (tmp_path / "evaluation/semantic-heldout-v1.json").write_text("{}")
    with pytest.raises(ValueError, match="Frozen"):
        load_frozen(tmp_path)
    value = dataset.model_dump()
    value["cases"][1]["language"] = "en"
    with pytest.raises(ValueError, match="Pairs"):
        Dataset.model_validate(value)
    value = dataset.model_dump()
    value["cases"][1]["id"] = value["cases"][0]["id"]
    with pytest.raises(ValueError, match="Duplicate"):
        Dataset.model_validate(value)
    with pytest.raises(ValueError, match="byte limit"):
        Case.model_validate(case("a").model_dump() | {"content": "ą" * 20000})


def test_slices_disagreement_and_percentiles():
    dataset, _, _ = load_frozen(ROOT)
    left = [observation(c.id, c.expected) for c in dataset.cases]
    right = [observation(c.id, c.expected, backend="laya_coreml") for c in dataset.cases]
    right[0] = observation(dataset.cases[0].id, "unclear", "abstain", "laya_coreml")
    result = disagreement(dataset, left, right)
    assert result["n"] == 26 and result["decisive_pairs"] == 25
    assert result["status_or_label_disagreements"] == [dataset.cases[0].id]
    assert result["decisive_label_disagreements"] == []
    assert slices(dataset, left)["language:pl"]["n"] == 13
    assert slices(dataset, left)["en:security_quotation"]["n"] == 2
    assert distribution([1, 2, 3, 4, 5]) == dict(n=5, p50=3, p95=5, max=5)
    assert distribution([]) == dict(n=0, p50=None, p95=None, max=None)
    with pytest.raises(ValueError):
        distribution([float("inf")])


def test_missing_runtime_reports_all_cases_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "active_workers", lambda: [])
    dataset, protocol, _ = load_frozen(ROOT)
    args = SimpleNamespace(
        backend="laya_standard", assets_root=tmp_path, runtime_python=tmp_path / "missing"
    )
    result = asyncio.run(runner.run_backend(args, dataset, protocol, {}))
    assert result["status"] == "unavailable" and result["runtime"] is None
    assert len(result["observations"]) == 104
    assert result["metrics"]["all"]["n"] == 26
    assert result["metrics"]["all"]["statuses"]["unavailable"] == 26
    assert all(c.content not in json.dumps(result, ensure_ascii=False) for c in dataset.cases)


def test_lock_never_kills_external_workers(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "active_workers", lambda: [])
    with runner.EvaluationLock(tmp_path):
        with pytest.raises(BlockingIOError), runner.EvaluationLock(tmp_path):
            pytest.fail("Second backend acquired the lock")
    monkeypatch.setattr(runner, "active_workers", lambda: [999999])
    with pytest.raises(RuntimeError, match="active"), runner.EvaluationLock(tmp_path):
        pytest.fail("Ignored an existing worker")


def test_malformed_child_is_reaped_and_no_case_is_dropped(tmp_path, monkeypatch):
    """Actual subprocess; deliberately invalid deterministic output, never model evidence."""
    monkeypatch.setattr(runner, "active_workers", lambda: [])
    dataset, protocol, _ = load_frozen(ROOT)
    original_spawn = asyncio.create_subprocess_exec
    processes = []
    ready = dict(
        status="ready", backend="laya_standard", checkpoint_revision=REVISIONS["laya_standard"]
    )
    fixture = f'import json,sys,time; print({json.dumps(json.dumps(ready))},flush=True); sys.stdin.readline(); print("{{}}",flush=True); time.sleep(30)'

    async def spawn(*args, **kwargs):
        process = await original_spawn(sys.executable, "-c", fixture, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", spawn)
    args = SimpleNamespace(
        backend="laya_standard", assets_root=tmp_path, runtime_python=Path(sys.executable)
    )
    report = asyncio.run(runner.run_backend(args, dataset, protocol, {}))
    assert report["status"] == "failed"
    assert report["observations"][0]["status"] == "invalid_output"
    assert report["metrics"]["all"]["statuses"]["unavailable"] == 25
    assert processes[0].returncode is not None


def test_comparison_rejects_unmatched_provenance(tmp_path, monkeypatch):
    dataset, protocol, frozen = load_frozen(ROOT)
    reports = []
    for backend in REVISIONS:
        reports.append(
            dict(
                schema_version=1,
                kind="real_semantic_evaluation",
                backend=backend,
                protocol=protocol,
                provenance=dict(frozen_sha256=frozen, evaluator_sha256={}),
                observations=[
                    observation(c.id, c.expected, backend=backend).model_dump()
                    for c in dataset.cases
                ],
            )
        )
    paths = [tmp_path / "a.json", tmp_path / "b.json"]
    for path, report in zip(paths, reports, strict=True):
        path.write_text(json.dumps(report))
    assert runner.compare(paths)["disagreement"]["n"] == 26
    bad = copy.deepcopy(reports[1])
    bad["provenance"]["frozen_sha256"] = {}
    paths[1].write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="provenance"):
        runner.compare(paths)


def test_timeout_reaps_owned_process_and_retains_denominator(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "active_workers", lambda: [])
    dataset, protocol, _ = load_frozen(ROOT)
    protocol = protocol | {"case_timeout_seconds": 0.03}
    original_spawn = asyncio.create_subprocess_exec
    processes = []
    ready = dict(
        status="ready", backend="laya_standard", checkpoint_revision=REVISIONS["laya_standard"]
    )
    fixture = f"import sys,time; print({json.dumps(json.dumps(ready))},flush=True); sys.stdin.readline(); time.sleep(30)"

    async def spawn(*args, **kwargs):
        process = await original_spawn(sys.executable, "-c", fixture, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", spawn)
    args = SimpleNamespace(
        backend="laya_standard", assets_root=tmp_path, runtime_python=Path(sys.executable)
    )
    report = asyncio.run(runner.run_backend(args, dataset, protocol, {}))
    assert report["status"] == "failed"
    assert report["observations"][0]["error_type"] == "call_TimeoutError"
    assert report["metrics"]["all"]["attempted"] == 1
    assert report["metrics"]["all"]["statuses"]["unavailable"] == 26
    assert report["timings"]["warm"]["attempt_wall_ms"]["n"] == 0
    assert processes[0].returncode is not None
