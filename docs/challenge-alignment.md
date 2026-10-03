# Laya Sec Layer: alignment with the AI Control Layer challenge

Assessment dated 2026-10-03. The product the user calls **laya-sec-layer** is the
AI control layer being implemented here as AgentGate. This assessment concerns
that product. The implementation is a document-enforcement prototype, not a
complete competition submission or an enterprise deployment.

The supplied `AI Control Layer.pdf` (4 pages, B1) and `TaC AI Control Layer.pdf`
(3 pages, B2) were read in full. The scoring pages were also rendered and checked
visually. Original PDFs are not republished in this repository. Their SHA-256s:

- B1: `786a9bb4a858f98dd178085dc27ad5fb81d599a523d9318901ef2a0ff6aaf11c`
- B2: `31a3fb1537ac1d02d3f4c8e22989b2a377d82c1f7ff2df749f461de695784924`

The baseline reviewed was `ed49820`; the accompanying security-event-export
change adds the reporting capability explicitly marked below. A count of tests
or completed development tasks is not a percentage of challenge completion.

## Requirement-to-evidence map

| Requirement in B1 | Observed implementation | Remaining evidence needed |
|---|---|---|
| Intercept agent/model/MCP/API interactions; simple architecture diagram (§§2–3, p. 2) | Authenticated REST `documents.read` path and Mermaid diagrams | Actual model facade and a real agent integration; MCP is a chosen project adapter, not a separately mandated brand/protocol demo |
| Central policy with strictness, allowed models, resource/financial budgets (§4.1, p. 3) | Validated policy file, roles/classifications, output controls, tool limits; optional semantic enforce/observe mode | Model allowlist, per-model/provider controls, token/money limits, audited atomic activation; current changes require restart |
| Deterministic controls (§4.2, p. 3) | Server-owned identity, tenant and role authorization, strict request parsing, email redaction, synthetic-secret marker blocking | Broader data classifications and realistic held-out leakage cases; the marker scanner is not general DLP |
| Semantic controls (§4.2, p. 3) | Authenticated standard Laya and native CoreML workers inspect document results; complete-input check and fail-closed deadlines | Model-input/output/tool-argument stages; held-out quality evaluation. Initial label smoke was 2/4 and benign notes abstained |
| External and local resource governance (§2, p. 2; §4.3, p. 3) | Atomic tenant/day, principal/day, root-run document-call budgets; worker concurrency, input cap and deadline | Provider-attempt reservations, money/tokens, cumulative per-scope local inference quotas and reconciliation of uncertain consumption |
| Historical exploit patterns; externally managed signatures (§2, p. 2; §4.4, p. 3) | Narrow executor registry and pinned model-file hashes provide limited preventive boundaries | Data-only threat feed, validation/version/expiry/activation, named safe exploit fixtures and assertions showing mitigation; no generic CVE coverage claim |
| Interactive dashboard, security posture, resource/cost metrics (§3.3 and §4.5, p. 3) | Local audit and budget CLI; this change adds scoped JSONL/ECS-oriented/HEC-envelope export | Authenticated product UI, event-derived metrics, live updates, latency telemetry, accurate cost display and collector delivery evidence |
| Positive and negative executable tests (§4.6, p. 3; §6, p. 4) | Gateway, policy, budget race/failure and worker-lifecycle tests; export tests use real gateway-generated records | Full implemented-control acceptance matrix, actual generation/agent integration, held-out semantic evaluation, deployment and performance tests |
| Spontaneous prompts and config/feed changes (§6, p. 4) | Document-ID demo is callable; limits are configurable at startup | A running agent/model demo, prompt entry, safe policy/feed changes without partial activation, visible decision/effect changes |
| Own setup without supplied paid services (§7, p. 4) | Gateway and both local classifiers have run on own hardware | Validated local generation model, predictable resource footprint, offline end-to-end startup and recovery |

Implementation evidence: [document contract](document-slice.md),
[tool budgets](budgets.md), [semantic evidence](semantic-workers.md),
[new export contract](audit-export.md), and the corresponding `tests/` suites.
Passing classifier process/coverage checks does not establish classifier accuracy.

## Delivery focus

The current architecture points toward the requested product. The most important
completion work is an end-to-end AI interaction, resource accounting, and reporting:

1. Model facade plus one local generation model. Prove allowed/blocked/redacted
   inputs and outputs, bounded results, per-attempt budgets and non-bypassable routing
   within the documented deployment boundary.
2. Product dashboard and policy activation. Show controls, decisions, semantic
   coverage, budget usage and measured latency. Distinguish executed-but-withheld
   results from operations prevented before dispatch.
3. Threat-feed update and safe exploit fixtures, with malformed/stale feed cases.
   Neither feed content nor model output may grant authorization.
4. Complete one telemetry delivery route in a local lab, using the new export
   format. Test actual ingestion, retries, partial failures, duplicate handling,
   restart and secret exclusion before claiming a connector works.
5. Run the full offline judge scenario and prepare the submission. Additional
   bank-specific adapters should not displace the core AI-control demonstration.

These are recommendations for finishing this product, not requirements to deploy
inside a bank. The brief does not require Goldman Sachs credentials or a named
SIEM. Vendor integration can strengthen practical applicability and reporting.

## Submission details and discrepancies

| Criterion | B1 §8, p. 4 | B2 §11, p. 2 |
|---|---:|---:|
| Robustness and guardrails | 30% | 30% |
| Architecture and performance | 20% | 20% |
| Security reporting | 20% | 20% |
| Self-testing | 15% | 20% |
| Implementability and scalability | 15% | 10% |

The documents disagree on the last two weights; no scoring precedence is inferred.
Both make reporting a substantial part of the assessment.

B2 §5, p. 1 requires a title, team name, 1–6 team members, description and PDF
presentation of at most ten slides; submission is through HackTribe in English
or Polish. These assets are not delivered by passing the code tests. The same
clause states 23:00 on October 3 as the earliest start and 23:00 on October 4 as
the submission cutoff, without a timezone. These hours and the weighting
discrepancy need organizer clarification; no eligibility decision is made here.
See also the original architecture §2 for the previously recorded discrepancies.
