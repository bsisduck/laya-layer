"""Bounded pytest hook for exact acceptance collection and execution provenance."""

import json
import os
from pathlib import Path

import pytest

MAX_NODES = 10000
MAX_REPORTS = MAX_NODES * 3
state = {
    "collected": [],
    "selected": [],
    "deselected": [],
    "reports": [],
    "collection_errors": [],
    "finished": False,
}


def pytest_itemcollected(item):
    if len(state["collected"]) >= MAX_NODES:
        raise pytest.UsageError("Acceptance collection bound exceeded")
    state["collected"].append(item.nodeid)


def pytest_collection_finish(session):
    state["selected"] = [item.nodeid for item in session.items]


def pytest_deselected(items):
    state["deselected"].extend(item.nodeid for item in items)


def pytest_collectreport(report):
    if report.failed:
        state["collection_errors"].append(report.nodeid)


def pytest_runtest_logreport(report):
    if len(state["reports"]) >= MAX_REPORTS:
        raise pytest.UsageError("Acceptance observation bound exceeded")
    state["reports"].append(
        {"nodeid": report.nodeid, "when": report.when, "outcome": report.outcome}
    )


def pytest_sessionfinish(session, exitstatus):
    state["finished"] = True
    Path(os.environ["AGENTGATE_ACCEPTANCE_CAPTURE"]).write_text(json.dumps(state))
