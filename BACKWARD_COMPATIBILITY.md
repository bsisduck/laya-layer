# Contract status

AgentGate has no implemented or released public API, SDK, policy format, storage
schema, CLI, or event stream yet. The architecture's examples are proposals.
Do not call a design revision a released breaking change or invent migrations
for a database that does not exist.

The current operational contracts are `make setup`, `make validate`, `make doctor`,
`make harness`, and the upstream configuration formats under `.ai/`. Keep their
documentation and callers consistent when changing them. Preserve the original
architecture document and record consequential design changes explicitly.

When implementing runtime surfaces, add their status here and establish contract
tests for HTTP/MCP schemas, canonical operation aliases, semantic-worker messages,
policy versions, approval payload binding, budget units, audit events, and SDK calls.
For a used contract, incompatible changes require a consumer update, migration or
versioning plan as appropriate, and tests. Never silently change identity,
authorization, or accounting semantics to preserve apparent compatibility.
