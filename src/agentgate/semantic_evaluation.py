"""Offline evaluation contracts and metrics; never an authorization decision."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from agentgate.contracts import Contract, SemanticResult
from agentgate.inference_engine import QUESTION_SET, QuestionSet, question_profile
from agentgate.semantics import Backend, validate_result

Label = Literal["task_data", "behavior_instruction"]
EvaluationVersion = Literal["v1", "v2"]
Status = Literal["ok", "abstain", "incomplete", "invalid_output", "unavailable"]
FiniteNonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Case(Contract):
    id: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,60}$")]
    pair_id: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,50}$")]
    language: Literal["en", "pl"]
    case_class: Annotated[str, Field(pattern=r"^[a-z_]{1,50}$")]
    expected: Label
    expected_coverage: Literal["complete", "incomplete"]
    content: Annotated[str, Field(min_length=1, max_length=32768)]

    @model_validator(mode="after")
    def byte_limit(self) -> "Case":
        if len(self.content.encode()) > 32768:
            raise ValueError("Case exceeds worker byte limit")
        return self


class Dataset(Contract):
    schema_version: Literal[1]
    dataset_id: Literal["semantic-heldout-v1", "semantic-heldout-v2"]
    purpose: str
    cases: Annotated[list[Case], Field(min_length=2, max_length=200)]

    @model_validator(mode="after")
    def paired(self) -> "Dataset":
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        for pair_id in {case.pair_id for case in self.cases}:
            pair = [c for c in self.cases if c.pair_id == pair_id]
            if (
                len(pair) != 2
                or {c.language for c in pair} != {"en", "pl"}
                or len({(c.expected, c.expected_coverage, c.case_class) for c in pair}) != 1
            ):
                raise ValueError("Pairs must have matching labels, coverage and EN/PL members")
        return self


class Diagnostics(Contract):
    state_tokens: Annotated[int, Field(ge=0)]
    state_tokens_used: Annotated[int, Field(ge=0)]
    state_tokens_dropped: Annotated[int, Field(ge=0)]
    rendered_tokens: Annotated[int, Field(ge=0, le=1024)]
    required_tokens: Annotated[int, Field(ge=0)]
    preflight_ms: FiniteNonnegative
    predict_ms: FiniteNonnegative
    peak_rss_bytes: Annotated[int, Field(ge=0)]
    cpu_user_seconds: FiniteNonnegative
    cpu_system_seconds: FiniteNonnegative


class Observation(Contract):
    case_id: str
    repetition: Annotated[int, Field(ge=0, le=3)]
    backend: Backend
    status: Status
    question_set_id: QuestionSet = QUESTION_SET
    attempted: bool = True
    elapsed_ms: FiniteNonnegative
    result: SemanticResult | None = None
    diagnostics: Diagnostics | None = None
    error_type: str | None = None

    @model_validator(mode="after")
    def valid_evidence(self) -> "Observation":
        if self.result is None:
            if self.status not in ("unavailable", "invalid_output") or self.diagnostics is not None:
                raise ValueError("Missing inference evidence")
            return self
        result = self.result
        validate_result(
            result, f"{self.case_id}-p{self.repetition}", self.backend, self.question_set_id
        )
        if self.status != result.status or self.diagnostics is None:
            raise ValueError("Result status or diagnostics mismatch")
        diag = self.diagnostics
        if (
            not math.isfinite(result.usage.inference_wall_ms)
            or any(not math.isfinite(v) for v in result.raw_scores.values())
            or diag.state_tokens != diag.state_tokens_used + diag.state_tokens_dropped
            or diag.required_tokens != diag.rendered_tokens + diag.state_tokens_dropped
            or (result.coverage.complete and diag.state_tokens_dropped != 0)
            or (result.coverage.complete and result.usage.input_tokens != diag.rendered_tokens)
        ):
            raise ValueError("Invalid numeric or token evidence")
        return self


def load_frozen(
    root: Path, version: EvaluationVersion = "v1"
) -> tuple[Dataset, dict[str, Any], dict[str, str]]:
    """Reject local changes to the pre-inference corpus, engine and protocol."""
    if version not in ("v1", "v2"):
        raise ValueError("Unknown evaluation version")
    frozen = json.loads((root / f"evaluation/freeze-{version}.json").read_bytes())["files"]
    required = {
        f"evaluation/semantic-heldout-{version}.json",
        f"evaluation/protocol-{version}.json",
        "src/agentgate/inference_engine.py",
        "manifests/model-assets.json",
        "requirements/laya-standard.txt",
        "requirements/laya-coreml.txt",
    }
    if version == "v2":
        required.add("evaluation/development-v2.json")
    if set(frozen) != required or any(digest(root / p) != h for p, h in frozen.items()):
        raise ValueError(
            "Frozen input changed; use a new evaluation version. "
            "Original v1 requires pinned PR23 checkout 639ea1fdb4651894db03eb2a6edefaf8c8a3865a; "
            "see docs/semantic-evaluation.md"
        )
    protocol = json.loads((root / f"evaluation/protocol-{version}.json").read_bytes())
    profile = question_profile(protocol["question_set_id"])
    if (
        protocol["question_set_id"] != f"content-role-{version}"
        or protocol["questions"] != profile.questions
    ):
        raise ValueError("Question differs from the production engine")
    if version == "v2" and (
        protocol["state_content_key"] != profile.state_key
        or protocol["label_mapping"] != profile.labels
    ):
        raise ValueError("Protocol differs from production adapter")
    dataset = Dataset.model_validate_json(
        (root / f"evaluation/semantic-heldout-{version}.json").read_bytes()
    )
    if dataset.dataset_id != f"semantic-heldout-{version}":
        raise ValueError("Dataset version mismatch")
    return dataset, protocol, frozen


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def metrics(cases: list[Case], observations: list[Observation]) -> dict[str, Any]:
    """One first-pass observation per case; no repetition-based sample inflation."""
    by_id = {o.case_id: o for o in observations}
    if (
        len(by_id) != len(observations)
        or set(by_id) != {c.id for c in cases}
        or any(o.repetition != 0 for o in observations)
    ):
        raise ValueError("Metrics require exactly one first-pass observation per case")
    counts: Counter[str] = Counter()
    statuses: Counter[str] = Counter(o.status for o in observations)
    for case in cases:
        obs = by_id[case.id]
        positive = case.expected == "behavior_instruction"
        counts["positive" if positive else "negative"] += 1
        if obs.result and obs.result.coverage.complete:
            counts["complete"] += 1
        if obs.status == "ok" and obs.result:
            predicted = obs.result.selected_labels["content_role"] == "behavior_instruction"
            counts[
                ("tp" if predicted else "fn") if positive else ("fp" if predicted else "tn")
            ] += 1
        else:
            counts["positive_nondecisive" if positive else "negative_nondecisive"] += 1
        actual_complete = bool(obs.result and obs.result.coverage.complete)
        counts["coverage_expectation_matches"] += actual_complete == (
            case.expected_coverage == "complete"
        )
    tp, tn, fp, fn = (counts[key] for key in ("tp", "tn", "fp", "fn"))
    decisive = tp + tn + fp + fn
    return {
        "n": len(cases),
        "positive": counts["positive"],
        "negative": counts["negative"],
        "decisive": decisive,
        "attempted": sum(o.attempted for o in observations),
        "correct": tp + tn,
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "statuses": {
            key: statuses[key]
            for key in ("ok", "abstain", "incomplete", "invalid_output", "unavailable")
        },
        "complete": counts["complete"],
        "coverage_rate": ratio(counts["complete"], len(cases)),
        "coverage_expectation_matches": counts["coverage_expectation_matches"],
        "conditional_accuracy": ratio(tp + tn, decisive),
        "all_case_accuracy": ratio(tp + tn, len(cases)),
        "false_positive_rate": ratio(fp, counts["negative"]),
        "false_negative_rate": ratio(fn, counts["positive"]),
        "conditional_false_positive_rate": ratio(fp, fp + tn),
        "conditional_false_negative_rate": ratio(fn, fn + tp),
        "precision": ratio(tp, tp + fp),
        "recall_all_positive": ratio(tp, counts["positive"]),
        "positive_nondecisive": counts["positive_nondecisive"],
        "negative_nondecisive": counts["negative_nondecisive"],
        "strict_benign_withhold_rate": ratio(counts["negative"] - tn, counts["negative"]),
    }


def slices(dataset: Dataset, observations: list[Observation]) -> dict[str, Any]:
    first = [o for o in observations if o.repetition == 0]
    result = {"all": metrics(dataset.cases, first)}
    for field in ("language", "case_class"):
        for value in sorted({getattr(c, field) for c in dataset.cases}):
            cases = [c for c in dataset.cases if getattr(c, field) == value]
            result[f"{field}:{value}"] = metrics(
                cases, [o for o in first if o.case_id in {c.id for c in cases}]
            )
    for language in ("en", "pl"):
        for cls in sorted({c.case_class for c in dataset.cases}):
            cases = [c for c in dataset.cases if c.language == language and c.case_class == cls]
            if cases:
                result[f"{language}:{cls}"] = metrics(
                    cases, [o for o in first if o.case_id in {c.id for c in cases}]
                )
    return result


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Invalid timing")
    ordered = sorted(values)
    return {
        "n": len(values),
        "p50": ordered[math.ceil(len(values) * 0.5) - 1] if values else None,
        "p95": ordered[math.ceil(len(values) * 0.95) - 1] if values else None,
        "max": ordered[-1] if values else None,
    }


def signature(obs: Observation) -> tuple[str, str | None]:
    return obs.status, obs.result.selected_labels.get("content_role") if obs.result else None


def disagreement(
    dataset: Dataset, left: list[Observation], right: list[Observation]
) -> dict[str, Any]:
    # Validate denominators before comparing; unavailable agreement is not label agreement.
    metrics(dataset.cases, left)
    metrics(dataset.cases, right)
    lmap, rmap = ({o.case_id: o for o in rows} for rows in (left, right))
    comparable = [c.id for c in dataset.cases if lmap[c.id].status == rmap[c.id].status == "ok"]
    differing = [c.id for c in dataset.cases if signature(lmap[c.id]) != signature(rmap[c.id])]
    label_differing = [cid for cid in comparable if signature(lmap[cid]) != signature(rmap[cid])]
    return {
        "n": len(dataset.cases),
        "status_or_label_disagreements": differing,
        "decisive_pairs": len(comparable),
        "decisive_label_disagreements": label_differing,
        "decisive_disagreement_rate": ratio(len(label_differing), len(comparable)),
    }
