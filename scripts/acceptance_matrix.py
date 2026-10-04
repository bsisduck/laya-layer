"""Map architecture T01–T48 to evidence; run control tests without model inference."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from threat_evidence import digest, load_index, reconcile, summarize

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/acceptance-inventory.json"


def load_inventory() -> dict:
    inventory = json.loads(MANIFEST.read_text())
    cases = inventory["cases"]
    if inventory["schema_version"] != 1 or [c["id"] for c in cases] != [
        f"T{number:02d}" for number in range(1, 49)
    ]:
        raise ValueError("Expected schema 1 and exactly ordered T01–T48")
    architecture = (ROOT / inventory["architecture"]).read_text()
    declared = {
        match[1]: (match[2], match[3])
        for match in re.finditer(r"^\| (T\d{2}) \| (.*?) \| (.*?) \|$", architecture, re.M)
    }
    fixture = json.loads((ROOT / inventory["evaluation_fixture"]).read_text())
    fixture_ids = {case["id"] for case in fixture["cases"]}
    v2_fixture = json.loads((ROOT / "evaluation/semantic-heldout-v2.json").read_text())
    v2_ids = {case["id"] for case in v2_fixture["cases"]}
    for case in cases:
        if (case["case"], case["expected"]) != declared.get(case["id"]):
            raise ValueError(f"{case['id']}: architecture case/assertion drift")
        if case["kind"] not in {"control", "partial", "measured", "pending", "gap"}:
            raise ValueError(f"{case['id']}: unknown evidence kind")
        if case["kind"] == "control" and not case["tests"]:
            raise ValueError(f"{case['id']}: control has no executable check")
        if case["kind"] == "measured" and not case["evaluation_cases"]:
            raise ValueError(f"{case['id']}: measurement has no frozen case")
        if not set(case["evaluation_cases"]) <= fixture_ids:
            raise ValueError(f"{case['id']}: unknown frozen evaluation case")
        if case.get("evaluation_v2_cases") and not set(case["evaluation_v2_cases"]) <= v2_ids:
            raise ValueError(f"{case['id']}: unknown frozen v2 case")
        for selector in case["tests"]:
            if not re.fullmatch(r"tests/test_[a-z_]+\.py::test_[A-Za-z0-9_]+", selector):
                raise ValueError(f"Invalid local selector: {selector}")
            filename, name = selector.split("::")
            tree = ast.parse((ROOT / filename).read_text())
            definitions = {
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if name not in definitions:
                raise ValueError(f"Missing test: {selector}")
        pending = case.get("pending")
        if pending and (
            not isinstance(pending["pr"], int)
            or pending["pr"] <= 0
            or not re.fullmatch(r"[0-9a-f]{40}", pending["head"])
        ):
            raise ValueError(f"{case['id']}: invalid pinned pending reference")
    load_index(ROOT)
    return inventory


def table(inventory: dict) -> str:
    lines = [
        "| ID | Scenario / expected assertion | Evidence | Limit |",
        "|---|---|---|---|",
    ]
    for case in inventory["cases"]:
        refs = [f"`{selector}`" for selector in case["tests"]]
        if case["evaluation_cases"]:
            refs.append("Frozen v1: " + ", ".join(case["evaluation_cases"]))
        if case.get("evaluation_v2_cases"):
            refs.append("Frozen v2: " + ", ".join(case["evaluation_v2_cases"]))
        if pending := case.get("pending"):
            refs.append(f"PR{pending['pr']} at `{pending['head'][:7]}`: {pending['state']}")
        lines.append(
            f"| {case['id']} | {case['case']}; {case['expected']} | "
            f"**{case['kind']}**: {'; '.join(refs) or 'No execution evidence'} | "
            f"{case['note']} |"
        )
    return "\n".join(lines)


def source_record(inventory: dict) -> dict:
    files = {
        "docs/acceptance-inventory.json",
        "scripts/acceptance_matrix.py",
        inventory["architecture"],
        inventory["evaluation_fixture"],
        inventory["evaluation_record"],
        "evaluation/semantic-heldout-v2.json",
        "docs/semantic-v2-evidence.md",
        "testdata/test-cases.json",
        "src/agentgate/threat_taxonomy.py",
        "scripts/threat_evidence.py",
        "scripts/acceptance_capture.py",
        "evaluation/freeze-v1.json",
        "evaluation/freeze-v2.json",
    }
    files.update(selector.split("::")[0] for c in inventory["cases"] for selector in c["tests"])
    return {
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        ),
        "python": sys.version,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(files)
        },
    }


def run_controls(inventory: dict, output: Path) -> int:
    # Pending branches and measured semantic fixtures never enter the pytest command.
    selectors = sorted({selector for case in inventory["cases"] for selector in case["tests"]})
    if not selectors:
        raise ValueError("No control selectors; refusing an empty test run")
    output = output.resolve()
    generated = (ROOT / "reports/generated").resolve()
    if not output.is_relative_to(generated):
        raise ValueError("Reports must be under ignored reports/generated/")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the report before dispatch; preserve prior evidence on accidental rerun.
    with output.open("x") as report:
        record = source_record(inventory)
        record.update(
            {
                "schema_version": 1,
                "started_at": datetime.now(UTC).isoformat(),
                "real_inference": "not_run_documentation_scope",
                "release_acceptance": "not_inferred_from_control_tests",
                "selected_tests": selectors,
                "cases": inventory["cases"],
            }
        )
        with tempfile.TemporaryDirectory(prefix="laya-acceptance-") as directory:
            junit = Path(directory) / "controls.xml"
            capture_path = Path(directory) / "capture.json"
            command = [
                sys.executable,
                "-m",
                "pytest",
                "-o",
                "addopts=-q --strict-markers",
                "-p",
                "acceptance_capture",
                *selectors,
                f"--junitxml={junit}",
            ]
            environment = dict(os.environ)
            environment.pop("PYTEST_ADDOPTS", None)
            environment["PYTHONPATH"] = (
                str(ROOT / "scripts") + os.pathsep + environment.get("PYTHONPATH", "")
            )
            environment["AGENTGATE_ACCEPTANCE_CAPTURE"] = str(capture_path)
            try:
                result = subprocess.run(
                    command, cwd=ROOT, env=environment, check=False, timeout=300
                )
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                exit_code = 124
            capture = json.loads(capture_path.read_bytes()) if capture_path.exists() else {}
            reconciliation = reconcile(selectors, capture, exit_code)
            evidence = summarize(load_index(ROOT), inventory, reconciliation)
            evidence["index_sha256"] = digest(ROOT / "testdata/test-cases.json")
            evidence["execution"] = reconciliation
            observations = []
            if junit.exists():
                for node in ET.parse(junit).getroot().iter("testcase"):
                    status = "passed"
                    for tag in ("skipped", "failure", "error"):
                        if node.find(tag) is not None:
                            status = {"failure": "failed", "error": "error"}.get(tag, tag)
                            break
                    observations.append(
                        {"class": node.get("classname"), "name": node.get("name"), "status": status}
                    )
            counts = dict(Counter(item["status"] for item in observations))
            record.update(
                {
                    "finished_at": datetime.now(UTC).isoformat(),
                    "pytest_exit": exit_code,
                    "threat_evidence": evidence,
                    "control_test_counts": counts,
                    "control_observations": observations,
                }
            )
            json.dump(record, report, ensure_ascii=False, indent=2)
            report.write("\n")
    print(f"Control observations: {counts}. Report: {output.relative_to(ROOT)}")
    print("Real inference NOT RUN. Measured, pending, partial and gap rows retain their meaning.")
    # A skip/missing execution cannot quietly satisfy the control gate.
    return exit_code or int(
        bool(reconciliation["problems"])
        or any(c["status"] != "passed" for c in reconciliation["selectors"].values())
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate mappings without inference")
    mode.add_argument("--run", action="store_true", help="Run mapped local control checks")
    mode.add_argument("--markdown", action="store_true", help="Print full evidence mapping")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/generated/acceptance-controls.json",
    )
    args = parser.parse_args()
    try:
        inventory = load_inventory()
        if args.run:
            return run_controls(inventory, args.output)
        if args.markdown:
            print(table(inventory))
        else:
            print(
                "Validated 48 mappings: "
                + str(dict(Counter(c["kind"] for c in inventory["cases"])))
            )
            print(
                "Mapping validation is not test execution, semantic accuracy or product completion."
            )
        return 0
    except (OSError, ValueError, KeyError, SyntaxError) as error:
        print(f"Acceptance inventory failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
