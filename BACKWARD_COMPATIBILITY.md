# Contract status

AgentGate is unreleased. Its first implemented contracts are documented in
`docs/document-slice.md`: REST action execution and health endpoints, strict
document arguments, the partial policy schema, minimized audit events, local CLI,
and SQLite schema version 1. Other architecture examples remain proposals.
There is no earlier schema to migrate; future schema changes need an explicit
migration or a documented disposable-demo reset, never a silent reinterpretation.

The current operational contracts are `make setup`, `make validate`, `make doctor`,
`make harness`, Python lint/type/test/build commands, local demo commands, and the
upstream configuration formats under `.ai/`. Keep their
documentation and callers consistent when changing them. Preserve the original
architecture document and record consequential design changes explicitly.

When implementing additional runtime surfaces, add their status here and establish contract
tests for HTTP/MCP schemas, canonical operation aliases, semantic-worker messages,
policy versions, approval payload binding, budget units, audit events, and SDK calls.
For a used contract, incompatible changes require a consumer update, migration or
versioning plan as appropriate, and tests. Never silently change identity,
authorization, or accounting semantics to preserve apparent compatibility.
