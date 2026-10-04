"""Real boundary adapters with synthetic native scores; not real-model evaluation."""

import json
import secrets

import pytest
from fastapi.testclient import TestClient
from test_admin import ORIGIN
from test_admin import admin as admin
from test_gateway import harness as harness
from test_mcp import rpc
from test_mcp import wire as wire
from test_models import model as model
from test_scoped_tools import mail, rows
from test_scoped_tools import tools as tools
from test_semantics import result_data

from agentgate.admin import attach_admin_routes
from agentgate.app import create_app
from agentgate.audit_export import format_event
from agentgate.contracts import SemanticResult
from agentgate.storage import credential_digest
from agentgate.threat_taxonomy import LAYERS, LEVELS, threat_context

SCORES = {"task_data": 0.123456789, "behavior_instruction": 0.765432101, "unclear": 0.11111111}
PUBLIC_KEYS = {
    "status",
    "action_id",
    "trace_id",
    "decision",
    "reason_codes",
    "policy_version",
    "executed",
}
EXPORT_KEYS = {
    "schema_version",
    "event_id",
    "sequence",
    "timestamp",
    "event_type",
    "action_id",
    "trace_id",
    "tenant_id",
    "principal_id",
    "root_run_id",
    "operation",
    "decision",
    "reason_codes",
    "policy_version",
    "executed",
    "semantic_status",
}


class DistinctiveScores:
    def __init__(self, deny_at=1):
        self.calls = []
        self.deny_at = deny_at

    def ready(self):
        return True

    def evaluate(self, request_id, content):
        self.calls.append(request_id)
        label = "behavior_instruction" if len(self.calls) >= self.deny_at else "task_data"
        data = result_data(label)
        scores = (
            SCORES
            if label == "behavior_instruction"
            else {
                "task_data": 0.765432101,
                "behavior_instruction": 0.123456789,
                "unclear": 0.11111111,
            }
        )
        return SemanticResult.model_validate(
            data | {"request_id": request_id, "raw_scores": scores}
        )


def require_scores(service, deny_at=1):
    service.semantic = DistinctiveScores(deny_at)
    service.policy = service.policy.model_copy(update={"semantic_required": True})


def no_private_metadata(value):
    serialized = json.dumps(value)
    for name in (
        "raw_scores",
        "threshold",
        "question_set_id",
        "selected_labels",
        "checkpoint_revision",
        "payload_digest",
    ):
        assert name not in serialized
    for score in SCORES.values():
        assert str(score) not in serialized


def correlate_private_and_projected(store, body):
    no_private_metadata(body)
    assert set(body) == PUBLIC_KEYS
    assert body["reason_codes"] == ["SEMANTIC_BLOCKED"]
    assert body["executed"] is False
    event = store.events()[-1]
    assert event.action_id == body["action_id"] and event.trace_id == body["trace_id"]
    assert event.semantic.raw_scores == SCORES
    assert "threat_context" not in event.model_dump()
    assert threat_context(event)["candidate_levels"] == []
    assert threat_context(event)["level_status"] == "unknown"
    exported = format_event(event, 1, "jsonl")
    assert set(exported) == EXPORT_KEYS
    no_private_metadata(exported)


def operator_projection(service):
    app = create_app(service)
    attach_admin_routes(app, service, origin=ORIGIN)
    token = secrets.token_urlsafe(32)
    with service.store.connection() as db:
        db.execute("INSERT INTO operator_credentials VALUES (1, ?)", (credential_digest(token),))
    with TestClient(app, base_url=ORIGIN) as client:
        login = client.post("/admin/session", headers={"Origin": ORIGIN}, json={"token": token})
        assert login.status_code == 200
        timeline = client.get("/admin/events").json()
        no_private_metadata(timeline)
        assert timeline["events"][0]["threat_context"]["level_status"] == "unknown"
        exported = client.get("/admin/audit/export?tenant=tenant-a").text.strip().splitlines()
        assert exported
        for line in exported:
            value = json.loads(line)
            assert set(value) == EXPORT_KEYS
            no_private_metadata(value)


