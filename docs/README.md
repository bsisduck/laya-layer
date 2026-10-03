# Documentation

Start with the [visual architecture](architecture.md), then follow the
[run instructions](../README.md#run-the-local-application).

| Document | Purpose |
|---|---|
| [Release evidence](release-evidence.md) | Exact integrated refs, merge states, measured limitations and root QA |
| [T01–T48 acceptance](acceptance.md) | Executable control mappings, frozen evaluation cases, partial/pending/gap evidence |
| [Demo and recovery](demo-runbook.md) | Five-minute product demonstration and state-preserving recovery |
| [Presentation sources](presentation/README.md) | Nine-slide English/Polish decks; generated PDFs stay ignored |
| [Submission template](submission-template.md) | User-owned team/member/URL and organizer fields |
| [Install and lifecycle](local-app.md) | One-command local app, credentials, offline restart and recovery |
| [Visual architecture](architecture.md) | Working path, trust boundaries, and target system |
| [Challenge alignment](challenge-alignment.md) | Supplied PDFs mapped to implemented controls, gaps and submission evidence |
| [Enterprise integration design](enterprise-integrations.md) | Bank-stack context, interface choices, diagram and verification boundaries |
| [Security event export](audit-export.md) | Implemented tenant-scoped JSONL, ECS-oriented records and Splunk HEC envelopes |
| [Full design](../AgentGate_Full_Project_Architecture.md) | Original requirements, decisions, protocols, and acceptance cases |
| [Document API](document-slice.md) | Implemented authentication, authorization, filtering, and audit contract |
| [Tool budgets](budgets.md) | Atomic scopes, uncertain usage, operator counters, and schema migration |
| [Semantic workers](semantic-workers.md) | Real standard/CoreML services, strict/observe behavior, bounds, and quality limitations |
| [Semantic v1](semantic-evaluation.md) | Frozen poor results and retained failed CoreML warm run |
| [Semantic v2](semantic-v2-evidence.md) | Fresh imperfect holdout, real CPU gateway smoke and experimental Apple status |
| [Local telemetry delivery](telemetry-delivery.md) | Actual local protocol, durable retry/dedup; separate from vendor envelopes |
| [Inference evidence](inference-spike.md) | Actual standard Laya and CoreML loading, predictions, and limitations |
| [Delivery plan and skills](delivery.md) | Ordered milestones, acceptance evidence, and installed skill choices |
| [Environment readiness](readiness.md) | Verified local tooling and remaining integration work |
| [Cezar task visibility](cezar.md) | Where implementation and validation progress appear |
| [Development workflow](../SDLC.md) | Implementation, review, QA, and publication rules |
| [Compatibility](../BACKWARD_COMPATIBILITY.md) | Public contracts and storage changes |
| [Third-party notices](../THIRD_PARTY_NOTICES.md) | Dependency and model provenance |

The full design describes the intended product. The implementation documents
describe observed behavior; a planned component is not a security guarantee.
