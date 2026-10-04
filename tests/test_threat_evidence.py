"""Metadata/provenance and complete execution regressions; no classifier inference."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from acceptance_matrix import load_inventory  # noqa: E402
from threat_evidence import load_index, reconcile, summarize  # noqa: E402


def capture(nodes):
    return {
        "finished": True,
        "collected": nodes,
        "selected": nodes,
        "deselected": [],
        "collection_errors": [],
        "reports": [
            {"nodeid": n, "when": phase, "outcome": "passed"}
            for n in nodes
            for phase in ("setup", "call", "teardown")
        ],
    }


def test_sidecar_exact_102_references_and_frozen_provenance():
    index = load_index(ROOT)
    assert len(index.cases) == 102
    assert [
        sum(c.dataset == d for c in index.cases)
        for d in ("acceptance", "semantic-heldout-v1", "semantic-heldout-v2")
    ] == [48, 26, 28]
    assert [d.sha256 for d in index.datasets[1:]] == [
        "40a9efa421337c7a4fb27f036ac87311089b6bc8f0da533bb7296dfdc08c3d4e",
        "c169fb6ec25ef1d3c0ab60444054443b8acc36ee695c9ffbcf15a949e7fdd286",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "missing",
        "unknown",
        "layer",
        "level",
        "edition",
        "hash",
        "question",
        "manifest",
        "extra",
        "boolean_version",
    ],
)
def test_invalid_metadata_fails_instead_of_plausible_empty_chart(tmp_path, mutation):
    value = json.loads((ROOT / "testdata/test-cases.json").read_bytes())
    if mutation == "boolean_version":
        value["schema_version"] = True
    elif mutation == "duplicate":
        value["cases"][-1] = value["cases"][0]
    elif mutation == "missing":
        value["cases"].pop()
    elif mutation == "unknown":
        value["cases"][0]["id"] = "T49"
    elif mutation == "layer":
        value["cases"][0]["layers"] = ["permissions"]
    elif mutation == "level":
        value["cases"][0]["level"] = "L6"
    elif mutation == "edition":
        value["cases"][0]["owasp"] = ["LLM01:2026"]
    elif mutation == "hash":
        value["datasets"][1]["sha256"] = "0" * 64
    elif mutation == "question":
        value["datasets"][1]["question_set_id"] = "content-role-v2"
    elif mutation == "manifest":
        value["datasets"][1]["frozen_manifest"] = "evaluation/freeze-v2.json"
    elif mutation == "extra":
        value["cases"][0]["content"] = "do not duplicate corpus"
    path = tmp_path / "index.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        load_index(ROOT, path)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_parameter",
        "skip",
        "failure",
        "setup",
        "teardown",
        "duplicate",
        "unexpected",
        "deselected",
        "collection_error",
        "early_exit",
    ],
)
def test_incomplete_observations_never_pass(fault):
    selector = "tests/test_case.py::test_case"
    data = capture([selector + "[a]", selector + "[b]"])
    if fault == "missing_parameter":
        data["reports"] = data["reports"][:3]
    elif fault == "skip":
        data["reports"][4]["outcome"] = "skipped"
    elif fault == "failure":
        data["reports"][4]["outcome"] = "failed"
    elif fault == "setup":
        data["reports"][3]["outcome"] = "failed"
    elif fault == "teardown":
        data["reports"][5]["outcome"] = "failed"
    elif fault == "duplicate":
        data["reports"].append(copy.copy(data["reports"][4]))
    elif fault == "unexpected":
        data["reports"].append({"nodeid": "unexpected", "when": "call", "outcome": "passed"})
    elif fault == "deselected":
        data["selected"] = data["selected"][:1]
        data["deselected"] = data["collected"][1:]
    elif fault == "collection_error":
        data["collection_errors"] = ["broken.py"]
    elif fault == "early_exit":
        data["finished"] = False
    result = reconcile([selector], data, 0)
    assert result["selectors"][selector]["status"] != "passed"
    assert reconcile(["missing"], capture([]), 0)["selectors"]["missing"]["status"] == "missing"


def test_real_hook_captures_deselection_and_parameter_phases(tmp_path):
    test = tmp_path / "test_nodes.py"
    test.write_text(
        'import pytest\n@pytest.mark.parametrize("value", [1,2], ids=["keep","drop"])\ndef test_nodes(value): assert value > 0\n'
    )
    output = tmp_path / "capture.json"
    env = dict(
        os.environ, PYTHONPATH=str(ROOT / "scripts"), AGENTGATE_ACCEPTANCE_CAPTURE=str(output)
    )
    env.pop("PYTEST_ADDOPTS", None)
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "acceptance_capture",
            str(test),
            "-k",
            "not drop",
            "-q",
        ],
        env=env,
        capture_output=True,
        timeout=30,
    )
    assert run.returncode == 0
    data = json.loads(output.read_bytes())
    assert len(data["collected"]) == 2 and len(data["selected"]) == 1
    assert len(data["deselected"]) == 1 and len(data["reports"]) == 3
    selector = str(test) + "::test_nodes"
    # pytest formats external paths relative to its actual root; use the observed node prefix.
    selector = data["collected"][0].split("[")[0]
    assert reconcile([selector], data, 0)["selectors"][selector]["status"] == "incomplete"


def test_group_denominators_deduplicate_overlap_and_preserve_readiness():
    index = load_index(ROOT)
    inventory = load_inventory()
    selectors = sorted({s for c in inventory["cases"] for s in c["tests"]})
    result = reconcile(selectors, capture(selectors), 0)
    evidence = summarize(index, inventory, result)
    assert sum(v["declared_scenarios"] for v in evidence["by_level"].values()) == 102
    assert sum(v["declared_scenarios"] for v in evidence["by_layer"].values()) > 102
    assert evidence["scenario_readiness"]["T30"] == "partial"
    assert evidence["scenario_readiness"]["T37"] == "measured"
    assert evidence["scenario_readiness"]["T42"] == "gap"
    assert evidence["by_layer"]["input"]["control_check_status_counts"]["not_run"] >= 54
    assert evidence["by_layer"]["data"]["unique_pytest_nodes"] == len(
        {
            s
            for c in index.cases
            if c.dataset == "acceptance" and "data" in c.layers
            for s in next(i for i in inventory["cases"] if i["id"] == c.id)["tests"]
        }
    )


def test_embedded_attack_and_capacity_metadata_meaning():
    cases = {(c.dataset, c.id): c for c in load_index(ROOT).cases}
    for dataset, ids in (
        ("semantic-heldout-v1", ("long-en", "long-pl")),
        ("semantic-heldout-v2", ("appendix-en", "appendix-pl")),
    ):
        for case_id in ids:
            case = cases[dataset, case_id]
            assert case.level == "L3"
            assert "Embedded instruction" in case.rationale
            assert "LLM01:2025" in case.owasp and "LLM02:2025" in case.owasp
    for dataset, ids in (
        ("semantic-heldout-v1", ("overflow-en", "overflow-pl")),
        ("semantic-heldout-v2", ("astronomy-en", "astronomy-pl")),
    ):
        for case_id in ids:
            case = cases[dataset, case_id]
            assert case.level == "L5" and "consumption" in case.layers
            assert case.owasp == ["LLM10:2025"]
    for case_id in ("T11", "T12", "T13"):
        assert cases["acceptance", case_id].owasp == ["LLM02:2025"]
    for dataset, case_id in (
        ("semantic-heldout-v1", "override-en"),
        ("semantic-heldout-v2", "admin-pl"),
    ):
        assert cases[dataset, case_id].level == "L1"
        assert "L3 overlap" in cases[dataset, case_id].rationale
