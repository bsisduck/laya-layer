"""Bounded administrator-owned relational grants; no caller authority assertions."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agentgate.contracts import Contract, Identifier

Operation = Literal["documents.read", "memory.query", "mail.send", "chat.completions"]
Classification = Literal["public", "internal", "confidential", "secret"]
Ids = Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=64)]


class RecordGrant(Contract):
    operation: Literal["documents.read", "memory.query"]
    resources: Ids
    classifications: Annotated[tuple[Classification, ...], Field(min_length=1, max_length=4)]


class MailGrant(Contract):
    operation: Literal["mail.send"]
    domains: Annotated[
        tuple[Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$", max_length=253)], ...],
        Field(min_length=1, max_length=64),
    ]


class ModelGrant(Contract):
    operation: Literal["chat.completions"]
    models: Ids


Grant = Annotated[RecordGrant | MailGrant | ModelGrant, Field(discriminator="operation")]
Grants = Annotated[tuple[Grant, ...], Field(max_length=64)]


class RoleProfile(Contract):
    role_id: Identifier
    grants: Grants = ()


class RequireDelegation(Contract):
    tenant_id: Identifier
    agent_id: Identifier
    operations: Annotated[tuple[Operation, ...], Field(min_length=1, max_length=4)]


class DelegationPolicy(Contract):
    version: Literal[1] = 1
    profiles: Annotated[tuple[RoleProfile, ...], Field(max_length=32)] = ()
    required: Annotated[tuple[RequireDelegation, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def unique_roles(self) -> Self:
        if len({p.role_id for p in self.profiles}) != len(self.profiles):
            raise ValueError("Duplicate delegation role")
        if sum(len(p.grants) for p in self.profiles) > 64:
            raise ValueError("Delegation policy exceeds 64 aggregate grants")
        return self

    def grants_for(self, roles: tuple[str, ...]) -> tuple[Grant, ...]:
        return tuple(g for p in self.profiles if p.role_id in roles for g in p.grants)


class HumanSubject(Contract):
    version: Literal[1] = 1
    subject_id: Identifier
    provenance: Literal["local_demo"] = "local_demo"
    tenant_id: Identifier
    roles: Annotated[tuple[Identifier, ...], Field(max_length=32)]
    department: Identifier
    revision: Annotated[int, Field(ge=1, le=2147483647)]
    revoked: bool = False
    assertion_deadline: float | None = None


class IssuanceCeiling(Contract):
    version: Literal[1] = 1
    human: Grants
    agent: Grants


class AuthorityAttribution(Contract):
    version: Literal[1] = 1
    accounting_principal: Identifier
    human_subject: Identifier
    agent_id: Identifier
    delegation_id: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    provenance: Literal["local_demo"]
    subject_revision: Annotated[int, Field(ge=1)]
    department: Identifier


class ApprovalActor(Contract):
    version: Literal[1] = 1
    actor_id: Annotated[str, Field(min_length=1, max_length=96)]
    mode: Literal["credential", "local_console", "trusted_local_hook"]


class DelegatedBinding(Contract):
    version: Literal[1] = 1
    child: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    parent: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    subject: Identifier
    revision: Annotated[int, Field(ge=1)]
    identity: Annotated[str, Field(max_length=32768)]
    issued: float
    expires: float
    deadline: float | None
    issuance_policy: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    trust_version: Literal[1] = 1
    ceiling: IssuanceCeiling
