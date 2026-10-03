import json
import os
import sqlite3
import subprocess
import sys

import pytest
from test_gateway import Harness
from test_gateway import harness as harness

from agentgate.audit_export import MAX_EVENT_BYTES, export_page
from agentgate.cli import main
from agentgate.storage import StorageUnavailable


def test_closed_output_pipe_exits_cleanly_without_checkpoint(harness: Harness, tmp_path):
    harness.read()
    with (
        sqlite3.connect(harness.store.path) as source,
        sqlite3.connect(tmp_path / "agentgate.sqlite3") as dest,
    ):
        source.backup(dest)
    reader, writer = os.pipe()
    os.close(reader)
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agentgate.cli",
                "--state-dir",
                str(tmp_path),
                "audit-export",
                "--tenant",
                "tenant-a",
            ],
            stdout=writer,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    finally:
        os.close(writer)
    assert result.returncode == 1
    assert b"output pipe closed" in result.stderr
    assert b"next_after_sequence" not in result.stderr
    assert b"Exception ignored" not in result.stderr


def records(page):
    return [json.loads(line) for line in page.lines]


def test_real_gateway_decisions_are_exported_without_content_or_credentials(harness: Harness):
    for document in ["tenant-a-notes", "tenant-a-contact", "tenant-a-leak", "tenant-b-notes"]:
        harness.read(document)
    page = export_page(harness.store.path, tenant="tenant-a")
    terminal = [r for r in records(page) if r["event_type"] != "dispatch_intent"]
    assert [r["decision"] for r in terminal] == ["allow", "redact", "deny", "deny"]
    assert [r["executed"] for r in terminal] == [True, True, True, False]
    assert terminal[-1]["reason_codes"] == ["RESOURCE_NOT_ALLOWED"]
    assert page.metadata() == {
        "next_after_sequence": 7,
        "through_sequence": 7,
        "scanned": 7,
        "exported": 7,
        "has_more": False,
    }
    raw = "\n".join(page.lines)
    for secret in [
        harness.token,
        "quarterly notes",
        "payload_digest",
        "AGENTGATE_SECRET[",
        "@example",
    ]:
        assert secret not in raw
    assert export_page(harness.store.path, tenant="tenant-a").lines == page.lines


def test_tenant_and_unattributed_selection_use_stored_identity(harness: Harness):
    harness.read()
    harness.client.post("/v1/actions/execute", json={"tenant_id": "tenant-a"})
    identity_b = harness.identity.model_copy(update={"tenant_id": "tenant-b"})
    token_b = harness.store.issue(identity_b, expires_at=2000.0)
    harness.client.post(
        "/v1/actions/execute",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"operation": "documents.read", "arguments": {"document_id": "tenant-b-notes"}},
    )
    for tenant, count in [("tenant-a", 2), ("tenant-b", 2), (None, 1)]:
        result = records(export_page(harness.store.path, tenant=tenant))
        assert len(result) == count
        assert all(r["tenant_id"] == tenant for r in result)
    assert records(export_page(harness.store.path, tenant=None))[0]["principal_id"] is None


def test_bounded_scan_advances_over_filtered_pages_and_pins_concurrent_append(harness: Harness):
    harness.read()
    harness.read()
    first = export_page(harness.store.path, tenant="absent", limit=2)
    assert first.lines == () and first.next_after_sequence == 2 and first.through_sequence == 4
    assert first.metadata()["has_more"] is True
    harness.read()  # New records must not enter the pinned export snapshot.
    second = export_page(
        harness.store.path,
        tenant="tenant-a",
        limit=2,
        after_sequence=first.next_after_sequence,
        through_sequence=first.through_sequence,
    )
    assert [r["sequence"] for r in records(second)] == [3, 4]
    assert second.metadata()["has_more"] is False
    new = export_page(harness.store.path, tenant="tenant-a", after_sequence=4)
    assert [r["sequence"] for r in records(new)] == [5, 6]


def test_ecs_separates_pre_dispatch_from_executed_output_denial(harness: Harness):
    harness.read("tenant-a-leak")
    start, blocked = records(export_page(harness.store.path, tenant="tenant-a", format="ecs"))
    assert start["event"]["outcome"] == "unknown"
    assert start["event"]["type"] == ["start"]
    assert start["laya"]["executed"] is False
    assert blocked["event"]["type"] == ["denied"]
    assert blocked["event"]["outcome"] == "failure"
    assert blocked["laya"]["executed"] is True
    assert blocked["@timestamp"].endswith("Z")
    assert blocked["event"]["id"] == blocked["laya"]["event_id"]
    assert blocked["user"]["id"] == "analyst"
    assert "agent" not in blocked and "risk_score" not in blocked["event"]


def test_uncertain_execution_is_not_reported_as_safe_to_retry(harness: Harness, monkeypatch):
    def fail(*args):
        raise RuntimeError("uncertain")

    monkeypatch.setattr(harness.executor, "read", fail)
    harness.read()
    event = records(export_page(harness.store.path, tenant="tenant-a", format="ecs"))[-1]
    assert event["event"]["outcome"] == "unknown"
    assert event["event"]["type"] == ["error"]
    assert event["laya"]["event_type"] == "execution_failed"