def test_rest_denial_scores_private_zero_mail_dispatch_and_minimized_admin(tools):
    require_scores(tools.service)
    response = mail(tools)
    assert response.status_code == 403
    correlate_private_and_projected(tools.store, response.json())
    assert rows(tools, "tool_outbox") == [] and rows(tools, "tool_actions") == []
    assert tools.store.budget_counters() == []
    operator_projection(tools.service)


def test_mcp_actual_wire_denial_scores_private_zero_side_effect(wire):
    client, _, tools = wire
    require_scores(tools.service)
    response = rpc(
        wire,
        "tools/call",
        {
            "name": "mail_send",
            "arguments": {
                "recipient": "a@demo.internal",
                "subject": "Privacy",
                "body": "Synthetic",
                "idempotency_key": "score-privacy",
            },
        },
        call_id="score-correlation",
    )
    assert response.status_code == 200 and response.json()["id"] == "score-correlation"
    envelope = response.json()["result"]
    assert envelope["isError"] is True
    body = envelope["structuredContent"]
    correlate_private_and_projected(tools.store, body)
    no_private_metadata(envelope)
    assert rows(tools, "tool_outbox") == [] and tools.store.budget_counters() == []
    operator_projection(tools.service)


@pytest.mark.parametrize("deny_at", [1, 2])
def test_model_input_and_output_denial_scores_private(model, deny_at):
    require_scores(model.actions, deny_at)
    response = model.call()
    assert response.status_code == 403
    body = response.json()
    no_private_metadata(body)
    assert set(body) == PUBLIC_KEYS
    assert body["reason_codes"] == ["SEMANTIC_BLOCKED"]
    event = model.store.events()[-1]
    assert event.action_id == body["action_id"] and event.trace_id == body["trace_id"]
    assert event.semantic.raw_scores == SCORES
    assert len(model.provider.calls) == deny_at - 1
    assert "result" not in body and "choices" not in body
    if deny_at == 1:
        assert model.models.ledger.counters() == [] and body["executed"] is False
    else:
        assert event.event_type == "output_blocked"
        assert (
            body["executed"] is True
        )  # The authorized provider work is accounted; output withheld.
        assert all(c["reserved"] == 0 for c in model.models.ledger.counters())
        assert threat_context(event)["layers"] == ["output"]
    operator_projection(model.actions)


def test_taxonomy_operator_boundary_and_unclassified_context(admin):
    assert admin.client.get("/admin/threat-taxonomy").status_code == 401
    assert (
        admin.client.get("/admin/threat-taxonomy", headers=admin.gateway.headers).status_code == 401
    )
    assert admin.login().status_code == 200
    response = admin.client.get("/admin/threat-taxonomy")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    value = response.json()
    assert [item["id"] for item in value["levels"]] == [i for i, *_ in LEVELS]
    assert [item["id"] for item in value["layers"]] == [i for i, *_ in LAYERS]
    assert admin.client.get("/admin/threat-taxonomy?unexpected=1").status_code == 422
    allowed = admin.gateway.read()
    denied = admin.gateway.read("tenant-b-notes")
    assert allowed.status_code == 200 and denied.status_code == 403
    events = admin.client.get("/admin/events").json()["events"]
    for event in events:
        ctx = event["threat_context"]
        assert ctx["candidate_levels"] == [] and ctx["level_status"] == "unknown"
        assert ctx["basis"] == "control_context_only" and ctx["intent"] == "not_assessed"
        if event["reason_codes"] == ["ALLOWED"]:
            assert ctx["layers"] == [] and ctx["owasp"] == []
    assert events[0]["threat_context"]["layers"] == ["identity", "data"]
    assert set(events[0]) == EXPORT_KEYS | {"feed_version", "threat_context"}
