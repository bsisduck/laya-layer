"""Unit and real REST/storage behavior for reviewed catalog authority."""

import hashlib
import json

import pytest
from pydantic import ValidationError
from test_gateway import harness as harness
from test_scoped_tools import decide, execute, mail, resume, rows
from test_scoped_tools import tools as tools

from agentgate.scoped_contracts import ALIASES, INPUTS, REGISTRY_DIGEST, registry_digest
from agentgate.tool_catalog import CATALOG, RiskMetadata, ToolMetadata, risk_band, score_risk


@pytest.mark.parametrize(
    "operation,score,band,components",
    [
        ("documents.read", 25, "moderate", [0, 25, 0, 0, 0]),
        ("memory.query", 25, "moderate", [0, 25, 0, 0, 0]),
        ("mail.send", 75, "high", [25, 25, 10, 5, 10]),
    ],
)
def test_reviewed_scores_are_explicit_local_heuristics(operation, score, band, components):
    risk = score_risk(CATALOG[operation])
    assert risk.score == score and risk.band == band
    assert list(risk.components.model_dump().values()) == components
    assert sum(components) == risk.score


@pytest.mark.parametrize(
    "score,band",
    [(0, "low"), (24, "low"), (25, "moderate"), (59, "moderate"), (60, "high"), (100, "high")],
)
def test_band_boundaries(score, band):
    assert risk_band(score) == band


@pytest.mark.parametrize("score", [-1, 101, True, 2.5, float("nan"), "25"])
def test_invalid_scores_rejected(score):
    with pytest.raises(ValueError):
        risk_band(score)


@pytest.mark.parametrize(
    "effect,data,exposure,reversibility,person,expected",
    [
        ("read", "public", "tenant_scope", "no_mutation", False, 0),
        (
            "destructive",
            "classified_content",
            "approved_destination",
            "external_system_dependent",
            True,
            100,
        ),
    ],
)
def test_formula_extremes(effect, data, exposure, reversibility, person, expected):
    risk = score_risk(
        RiskMetadata(
            effect=effect,
            potential_data=data,
            exposure=exposure,
            reversibility=reversibility,
            affects_person=person,
        )
    )
    assert risk.score == expected


@pytest.mark.parametrize(
    "changes",
    [
        {"effect": "destructive"},
        {"approval": "automatic_read"},
        {"adapter": "tenant_memory_store"},
        {"operation": "payments.transfer"},
        {"affects_person": "false"},
        {"description": ""},
        {"risk_score": 0},
        {"destructiveHint": False},
    ],
)
def test_invalid_or_inconsistent_executable_metadata_is_rejected(changes):
    with pytest.raises(ValidationError):
        ToolMetadata.model_validate(CATALOG["mail.send"].model_dump() | changes)


def test_catalog_registry_is_immutable_and_bound_to_every_metadata_field():
    assert set(CATALOG) == set(INPUTS) == set(ALIASES.values())
    with pytest.raises(TypeError):
        CATALOG["payments.transfer"] = CATALOG["mail.send"]
    with pytest.raises(ValidationError):
        CATALOG["mail.send"].affects_person = False
    assert registry_digest() == REGISTRY_DIGEST
    for field, value in [
        ("description", "Reviewed new interpretation"),
        ("affects_person", False),
        ("reversibility", "external_system_dependent"),
    ]:
        changed = dict(CATALOG)
        changed["mail.send"] = ToolMetadata.model_validate(
            CATALOG["mail.send"].model_dump() | {field: value}
        )
        assert registry_digest(changed) != REGISTRY_DIGEST
    with pytest.raises(ValueError):
        registry_digest({})


