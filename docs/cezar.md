# Where progress appears

[Cezar on port 4322](http://localhost:4322) shows runs started through Cezar.
Work performed directly in the Codex conversation does not automatically appear
as a task. An empty cockpit therefore did not mean the repository was empty;
it meant no workflow had been started there.

The original development workspace contains actual verification runs for document enforcement,
atomic budgets, semantic worker boundaries, and the project documentation. Their
task descriptions link to the published implementation and its evidence. They
verify work authored in the Codex session; they are not fabricated historical
implementation runs. Its pinned **Project map** task contains the roadmap.
Task history is local and ignored by Git, so a fresh checkout starts empty.

To record a new full validation run:

```sh
make harness         # leave this running if it is not already open
make harness-verify  # in another terminal
```

`harness-verify` checks that the cockpit belongs to this repository, starts the
check-only `agentgate-verify` workflow, and returns its ID. Open Tasks to inspect
the live command and actual result. It runs in the current working tree and does
not launch a coding agent. Wait for completion before changing the tested files.
The title records the starting commit and notes any uncommitted changes; the
workflow does not create an immutable snapshot. Port 4322 is the default; for
another port use `python3 .ai/scripts/cezar_verify.py --port 4323`.

The **New task** composer can run the `agentgate-local` implementation workflow
when you explicitly want Cezar to launch a separate coding session. That workflow
implements one bounded task and runs validation; it is different from the checks
above. Keep one implementation owner per branch/worktree.

These are development views, not the AgentGate operator dashboard. The product's
operator dashboard remains a planned milestone. For the graphical system design,
open [architecture](architecture.md); for what works now and what comes next, open
[delivery](delivery.md). Completion of a Cezar check does not certify a release.
