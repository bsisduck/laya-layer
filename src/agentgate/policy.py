"""Validated, immutable policy for the first document-read slice."""

import json
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field
from yaml.nodes import MappingNode

from agentgate.budgets import ToolBudgets
from agentgate.contracts import Contract, DocumentMetadata, Identifier, Identity, Reason


class IngressPolicy(Contract):
    max_body_bytes: Annotated[int, Field(ge=256, le=262144)] = 16384
    max_json_depth: Annotated[int, Field(ge=2, le=24)] = 12
    body_timeout_seconds: Annotated[float, Field(gt=0, le=30)] = 5.0


class DocumentPermission(Contract):
    roles: tuple[Identifier, ...] = ("analyst",)
    classifications: tuple[Literal["public", "internal", "confidential"], ...] = (
        "public",
        "internal",
    )


class OutputPolicy(Contract):
    max_result_bytes: Annotated[int, Field(ge=64, le=262144)] = 32768
    redact_emails: bool = True
    block_synthetic_secrets: Literal[True] = True


class Policy(Contract):
    schema_version: Literal[1] = 1
    policy_id: Identifier
    revision: Annotated[int, Field(ge=1)]
    ingress: IngressPolicy = IngressPolicy()
    documents_read: DocumentPermission = DocumentPermission()
    output: OutputPolicy = OutputPolicy()
    semantic_required: bool = False
    tool_budgets: ToolBudgets | None = None

    @property
    def version(self) -> str:
        return f"{self.policy_id}:{self.revision}"

    def authorize(self, identity: Identity, document: DocumentMetadata | None) -> Reason | None:
        if "documents.read" not in identity.operations:
            return Reason.OPERATION_NOT_ALLOWED
        if not set(identity.roles).intersection(self.documents_read.roles):
            return Reason.OPERATION_NOT_ALLOWED
        if (
            document is None
            or document.tenant_id != identity.tenant_id
            or document.classification not in self.documents_read.classifications
        ):
            # Unknown, cross-tenant and classified resources deliberately look identical.
            return Reason.RESOURCE_NOT_ALLOWED
        return None


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        keys: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise ValueError("Duplicate policy key")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def load_policy(path: Path) -> Policy:
    with path.open("rb") as source:
        raw = source.read(65537)
    if len(raw) > 65536:
        raise ValueError("Policy exceeds 64 KiB")
    if any(isinstance(token, yaml.AliasToken) for token in yaml.scan(raw)):
        raise ValueError("Policy aliases are unsupported")
    document = yaml.load(raw, Loader=UniqueKeyLoader)
    return Policy.model_validate_json(json.dumps(document, allow_nan=False))