def legacy_registry_digest():
    return hashlib.sha256(
        json.dumps(
            {
                "version": "scoped-tools-v1-local-outbox",
                "aliases": dict(ALIASES),
                "schemas": {key: value.model_json_schema() for key, value in INPUTS.items()},
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


@pytest.mark.parametrize("old_state", ["pending", "approved", "consumed"])
def test_registry_upgrade_safe_reproposal_and_consumed_replay(tools, monkeypatch, old_state):
    # Build authentic old-version snapshots/fingerprints, never rewrite stored rows.
    with monkeypatch.context() as old:
        old.setattr("agentgate.scoped_tools.REGISTRY_DIGEST", legacy_registry_digest())
        action = mail(tools).json()["action_id"]
        if old_state != "pending":
            decide(tools)
        if old_state == "consumed":
            assert resume(tools, action).json()["executed"] is True
    original = rows(tools, "tool_actions")[0]
    spend = tools.store.budget_counters()
    response = resume(tools, action)
    current = rows(tools, "tool_actions")[0]
    for key in (
        "payload",
        "payload_digest",
        "fingerprint",
        "registry_digest",
        "policy_digest",
        "expires_at",
    ):
        assert current[key] == original[key]
    assert tools.store.budget_counters() == spend
    assert mail(tools).json()["action_id"] == action
    if old_state == "consumed":
        assert response.status_code == 200 and response.json()["executed"] is True
        assert current == original
        assert len(rows(tools, "tool_outbox")) == 1
    else:
        assert response.status_code == 403
        assert response.json()["reason_codes"] == ["POLICY_CHANGED"]
        assert current["state"] == "denied"
        assert rows(tools, "tool_outbox") == []
        # Deliberately repropose the same content with a new key and exact approval.
        proposal = mail(tools, idempotency_key="after-registry-review").json()
        assert proposal["status"] == "pending_approval"
        new = next(
            row for row in rows(tools, "tool_actions") if row["action_id"] == proposal["action_id"]
        )
        assert new["registry_digest"] == REGISTRY_DIGEST
        tools.service.tools.decide(
            tenant_id="tenant-a",
            action_id=new["action_id"],
            fingerprint=new["fingerprint"],
            approve=True,
            actor="operator-test",
        )
        assert resume(tools, new["action_id"]).json()["executed"] is True
        assert resume(tools, new["action_id"]).json()["executed"] is True
        assert len(rows(tools, "tool_outbox")) == 1
        assert all(counter["spent"] == 1 for counter in tools.store.budget_counters())


def test_changed_reviewed_risk_invalidates_pending_approval(tools, monkeypatch):
    action = mail(tools).json()["action_id"]
    decide(tools)
    changed = dict(CATALOG)
    changed["mail.send"] = ToolMetadata.model_validate(
        CATALOG["mail.send"].model_dump() | {"affects_person": False}
    )
    monkeypatch.setattr("agentgate.scoped_tools.REGISTRY_DIGEST", registry_digest(changed))
    assert resume(tools, action).json()["reason_codes"] == ["POLICY_CHANGED"]
    assert rows(tools, "tool_outbox") == []
    assert tools.store.budget_counters() == []


@pytest.mark.parametrize(
    "canonical,alias,arguments",
    [
        ("documents.read", "documents_read", {"document_id": "tenant-a-notes"}),
        ("memory.query", "memory_query", {"query": "Quarterly"}),
        (
            "mail.send",
            "mail_send",
            {
                "recipient": "a@demo.internal",
                "subject": "Review",
                "body": "Exact content",
                "idempotency_key": "same-key",
            },
        ),
    ],
)
def test_aliases_have_identical_authority_results_and_approval(tools, canonical, alias, arguments):
    a, b = (execute(tools, operation, arguments) for operation in (canonical, alias))
    assert a.status_code == b.status_code
    for key in ("status", "decision", "executed", "result", "reason_codes"):
        assert a.json().get(key) == b.json().get(key)
    if canonical == "mail.send":
        assert a.json()["action_id"] == b.json()["action_id"]
        assert rows(tools, "tool_outbox") == []


@pytest.mark.parametrize(
    "operation", ["gitlab.merge_main", "payments.transfer", "documents.delete", "mail.send_evil"]
)
def test_even_credential_scope_cannot_register_unknown_or_destructive_tools(tools, operation):
    tools.token = tools.store.issue(
        tools.identity.model_copy(update={"operations": (*tools.identity.operations, operation)}),
        2000.0,
    )
    denied = execute(
        tools, operation, {"destructiveHint": False, "risk": 0, "approval": "automatic_read"}
    )
    assert denied.status_code == 403 and denied.json()["executed"] is False
    assert denied.json()["reason_codes"] == ["UNKNOWN_OPERATION"]
    assert operation not in tools.client.get("/v1/tools", headers=tools.headers).json()["tools"]
    assert (
        rows(tools, "tool_actions")
        == rows(tools, "tool_outbox")
        == rows(tools, "tool_reservations")
        == []
    )
    assert tools.executor.calls == [] and tools.store.budget_counters() == []
