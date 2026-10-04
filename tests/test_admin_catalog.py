"""Protected catalog projects actual active policy and exposes no request data."""

import pytest
from test_admin import admin as admin
from test_gateway import harness as harness

from agentgate.scoped_contracts import REGISTRY_DIGEST
from agentgate.tool_catalog import CATALOG, policy_requirements, score_risk


def test_catalog_uses_protected_session_and_actual_policy(admin):
    assert admin.client.get("/admin/catalog").status_code == 401
    admin.login()
    result = admin.client.get("/admin/catalog")
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    data = result.json()
    assert data["version"] == "approved-tools-v1" and data["registry_digest"] == REGISTRY_DIGEST
    assert data["policy_version"] == admin.gateway.service.policy.version
    assert [tool["operation"] for tool in data["tools"]] == list(CATALOG)
    for tool in data["tools"]:
        metadata = CATALOG[tool["operation"]]
        assert tool["risk"] == score_risk(metadata).model_dump(mode="json")
        assert tool["policy"] == policy_requirements(
            tool["operation"], admin.gateway.service.policy
        )
        assert tool["executable"] is True
    assert {row["operation"] for row in data["examples"]} == {
        "gitlab.merge_main",
        "payments.transfer",
    }
    assert all(row["executable"] is False for row in data["examples"])
    assert "No GitLab connection" in result.text and "No bank connection" in result.text
    for forbidden in (
        admin.token,
        admin.gateway.token,
        "payload_digest",
        "fingerprint",
        "raw_model_score",
    ):
        assert forbidden not in result.text
    assert admin.gateway.executor.calls == [] and admin.gateway.store.budget_counters() == []


def test_catalog_projects_live_activation_without_changing_authority(admin):
    admin.login()
    original = admin.gateway.service.policy
    candidate = original.model_dump(mode="json")
    candidate["revision"] += 1
    candidate["documents_read"] = {"roles": ["reviewer"], "classifications": ["public"]}
    candidate["scoped_tools"]["mail_domains"] = ["review.internal"]
    candidate["scoped_tools"]["memory_classifications"] = ["confidential"]
    activated = admin.client.post(
        "/admin/policy/activate",
        headers=admin.headers(),
        json={"policy": candidate, "expected_version": original.version},
    )
    assert activated.status_code == 200
    data = admin.client.get("/admin/catalog").json()
    assert data["policy_version"] == activated.json()["version"]
    tools = {tool["operation"]: tool for tool in data["tools"]}
    assert tools["documents.read"]["policy"]["roles"] == ["reviewer"]
    assert tools["documents.read"]["policy"]["classifications"] == ["public"]
    assert tools["memory.query"]["policy"]["classifications"] == ["confidential"]
    assert tools["mail.send"]["policy"]["recipient_domains"] == ["review.internal"]
    assert tools["mail.send"]["policy"]["disposition"] == "exact_approval"
    denied = admin.gateway.read()
    assert denied.status_code == 403 and denied.json()["executed"] is False
    assert admin.gateway.executor.calls == [] and admin.gateway.store.budget_counters() == []


@pytest.mark.parametrize(
    "query", ["?limit=9999", "?tenant_id=tenant-b", "?risk=0", "?version=x&version=y"]
)
def test_catalog_is_fixed_and_rejects_client_configuration(admin, query):
    admin.login()
    assert admin.client.get("/admin/catalog" + query).status_code == 422
    assert admin.gateway.executor.calls == []


def test_catalog_origin_session_expiry_and_methods(admin):
    admin.login()
    assert (
        admin.client.get("/admin/catalog", headers={"Origin": "https://evil.invalid"}).status_code
        == 403
    )
    assert (
        admin.client.post("/admin/catalog", headers=admin.headers(), json={"risk": 0}).status_code
        == 405
    )
    admin.gateway.now[0] += 900
    assert admin.client.get("/admin/catalog").status_code == 401
    assert admin.gateway.executor.calls == []
