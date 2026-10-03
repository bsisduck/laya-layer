# Code review: document enforcement and real inference loading

## Verdict

**approve** for the scoped local implementation. The configured validation gate
passes and the changed authorization boundary has HTTP-level denied-path evidence.
This is a self-review, not the independent review required by `SDLC.md` before
releasing authentication or tenant-isolation changes.

## Summary

The new REST path authenticates a server-bound credential, checks agent scope,
role, tenant and classification, commits dispatch intent, reads a synthetic
fixture, filters output, and audits before release. The architecture's remaining
model/tool routes are absent and are documented as unimplemented.

Review scope: the implementation branch against local `main`, including the final
loading-spike changes. Applied `om-code-review`, its full checklist,
`CODE_REVIEW.md`, and `BACKWARD_COMPATIBILITY.md`. No remote operations were performed.

## Resolved findings

- Expiry was initially sampled before acquiring the SQLite writer lock. The
  dispatch transaction now samples the clock after lock acquisition; a regression
  test holds the real database lock and expires the credential before releasing it.
- Long/unclosed synthetic markers could evade the original bounded matching
  pattern. Detection now blocks the designated prefix; regression coverage proves it.
- The standard Laya loader rewrote a pinned tokenizer file. The spike now runs
  normalization on a disposable copy, records its resulting digest, and preserves
  the verified snapshot. Both real inference runs and post-run hashes were checked.

## Validation gate

| Configured command | Status | Evidence |
|---|---|---|
| `make validate` | PASS | Workflow/config and lock checks, Ruff lint/format, strict mypy, 57 pytest cases, sdist and wheel build. |

Additional observed checks: live HTTP allowed/denied/redacted/blocked-output and
missing-credential cases; persisted audit pairs; actual standard/CoreML inference;
all 18 pinned model asset hashes verified; MCP 2.3.0 server/schema construction.

## Contracts and remaining scope

This introduces initial unreleased HTTP, policy, CLI, and SQLite-v1 contracts;
there is no prior released API or database migration to preserve. Existing harness
commands remain available. Model files, private state and generated reports are ignored.

The 57 tests cover a subset of the architecture scenarios, with parametrized cases;
they do not imply 48/48 architecture scenarios. Both real backends matched only
2/4 expected loading-fixture labels. Semantic workers, budgets, approvals, MCP
transport, Hermes, provider routing, and the dashboard remain future implementation.
