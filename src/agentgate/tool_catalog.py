"""Reviewed tool authority and explainable local risk; never caller-supplied hints."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, model_validator

from agentgate.contracts import Contract, Identifier

if TYPE_CHECKING:
    from agentgate.policy import Policy

CATALOG_VERSION = "approved-tools-v1"
RISK_VERSION: Literal["tool-policy-heuristic-v1"] = "tool-policy-heuristic-v1"


class RiskMetadata(Contract):
    effect: Literal["read", "write", "destructive"]
    potential_data: Literal["public", "classified_content", "unclassified_submitted_text"]
    exposure: Literal["tenant_scope", "approved_destination"]
    reversibility: Literal["no_mutation", "local_record_retained", "external_system_dependent"]
    affects_person: bool


class ToolMetadata(RiskMetadata):
    operation: Identifier
    description: Annotated[str, Field(min_length=1, max_length=512)]
    data_scope: Annotated[str, Field(min_length=1, max_length=512)]
    adapter: Literal["tenant_document_store", "tenant_memory_store", "local_fixture_outbox"]
    approval: Literal["automatic_read", "exact_approval"]
    idempotent: Literal[True] = True
    open_world: Literal[False] = False

    @model_validator(mode="after")
    def reviewed_executor_contract(self) -> ToolMetadata:
        # These are the actual three executor contracts. Adding a tool requires
        # an explicit reviewed implementation here, not metadata alone.
        expected = {
            "documents.read": ("tenant_document_store", "read", "automatic_read"),
            "memory.query": ("tenant_memory_store", "read", "automatic_read"),
            "mail.send": ("local_fixture_outbox", "write", "exact_approval"),
        }
        if expected.get(self.operation) != (self.adapter, self.effect, self.approval):
            raise ValueError("No reviewed executor/disposition for this metadata")
        return self


class RiskComponents(Contract):
    effect: int
    potential_data: int
    exposure: int
    reversibility: int
    affects_person: int


class ToolRisk(Contract):
    version: Literal["tool-policy-heuristic-v1"] = RISK_VERSION
    score: Annotated[int, Field(ge=0, le=100)]
    band: Literal["low", "moderate", "high"]
    components: RiskComponents


# Sum is bounded by construction to 0..100. Named weights are also bound into
# the approved registry, so changing the interpretation invalidates approvals.
RISK_WEIGHTS = MappingProxyType(
    {
        "effect": MappingProxyType({"read": 0, "write": 25, "destructive": 45}),
        "potential_data": MappingProxyType(
            {"public": 0, "classified_content": 25, "unclassified_submitted_text": 25}
        ),
        "exposure": MappingProxyType({"tenant_scope": 0, "approved_destination": 10}),
        "reversibility": MappingProxyType(
            {"no_mutation": 0, "local_record_retained": 5, "external_system_dependent": 10}
        ),
        "affects_person": MappingProxyType({"false": 0, "true": 10}),
    }
)


def risk_band(score: int) -> Literal["low", "moderate", "high"]:
    if type(score) is not int or not 0 <= score <= 100:
        raise ValueError("Risk score must be an integer in 0..100")
    return "low" if score < 25 else "moderate" if score < 60 else "high"


def score_risk(metadata: RiskMetadata) -> ToolRisk:
    components = RiskComponents(
        effect=RISK_WEIGHTS["effect"][metadata.effect],
        potential_data=RISK_WEIGHTS["potential_data"][metadata.potential_data],
        exposure=RISK_WEIGHTS["exposure"][metadata.exposure],
        reversibility=RISK_WEIGHTS["reversibility"][metadata.reversibility],
        affects_person=RISK_WEIGHTS["affects_person"][str(metadata.affects_person).lower()],
    )
    score = sum(components.model_dump().values())
    return ToolRisk(score=score, band=risk_band(score), components=components)


CATALOG = MappingProxyType(
    {
        item.operation: item
        for item in (
            ToolMetadata(
                operation="documents.read",
                description="Read an authorized tenant document.",
                effect="read",
                potential_data="classified_content",
                exposure="tenant_scope",
                data_scope="Potential classified document content; the selected resource's tenant and classification are authorized before reading.",
                reversibility="no_mutation",
                affects_person=False,
                adapter="tenant_document_store",
                approval="automatic_read",
            ),
            ToolMetadata(
                operation="memory.query",
                description="Search permitted memory in the credential tenant.",
                effect="read",
                potential_data="classified_content",
                exposure="tenant_scope",
                data_scope="Potential classified memory content; rows are restricted to the credential tenant and policy classifications.",
                reversibility="no_mutation",
                affects_person=False,
                adapter="tenant_memory_store",
                approval="automatic_read",
            ),
            ToolMetadata(
                operation="mail.send",
                description="Propose exact mail for human approval; writes only to a local test outbox.",
                effect="write",
                potential_data="unclassified_submitted_text",
                exposure="approved_destination",
                data_scope="Caller-submitted text, not a content classification; exact recipient domain and content controls apply before local storage.",
                reversibility="local_record_retained",
                affects_person=True,
                adapter="local_fixture_outbox",
                approval="exact_approval",
            ),
        )
    }
)


def disposition(operation: str) -> Literal["automatic_read", "exact_approval", "deny"]:
    metadata = CATALOG.get(operation)
    return metadata.approval if metadata is not None else "deny"


def mcp_annotations(operation: str) -> dict[str, bool]:
    metadata = CATALOG[operation]
    return {
        "readOnlyHint": metadata.effect == "read",
        "destructiveHint": metadata.effect == "destructive",
        # Local mail deduplicates only for the same immutable idempotency key.
        "idempotentHint": metadata.idempotent,
        "openWorldHint": metadata.open_world,
    }


def policy_requirements(operation: str, policy: Policy) -> dict[str, object]:
    """Project the same policy fields consumed by the executors, not new rules."""
    roles = {
        "documents.read": policy.documents_read.roles,
        "memory.query": policy.scoped_tools.memory_roles,
        "mail.send": policy.scoped_tools.mail_roles,
    }[operation]
    result: dict[str, object] = {
        "credential_operation": operation,
        "roles": list(roles),
        "disposition": disposition(operation),
        "hard_authorization_first": True,
        "output_inspection": True,
    }
    if operation == "mail.send":
        result["recipient_domains"] = list(policy.scoped_tools.mail_domains)
        result["approval_ttl_seconds"] = policy.scoped_tools.approval_ttl_seconds
    else:
        result["tenant_scope"] = "credential_owned"
        result["classifications"] = list(
            policy.documents_read.classifications
            if operation == "documents.read"
            else policy.scoped_tools.memory_classifications
        )
    return result


def catalog_document(policy: Policy, registry_digest: str) -> dict[str, object]:
    return {
        "version": CATALOG_VERSION,
        "registry_digest": registry_digest,
        "policy_version": policy.version,
        "risk_version": RISK_VERSION,
        "risk_weights": {key: dict(value) for key, value in RISK_WEIGHTS.items()},
        "risk_limits": "Local policy heuristic, not probability, content classification, semantic inference, OWASP level or AI Act legal classification.",
        "tools": [
            {
                **metadata.model_dump(mode="json"),
                "executable": True,
                "risk": score_risk(metadata).model_dump(mode="json"),
                "policy": policy_requirements(operation, policy),
            }
            for operation, metadata in CATALOG.items()
        ],
        "examples": [
            {
                "operation": "gitlab.merge_main",
                "category": "Dev",
                "executable": False,
                "effect": "write",
                "status": "proposed_unavailable",
                "description": "Consequential merge example; reversibility depends on repository history and policy. No GitLab connection or executor.",
            },
            {
                "operation": "payments.transfer",
                "category": "Finance",
                "executable": False,
                "effect": "write",
                "status": "proposed_unavailable",
                "description": "Payment example; reversibility depends on the external system. No bank connection or executor.",
            },
        ],
    }
