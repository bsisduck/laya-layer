from pathlib import Path

import pytest
from pydantic import ValidationError

from agentgate.contracts import DocumentMetadata, Identity, Reason, SemanticCoverage, SemanticResult
from agentgate.policy import Policy, load_policy


def test_policy_intersects_agent_scope_role_and_resource_tenant():
    policy = Policy(policy_id="test", revision=1)
    identity = Identity(
        principal_id="person",
        tenant_id="a",
        agent_id="reader",
        root_run_id="run",
        roles=("analyst",),
        operations=("documents.read",),
    )
    own = DocumentMetadata(document_id="doc", tenant_id="a", classification="internal")
    other = own.model_copy(update={"tenant_id": "b"})
    assert policy.authorize(identity, own) is None
    assert policy.authorize(identity, other) == Reason.RESOURCE_NOT_ALLOWED
    assert policy.authorize(identity, None) == Reason.RESOURCE_NOT_ALLOWED
    assert (
        policy.authorize(identity.model_copy(update={"operations": ()}), own)
        == Reason.OPERATION_NOT_ALLOWED
    )
    assert (
        policy.authorize(identity.model_copy(update={"roles": ("viewer",)}), own)
        == Reason.OPERATION_NOT_ALLOWED
    )


@pytest.mark.parametrize(
    "extra", ["revision: 2", "unknown: true", "semantic_required: 'false'", "revision: .nan"]
)
def test_invalid_policy_is_not_silently_accepted(tmp_path: Path, extra: str):
    path = tmp_path / "policy.yaml"
    path.write_text("policy_id: test\nrevision: 1\n" + extra + "\n")
    with pytest.raises((ValidationError, ValueError)):
        load_policy(path)


def test_shipped_policy_loads():
    policy = load_policy(Path("config/policy.yaml"))
    assert policy.version == "document-demo:2"
    assert policy.tool_budgets is not None
    assert policy.tool_budgets.root_run == 100


def test_nonfinite_semantic_signal_is_invalid():
    with pytest.raises(ValidationError):
        SemanticResult(
            request_id="test",
            backend="laya_standard",
            checkpoint_revision="a" * 40,
            question_set_id="risk-v1",
            status="ok",
            selected_labels={"risk": "low"},
            raw_scores={"risk": float("nan")},
            coverage=SemanticCoverage(
                complete=True, windows_evaluated=1, input_truncated=False, options_collapsed=False
            ),
        )
