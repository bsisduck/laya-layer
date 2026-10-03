# AgentGate visual architecture

These Mermaid diagrams render directly on GitHub. The
[full design](../AgentGate_Full_Project_Architecture.md#5-system-architecture)
contains the detailed target architecture and budget state machine.

## Working document path

```mermaid
flowchart LR
    Client["Agent or REST client<br/>untrusted request"] --> API["Authenticated action API"]
    subgraph Gateway["AgentGate — implemented"]
        API --> Identity["Server-owned identity<br/>tenant, role, agent, root run"]
        Identity --> Policy["Strict schema and deterministic policy"]
        Policy --> Intent["Recheck credential<br/>persist dispatch intent"]
        Intent --> Executor["Registered document executor"]
        Executor --> Filter["Bounded output<br/>email redaction and synthetic-secret block"]
        Filter --> Outcome["Persist outcome before release"]
    end
    Policy -- deny --> Audit[("SQLite audit and credentials")]
    Intent --> Audit
    Outcome --> Audit
    Executor --> Fixtures["Tenant-scoped synthetic documents"]
    Outcome --> Response["Allowed, redacted, or withheld result"]
    Response --> Client
```

No fixture read occurs after a pre-execution denial. A blocked tool result may
follow an executed read; the response reports that distinction. SQLite and
fixture access assume trusted host processes. The gateway is not a host sandbox.

## Product target and implementation status

```mermaid
flowchart TB
    Agent["Hermes / compatible agent<br/>integration planned"]
    subgraph Boundary["AgentGate policy authority"]
        REST["REST action API<br/>working"]
        Model["Model facade<br/>planned"]
        MCP["MCP adapter<br/>planned"]
        Core["Identity, policy, output filtering, audit<br/>working for documents"]
        Budget["Atomic resource ledger<br/>next"]
        Approval["Exact-action approvals<br/>planned"]
        Sem["Semantic adapter<br/>planned"]
    end
    Agent --> REST
    Agent -.-> Model
    Agent -.-> MCP
    REST --> Core
    Model -.-> Core
    MCP -.-> Core
    Core -.-> Budget
    Core -.-> Approval
    Core -.-> Sem
    Sem -.-> Laya["Standard Laya worker<br/>real loader tested; service planned"]
    Sem -.-> Apple["Native CoreML worker<br/>real loader tested; service planned"]
    Core --> Docs["Document fixtures<br/>working"]
    Core -.-> Tools["Memory and test outbox<br/>planned"]
    Model -.-> Lite["Private LiteLLM<br/>planned"]
    Lite -.-> Local["Local generation model"]
    Core --> DB[("SQLite")]
    Admin["Authenticated dashboard<br/>planned"] -.-> DB
    Admin -.-> Approval
```

Solid edges describe implemented paths. Dashed edges describe the target.
Real Laya and CoreML smoke tests both matched 2 of 4 prewritten labels; they
are loading evidence, not a validated security classifier or gateway integration.

## Output-release boundary

```mermaid
sequenceDiagram
    actor Agent
    participant API as AgentGate
    participant DB as SQLite
    participant Tool as Document executor
    Agent->>API: Bearer credential + canonical action
    API->>DB: Resolve server-owned identity
    API->>API: Validate input, role, scope, tenant, classification
    alt Deterministic denial
        API->>DB: Persist denied outcome
        API-->>Agent: Deny; executed=false
    else Authorized document read
        API->>DB: Recheck credential + durable dispatch intent
        API->>Tool: Read registered tenant document
        Tool-->>API: Untrusted result
        API->>API: Bound, inspect, redact or withhold
        API->>DB: Persist outcome
        API-->>Agent: Decision; executed=true; result only if releasable
    end
```

Audit failure before dispatch prevents execution. Audit failure after dispatch
withholds the output. Neither outcome makes an uncertain action safe to retry.
