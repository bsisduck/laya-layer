# Semantic worker review

## Verdict

Approve for prototype source publication. This author self-review does not replace
the independent security review needed before release.

## Summary

Document output can be inspected by a real standard Laya or native CoreML worker.
The supervisor authenticates requests, admits one job, validates the full result,
and kills/reaps failed native work. The gateway keeps deterministic permissions,
call accounting, output DLP, and durable audit authoritative.

## Findings and limits

No unresolved Blocker or Major findings for this document-result slice. Review
caught temporary model copies surviving forced child termination; the supervisor
now owns cleanup, covered by a real-process regression test. Failure audit status
now distinguishes invalid output from unavailable inference. No hidden retries,
fallbacks, or permission grants were introduced.

Both real HTTP profiles passed integration checks, but each matched only 2/4
unchanged expected labels. Both also abstained on benign document notes. This
is an explicit product-quality limitation, not passing classifier accuracy.
The strict profile withholds uncertain output; held-out evaluation and calibration
remain necessary. Inference-specific persistent quotas and other semantic stages
are not claimed. No frontend was changed.

## Validation Gate

| Command | Status | Evidence |
|---|---|---|
| `make validate` | PASS | Workflow/lock, lint/format, strict mypy, 135 tests, sdist/wheel |
| `semantic_gateway_smoke.py`, standard profile | PASS | Real HTTP worker and gateway, audit linkage, no inference on hard denial, capacity refusal; labels 2/4 |
| `semantic_gateway_smoke.py`, native CoreML profile | PASS | Same boundaries with real CoreML; labels 2/4 |

The deterministic tests cover invalid IDs/revisions/labels/scores/coverage,
worker authentication and size limits, response bounds/redirects, strict/observe
semantics, audit privacy, hard-denial precedence, busy admission, and actual
subprocess termination. Real reports are ignored local artifacts; the worker
runbook records conclusions and reproducible commands. These results do not
establish a production security classifier, hardware placement, or performance SLO.
