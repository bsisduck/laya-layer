"""Strict sidecar provenance and actual node reconciliation, without semantic inference."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from agentgate.contracts import Contract
from agentgate.threat_taxonomy import LAYERS, LEVELS, OWASP, VERSION, taxonomy_digest

DATASETS = {
    "acceptance": ("docs/acceptance-inventory.json", None, None),
    "semantic-heldout-v1": (
        "evaluation/semantic-heldout-v1.json",
        "evaluation/freeze-v1.json",
        "content-role-v1",
    ),
    "semantic-heldout-v2": (
        "evaluation/semantic-heldout-v2.json",
        "evaluation/freeze-v2.json",
        "content-role-v2",
    ),
}


class Dataset(Contract):
    id: str
    path: str
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    frozen_manifest: str | None
    question_set_id: str | None
    evidence: str


class Scenario(Contract):
    dataset: str
    id: str
    level: Literal["L0", "L1", "L2", "L3", "L4", "L5"]
    layers: Annotated[list[str], Field(min_length=1, max_length=7)]
    owasp: Annotated[list[str], Field(min_length=1, max_length=20)]
    rationale: Annotated[str, Field(min_length=1, max_length=512)]

    @model_validator(mode="after")
    def valid_axes(self):
        if len(set(self.layers)) != len(self.layers) or not set(self.layers) <= {
            i for i, *_ in LAYERS
        }:
            raise ValueError("Invalid or duplicate layer")
        if len(set(self.owasp)) != len(self.owasp) or not set(self.owasp) <= set(OWASP):
            raise ValueError("Invalid or duplicate OWASP edition/category")
        return self


class Index(Contract):
    schema_version: Literal[1]
    taxonomy_version: Literal["laya-threat-v1"]
    datasets: Annotated[list[Dataset], Field(min_length=3, max_length=3)]
    cases: Annotated[list[Scenario], Field(min_length=102, max_length=102)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def load_index(root: Path, path: Path | None = None) -> Index:
    path = path or root / "testdata/test-cases.json"
    if path.stat().st_size > 131072:
        raise ValueError("Metadata index exceeds 128 KiB")
    value = json.loads(path.read_bytes(), object_pairs_hook=unique_object)
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
        raise ValueError("Metadata schema version must be an integer")
    index = Index.model_validate_json(json.dumps(value, allow_nan=False))
    if {d.id for d in index.datasets} != set(DATASETS):
        raise ValueError("Exact dataset set required")
    expected = set()
    for dataset in index.datasets:
        corpus, freeze, question = DATASETS[dataset.id]
        if (dataset.path, dataset.frozen_manifest, dataset.question_set_id) != (
            corpus,
            freeze,
            question,
        ):
            raise ValueError("Dataset provenance reference drift")
        current = digest(root / corpus)
        if dataset.sha256 != current:
            raise ValueError("Corpus byte hash mismatch")
        value = json.loads((root / corpus).read_bytes())
        if freeze:
            manifest = json.loads((root / freeze).read_bytes())
            protocol = json.loads(
                (root / f"evaluation/protocol-{dataset.id[-2:]}.json").read_bytes()
            )
            if (
                manifest["schema_version"] != 1
                or manifest["files"][corpus] != current
                or value["dataset_id"] != dataset.id
                or protocol["question_set_id"] != question
            ):
                raise ValueError("Frozen corpus/question provenance mismatch")
        ids = [c["id"] for c in value["cases"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source case")
        expected.update((dataset.id, i) for i in ids)
    actual = [(c.dataset, c.id) for c in index.cases]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Exact unique complete scenario references required")
    return index


def reconcile(selectors, capture, exit_code):
    """All three phases exactly once for every required collected parametrized node."""
    collected = capture.get("collected", [])
    selected = capture.get("selected", [])
    reports = capture.get("reports", [])
    problems = []
    if not capture.get("finished") or capture.get("collection_errors") or exit_code:
        problems.append("execution_or_collection_error")
    if len(collected) != len(set(collected)) or len(selected) != len(set(selected)):
        problems.append("duplicate_collection")
    if set(selected) != set(collected) or capture.get("deselected"):
        problems.append("deselected_required_nodes")
    if any(not any(n == s or n.startswith(s + "[") for s in selectors) for n in collected):
        problems.append("unexpected_collected_node")
    if any(r["nodeid"] not in collected for r in reports):
        problems.append("unexpected_observation")
    nodes = {}
    for node in collected:
        phases = [r for r in reports if r["nodeid"] == node]
        counts = Counter(r["when"] for r in phases)
        if any(r["outcome"] == "failed" for r in phases):
            status = "failed"
        elif any(r["outcome"] == "skipped" for r in phases):
            status = "skipped"
        elif counts == {"setup": 1, "call": 1, "teardown": 1} and all(
            r["outcome"] == "passed" for r in phases
        ):
            status = "passed"
        else:
            status = "incomplete"
        nodes[node] = status
    checks = {}
    for selector in selectors:
        matched = {n: s for n, s in nodes.items() if n == selector or n.startswith(selector + "[")}
        if not matched:
            status = "missing"
        elif problems:
            status = "incomplete"
        elif all(s == "passed" for s in matched.values()):
            status = "passed"
        else:
            status = next(s for s in ("failed", "skipped", "incomplete") if s in matched.values())
        checks[selector] = {"status": status, "expected_nodes": sorted(matched)}
    return {
        "problems": problems,
        "selectors": checks,
        "nodes": nodes,
        "expected_collected_nodes": collected,
        "selected_nodes": selected,
        "deselected_nodes": capture.get("deselected", []),
        "phase_observations": reports,
    }


def summarize(index, inventory, reconciliation=None):
    mapped = {c["id"]: c for c in inventory["cases"]}

    def group(cases):
        kinds = Counter()
        checks = Counter()
        nodes = set()
        for case in cases:
            if case.dataset != "acceptance":
                kinds["semantic_declared_measured_elsewhere"] += 1
                checks["not_run"] += 1
                continue
            source = mapped[case.id]
            kinds[source["kind"]] += 1
            if not source["tests"]:
                checks["not_run"] += 1
                continue
            if reconciliation is None:
                checks["not_run"] += 1
                continue
            statuses = [reconciliation["selectors"][s]["status"] for s in source["tests"]]
            status = (
                "passed"
                if all(s == "passed" for s in statuses)
                else next(
                    s for s in ("failed", "skipped", "missing", "incomplete") if s in statuses
                )
            )
            # These are narrow check statuses; readiness is always the original kind.
            checks[status] += 1
            for selector in source["tests"]:
                nodes.update(reconciliation["selectors"][selector]["expected_nodes"])
        return {
            "declared_scenarios": len(cases),
            "evidence_kind_counts": dict(kinds),
            "control_check_status_counts": dict(checks),
            "unique_pytest_nodes": len(nodes),
            "unique_collected_pytest_nodes": len(nodes),
            "unique_observed_pytest_nodes": len(
                nodes & {r["nodeid"] for r in reconciliation["phase_observations"]}
            )
            if reconciliation
            else 0,
            "pytest_node_status_counts": dict(Counter(reconciliation["nodes"][n] for n in nodes))
            if reconciliation
            else {},
        }

    return {
        "schema_version": 1,
        "taxonomy_version": VERSION,
        "taxonomy_sha256": taxonomy_digest(),
        "semantic_execution": "not_run; measurements remain in existing evidence documents",
        "layer_totals": "overlapping; never sum as independent attacks",
        "pytest_denominator": "unique collected nodes; shared checks are not independent attack samples",
        "datasets": [d.model_dump(mode="json") for d in index.datasets],
        "by_level": {i: group([c for c in index.cases if c.level == i]) for i, *_ in LEVELS},
        "by_layer": {i: group([c for c in index.cases if i in c.layers]) for i, *_ in LAYERS},
        "scenario_readiness": {c["id"]: c["kind"] for c in inventory["cases"]},
    }
