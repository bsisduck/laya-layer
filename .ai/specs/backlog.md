# Backlogs

## .ai/specs/full-stack-delivery.md

Backlog source: .ai/specs/full-stack-delivery.md
Last filed: 2026-10-03

Source: [authorized delivery specification](https://github.com/bsisduck/laya-sec-agent/blob/1ab151ef09619eaf4409b4af86908910d80dbb41/.ai/specs/full-stack-delivery.md) in [spec PR #2](https://github.com/bsisduck/laya-sec-agent/pull/2), pinned at `1ab151e`. The [architecture](https://github.com/bsisduck/laya-sec-agent/blob/ed498205d3f76075272a3aeb7afb2ab70f36549d/AgentGate_Full_Project_Architecture.md) and its B1/B2 PDF source record define the challenge requirements; these are documented requirements, not market-research claims.

This mapping covers all four epics and nine stories in the source. IDs are preserved, and each issue contains acceptance criteria, decisions, non-goals, dependencies, contract implications and priority/risk rationale. GitHub is the live status authority; filing is not implementation or evaluation evidence.

Readiness: SDLC has no Definition of Ready section, so that gate was skipped; `om-setup-discovery-pipeline` can add it. Existing documented requirements and ordinary ticket hygiene were used. The user authorized the previously shown tree and all issue creation. Labels are disabled; priority/risk below are recorded classifications only, with a rationale comment on each issue.

Initial dedupe covered all open/closed issues and PRs, then three ID/semantic issue queries per item. No existing issues were found or adopted. PR #2 supplies the design; PR #1 supplies only the telemetry export foundation. Exact source/full-ID and title were checked again before each creation.

| ID | Issue | Title | Epic | Depends on | Priority / risk | Adopted |
|---|---|---|---|---|---|---|
| E01 | [#3](https://github.com/bsisduck/laya-sec-agent/issues/3) | Governed AI runtime | — | Child dependencies below | high / high | no |
| E02 | [#4](https://github.com/bsisduck/laya-sec-agent/issues/4) | Operator application and reporting | — | Child dependencies below | high / high | no |
| E03 | [#5](https://github.com/bsisduck/laya-sec-agent/issues/5) | Installation and real integrations | — | Child dependencies below | high / high | no |
| E04 | [#7](https://github.com/bsisduck/laya-sec-agent/issues/7) | Evaluation and release evidence | — | Child dependencies below | high / high | no |
| E01-S01 | [#8](https://github.com/bsisduck/laya-sec-agent/issues/8) | Operator control plane, live policy and threat feed | [E01 #3](https://github.com/bsisduck/laya-sec-agent/issues/3) | None | high / high | no |
| E01-S02 | [#9](https://github.com/bsisduck/laya-sec-agent/issues/9) | Private model routing and atomic resource budgets | [E01 #3](https://github.com/bsisduck/laya-sec-agent/issues/3) | None | high / high | no |
| E01-S03 | [#10](https://github.com/bsisduck/laya-sec-agent/issues/10) | Scoped tools, approvals and MCP | [E01 #3](https://github.com/bsisduck/laya-sec-agent/issues/3) | [E01-S01 #8](https://github.com/bsisduck/laya-sec-agent/issues/8), [E01-S02 #9](https://github.com/bsisduck/laya-sec-agent/issues/9) | high / high | no |
| E02-S01 | [#11](https://github.com/bsisduck/laya-sec-agent/issues/11) | Functional dashboard and playground | [E02 #4](https://github.com/bsisduck/laya-sec-agent/issues/4) | [E01-S01 #8](https://github.com/bsisduck/laya-sec-agent/issues/8), [E01-S02 #9](https://github.com/bsisduck/laya-sec-agent/issues/9), [E01-S03 #10](https://github.com/bsisduck/laya-sec-agent/issues/10) | high / high | no |
| E02-S02 | [#12](https://github.com/bsisduck/laya-sec-agent/issues/12) | Durable telemetry delivery and measured performance | [E02 #4](https://github.com/bsisduck/laya-sec-agent/issues/4) | [export PR #1](https://github.com/bsisduck/laya-sec-agent/pull/1), [E01-S01 #8](https://github.com/bsisduck/laya-sec-agent/issues/8) | high / high | no |
| E03-S01 | [#13](https://github.com/bsisduck/laya-sec-agent/issues/13) | One-command installation and lifecycle | [E03 #5](https://github.com/bsisduck/laya-sec-agent/issues/5) | [E01-S01 #8](https://github.com/bsisduck/laya-sec-agent/issues/8), [E01-S02 #9](https://github.com/bsisduck/laya-sec-agent/issues/9), [E01-S03 #10](https://github.com/bsisduck/laya-sec-agent/issues/10), [E02-S01 #11](https://github.com/bsisduck/laya-sec-agent/issues/11) | high / medium | no |
| E03-S02 | [#14](https://github.com/bsisduck/laya-sec-agent/issues/14) | Real agent and offline acceptance demo | [E03 #5](https://github.com/bsisduck/laya-sec-agent/issues/5) | [E01-S02 #9](https://github.com/bsisduck/laya-sec-agent/issues/9), [E01-S03 #10](https://github.com/bsisduck/laya-sec-agent/issues/10), [E03-S01 #13](https://github.com/bsisduck/laya-sec-agent/issues/13) | high / high | no |
| E04-S01 | [#15](https://github.com/bsisduck/laya-sec-agent/issues/15) | Real semantic evaluation and resource envelope | [E04 #7](https://github.com/bsisduck/laya-sec-agent/issues/7) | None | high / medium | no |
| E04-S02 | [#16](https://github.com/bsisduck/laya-sec-agent/issues/16) | Integrated security QA and submission | [E04 #7](https://github.com/bsisduck/laya-sec-agent/issues/7) | [E01-S01 #8](https://github.com/bsisduck/laya-sec-agent/issues/8), [E01-S02 #9](https://github.com/bsisduck/laya-sec-agent/issues/9), [E01-S03 #10](https://github.com/bsisduck/laya-sec-agent/issues/10), [E02-S01 #11](https://github.com/bsisduck/laya-sec-agent/issues/11), [E02-S02 #12](https://github.com/bsisduck/laya-sec-agent/issues/12), [E03-S01 #13](https://github.com/bsisduck/laya-sec-agent/issues/13), [E03-S02 #14](https://github.com/bsisduck/laya-sec-agent/issues/14), [E04-S01 #15](https://github.com/bsisduck/laya-sec-agent/issues/15) | high / high | no |

### Dependency and scope notes

- [E01-S01 #8](https://github.com/bsisduck/laya-sec-agent/issues/8) freezes the shared admin contracts before UI integration. [E01-S02 #9](https://github.com/bsisduck/laya-sec-agent/issues/9) can develop concurrently but must coordinate those state projections. Core tools in [E01-S03 #10](https://github.com/bsisduck/laya-sec-agent/issues/10) may be developed first; its integrated demo needs both runtime predecessors.
- [E02-S01 #11](https://github.com/bsisduck/laya-sec-agent/issues/11) needs the control plane for its core views; only model/tool portions wait for [E01-S02 #9](https://github.com/bsisduck/laya-sec-agent/issues/9) and [E01-S03 #10](https://github.com/bsisduck/laya-sec-agent/issues/10). The source’s medium/high dashboard risk is recorded as high because the UI handles privileged sessions, policy activation and exact approvals.
- [E02-S02 #12](https://github.com/bsisduck/laya-sec-agent/issues/12) depends on [export PR #1](https://github.com/bsisduck/laya-sec-agent/pull/1) and [E01-S01 #8](https://github.com/bsisduck/laya-sec-agent/issues/8). Local JSONL/ECS-oriented/Splunk HEC serialization does not complete acknowledged collector delivery, restart/retry durability or measured performance.
- [E03-S01 #13](https://github.com/bsisduck/laya-sec-agent/issues/13) depends on the runtime/UI contracts represented by [E01-S01 #8](https://github.com/bsisduck/laya-sec-agent/issues/8), [E01-S02 #9](https://github.com/bsisduck/laya-sec-agent/issues/9), [E01-S03 #10](https://github.com/bsisduck/laya-sec-agent/issues/10), [E02-S01 #11](https://github.com/bsisduck/laya-sec-agent/issues/11). Launcher scaffolding can start earlier; full clean-install acceptance needs the integrated application.
- [E04-S01 #15](https://github.com/bsisduck/laya-sec-agent/issues/15) may proceed independently, with standard and native CoreML evaluated separately. [E04-S02 #16](https://github.com/bsisduck/laya-sec-agent/issues/16) depends on every other story and owns integrated acceptance, not their implementation.

### Evidence and remaining decisions

Every story requires meaningful tests, review evidence and a focused PR. Deterministic fixtures, actual local generation, real semantic evaluation and end-to-end client runs must be reported separately. Auth/data/money/approval release boundaries require independent review or the explicit maintainer exception documented by SDLC.

The runtime owner selects and pins a local generation tag only after a real generation/tool-call spike. The telemetry owner selects and documents one local compatible collector and its acknowledgement semantics. These are implementation gates within the accepted scope, not invented product decisions.

The user owns team identity; the organizer owns scoring/start-time and any submission-eligibility clarifications. They remain explicit release/submission constraints in [E04-S02 #16](https://github.com/bsisduck/laya-sec-agent/issues/16). No organizer approval, actual submission, bank connection, enterprise SSO, certification or universal prompt-injection protection is implied.

Implementation is coordinated separately. This backlog PR changes only this mapping and does not merge or implement any runtime story.