def test_hec_envelope_has_structured_event_and_stable_id(harness: Harness):
    harness.read()
    native = records(export_page(harness.store.path, tenant="tenant-a"))
    hec = records(export_page(harness.store.path, tenant="tenant-a", format="splunk-hec"))
    assert [r["event"] for r in hec] == native
    assert hec[0]["time"] == 1000.0
    assert hec[0]["sourcetype"] == "laya:security"
    assert set(hec[0]) == {"time", "source", "sourcetype", "event"}


@pytest.mark.parametrize("format", ["jsonl", "ecs", "splunk-hec"])
def test_private_semantic_detail_is_excluded_from_every_format(harness: Harness, format):
    harness.read()
    event = harness.store.events()[-1].model_dump(mode="json")
    event["payload_digest"] = "PRIVATE-DIGEST-CANARY"
    event["semantic"] = {
        "request_id": "PRIVATE-SEMANTIC-CANARY",
        "backend": "laya_standard",
        "checkpoint_revision": "a" * 40,
        "question_set_id": "PRIVATE-QUESTION-CANARY",
        "status": "ok",
        "selected_labels": {"private": "PRIVATE-LABEL-CANARY"},
        "raw_scores": {"PRIVATE-SCORE-CANARY": 0.5},
        "coverage": {
            "complete": True,
            "windows_evaluated": 1,
            "input_truncated": False,
            "options_collapsed": False,
        },
        "usage": {"input_tokens": 10, "inference_wall_ms": 2.0},
    }
    with harness.store.connection() as conn:
        conn.execute(
            "UPDATE audit_events SET event=? WHERE event_id=?",
            (json.dumps(event), event["event_id"]),
        )
    output = "\n".join(export_page(harness.store.path, tenant="tenant-a", format=format).lines)
    assert "CANARY" not in output


def test_export_is_read_only_and_does_not_create_missing_state(harness: Harness, tmp_path):
    harness.read()
    before = harness.store.path.read_bytes()
    export_page(harness.store.path, tenant="tenant-a")
    assert harness.store.path.read_bytes() == before
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(StorageUnavailable):
        export_page(missing, tenant="tenant-a")
    assert not missing.exists()


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"limit": 1001},
        {"limit": True},
        {"after_sequence": -1},
        {"after_sequence": 2**63},
        {"through_sequence": -1},
        {"through_sequence": 2**63},
        {"tenant": "tenant-a' OR 1=1"},
        {"format": "unknown"},
        {"after_sequence": 3},
        {"through_sequence": 3},
        {"after_sequence": 2, "through_sequence": 1},
    ],
)
def test_invalid_selection_and_snapshot_fail(harness: Harness, options):
    harness.read()
    with pytest.raises(ValueError):
        export_page(harness.store.path, **({"tenant": "tenant-a"} | options))


def test_schema_one_rows_and_empty_database_are_supported(harness: Harness):
    assert export_page(harness.store.path, tenant="tenant-a").metadata()["has_more"] is False
    harness.read()
    with harness.store.connection() as conn:
        conn.execute("PRAGMA user_version=1")
        conn.execute("UPDATE audit_events SET event=json_remove(event, '$.semantic')")
    assert len(export_page(harness.store.path, tenant="tenant-a").lines) == 2


@pytest.mark.parametrize("damage", ["malformed", "oversized", "wrong_id", "unknown_schema"])
def test_corrupt_page_has_no_partial_cli_output_or_checkpoint(
    harness: Harness, monkeypatch, capsys, damage
):
    harness.read()
    with harness.store.connection() as conn:
        if damage == "unknown_schema":
            conn.execute("PRAGMA user_version=99")
        elif damage == "wrong_id":
            conn.execute("UPDATE audit_events SET event_id='other' WHERE sequence=2")
        else:
            value = "not-json" if damage == "malformed" else "x" * (MAX_EVENT_BYTES + 1)
            conn.execute("UPDATE audit_events SET event=? WHERE sequence=2", (value,))
    # CLI database name is different from this test harness's filename.
    monkeypatch.setattr(
        "agentgate.cli.export_page", lambda *a, **kw: export_page(harness.store.path, **kw)
    )
    monkeypatch.setattr(sys, "argv", ["agentgate", "audit-export", "--tenant", "tenant-a"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "next_after_sequence" not in output.err
    assert "not-json" not in output.err and "command failed" in output.err


def test_cli_separates_records_from_checkpoint_and_requires_scope(
    harness: Harness, monkeypatch, capsys, tmp_path
):
    harness.read()
    target = tmp_path / "agentgate.sqlite3"
    with sqlite3.connect(harness.store.path) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    monkeypatch.setattr(
        sys,
        "argv",
        ["agentgate", "--state-dir", str(tmp_path), "audit-export", "--tenant", "tenant-a"],
    )
    main()
    output = capsys.readouterr()
    assert len([json.loads(line) for line in output.out.splitlines()]) == 2
    assert json.loads(output.err)["exported"] == 2
    monkeypatch.setattr(sys, "argv", ["agentgate", "audit-export"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
