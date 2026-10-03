"""Administrator-owned resource and routing policy; no provider secrets."""

from typing import Annotated, Literal

from pydantic import Field

from agentgate.contracts import Contract, Identifier

Amount = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


class ResourceLimits(Contract):
    calls: Amount = 100
    tokens: Amount = 100_000
    micro_usd: Amount = 0


class ModelPolicy(Contract):
    aliases: Annotated[tuple[Literal["local-demo"], ...], Field(min_length=1, max_length=1)] = (
        "local-demo",
    )
    max_output_tokens: Annotated[int, Field(ge=1, le=4096)] = 256
    max_input_bytes: Annotated[int, Field(ge=64, le=65536)] = 8192
    # Bounded serialized request bytes + this allowance is the reserved input
    # token estimate. Provider usage beyond it freezes these scopes for review.
    template_token_allowance: Annotated[int, Field(ge=1024, le=8192)] = 4096
    tenant_day: ResourceLimits = ResourceLimits()
    principal_day: ResourceLimits = ResourceLimits()
    root_run: ResourceLimits = ResourceLimits()
    max_concurrent: Annotated[int, Field(ge=1, le=16)] = 1
    input_micro_usd: Amount = 0
    output_micro_usd: Amount = 0
    tariff_revision: Identifier = "local-no-invoice-v1"
    # Nonzero tariffs are a simulation, never an assertion about provider billing.
    simulated_tariff: Literal[True] = True
