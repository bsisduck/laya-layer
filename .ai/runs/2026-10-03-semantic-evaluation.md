# Real semantic evaluation and resource envelope

Source doc: .ai/specs/full-stack-delivery.md
Issue: #15 (E04-S01)
Engine: om-auto-create-pr (steps: 5, --loop: no)

## Goal and scope

Reproducibly measure the existing content-role-v1 engine on separately frozen
synthetic EN/PL cases. Reuse verified local assets, run standard CPU and native
CoreML CPU/GPU separately, and publish honest quality/coverage/resource evidence.
No policy/auth changes, model downloads, other agents, labels, merge, ANE/energy
claims, universal protection, or persistent semantic-budget implementation.

## Implementation Plan

### Phase 1: Freeze and measure

1.1 Commit distinct paired labels, question/config hashes and a fixed protocol
before held-out inference. Retain the existing v1 question unchanged to establish
an honest shipped-contract baseline; do not tune on held-out results.
1.2 Implement validated offline evaluation, minimized reports, provenance,
all-case/conditional metrics, slices, disagreements, cold/warm timings and resources.
1.3 Test metric math, frozen provenance, invalid scores/coverage, failure reporting,
serialization and bounded process lifecycle using declared deterministic fixtures.

### Phase 2: Verify and deliver

2.1 Run actual standard and CoreML sequentially with no other active worker;
record every case, including abstentions and over-capacity results.
2.2 Run make validate, author OM code review, tracked measured summary, publish
ready PR and confirm CI. Explicitly disclose T28 and integration limitations.

## Risks

Tiny synthetic corpus is not population accuracy. Content-role labels are not
maliciousness probabilities. Repetitions measure warm performance, not independent
quality samples. Resource usage excludes exact device placement/energy and the
broader gateway path. Existing HTTP worker deadlines and deterministic gates remain.

## Progress

PR: #23

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Freeze and measure

- [x] 1.1 Freeze labels and evaluation contract — b4922c4
- [ ] 1.2 Implement real evaluation and minimized reporting
- [ ] 1.3 Verify math and failure handling deterministically

### Phase 2: Verify and deliver

- [ ] 2.1 Measure both real backends sequentially
- [ ] 2.2 Validate, review and publish measured delivery
