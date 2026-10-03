---
name: om-prepare-test-env
description: Reuse the installed Laya Sec Layer QA environment and its owned lifecycle.
---

Run `.ai/scripts/test-env-up.sh` from the repository root. Read its ignored
`.ai/qa/test-env.json` descriptor for the URL and state path. The helper prepares
the actual packaged product via `./laya install`, waits for owned services and
checks authenticated operator readiness. Do not start a separate development
server or reset databases to make a test pass.

Prerequisites: uv/Python 3.12 and the manifest-pinned local Ollama model. Shared
Ollama is never owned or stopped by this helper. The descriptor's credential-file
reference is private; use its token only inside a process/browser login, never in
arguments, output, screenshots, commits or browser storage.

The warm path checks the tracked-source fingerprint/mtime, 600-second TTL, PID
liveness, supervisor ownership and authenticated readiness. `--force` restarts
owned services; `--force-rebuild` also invalidates the preparation fingerprint.
Source changes require reinstalling the non-editable wheel, not importing directly
from the checkout. An unchanged wheel reuses prepared dependencies. Preserve keys,
active controls, credential epochs, approvals and tool/model/semantic budgets.

`.ai/scripts/test-env-down.sh` stops only this checkout's private installation.
It is idempotent. No guessed-PID/port kills or Docker-wide cleanup is permitted.

Browser verification uses the real product:

```sh
uv run --locked --with playwright python tests/frontend/browser_check.py \
  --url <descriptor.baseUrl> --state-dir <descriptor.stateDir>/data \
  --artifacts .ai/qa/artifacts_fullstack
```

Prepare Playwright Chromium separately if absent. `--model` additionally invokes
the actual configured provider; coordinate the single heavyweight inference slot.
The ordinary suite does not claim inference. It temporarily changes live policy,
feed and a QA-owned credential expiry, restores configuration at newer audited
revisions, and retains side-effect/audit/budget evidence. Use this isolated QA
installation, never an operator's unrelated state. Failed runs are not erased.

Verified on macOS: cold launch, warm reuse (0.244 s), source-touch invalidation,
double stop, restart (7.406 s), and unchanged private tokens/epochs/budget accounts.
These are observations, not performance guarantees. Scripts and this note must
stay in sync when bootstrap behavior changes.
