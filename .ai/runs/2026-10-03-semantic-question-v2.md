# Validate a usable versioned semantic question profile

Source doc: .ai/specs/full-stack-delivery.md
Issue: #29; delivery dependency: #16
Engine: om-auto-create-pr (steps: 7, --loop: no)

## Goal

Deliver an explicitly versioned two-choice semantic profile with honest fresh
EN/PL measurements and real gateway allow/block evidence, preserving deterministic
authority and the frozen v1 evaluation.

## Scope and decisions

Use the exact neutral2 development-3 question, including its neutral2 question key,
A/B descriptions and operation/prompt state. The eight development examples are
selection evidence only (7/8, English quotation false positive). Name the new
contract content-role-v2; map actual A/B probabilities to task_data and
behavior_instruction without inventing unclear or a confidence threshold.
V1 stays the CLI/API compatibility default; installer may explicitly activate
v2 only after measured readiness. Unknown/mismatched versions fail closed.

Keep 1024 tokens, 32 KiB, concurrency one and five-second native deadline. Do not
change auth/ACL/DLP/feed/budget enforcement. Reuse the evaluation harness with an
explicit version selector. Preserve every v1 artifact/hash and document the exact
PR23 checkout for reproducing its unchanged engine. Freeze at least 26 new paired
EN/PL cases with labels/coverage before inference; never tune on that corpus.

No merges, additional agents, downloads, fallback, claims of universal protection,
or changes to installer/client branches. Publish this task's plan/draft/commits/
ready PR as authorized. Coordinate inference with existing client/installer runs.
Independent enforcement review is a release gate; author review is not independent.

## Implementation Plan

### Phase 1: Versioned contract

1.1 Bind v1/v2 across engine, result validation, authenticated worker/client and CLI.
1.2 Add consuming-boundary tests and compatibility/protocol documentation.

### Phase 2: Frozen evaluation

2.1 Version the existing runner and freeze a new 26+ case EN/PL corpus and protocol.
2.2 Run standard CPU then native CoreML once under the frozen protocol; preserve all failures.

### Phase 3: Application and delivery evidence

3.1 Exercise real HTTP gateway ordinary allow, malicious block and hard-control denials.
3.2 Record metrics, raw-report hashes, resource limits and CoreML failure investigation.
3.3 Run full validation and OM review, publish evidence and ready PR without merging.

## Risks

Two options provide no learned abstention or calibrated uncertainty. Correct
interpretation of task_data is ordinary/allowed/discussed content, not permission.
Fresh held-out results may expose false positives/negatives; report them without
relabelling or tuning. CoreML may time out; keep experimental status if unstable.
Independent review remains required before integration/release.

## Progress

PR: #32

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Versioned contract

- [x] 1.1 Bind v1/v2 across engine, result validation, authenticated worker/client and CLI. — b466537
- [x] 1.2 Add consuming-boundary tests and compatibility/protocol documentation. — b466537

### Phase 2: Frozen evaluation

- [x] 2.1 Version the existing runner and freeze a new 26+ case EN/PL corpus and protocol. — b466537
- [x] 2.2 Run standard CPU then native CoreML once under the frozen protocol; preserve all failures. — 43ea6e6

### Phase 3: Application and delivery evidence

- [x] 3.1 Exercise real HTTP gateway ordinary allow, malicious block and hard-control denials. — f503b0f
- [x] 3.2 Record metrics, raw-report hashes, resource limits and CoreML failure investigation. — f503b0f
- [ ] 3.3 Run full validation and OM review, publish evidence and ready PR without merging.
