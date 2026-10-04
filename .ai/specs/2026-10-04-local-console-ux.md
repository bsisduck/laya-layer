# Make the local HR workflow understandable and keep evidence within reach

## Observed problem
At main 671979e, the packaged no-login app works, but the HR page opens with a long technical identity table. A desktop user reaches the first read only below the fold; on mobile it takes several screens. Results and errors appear below the entire proposal form. Two summary/source links have the same audit label. Disabled controls imply loading through a wait cursor. Overview buries department usage and standards below unrelated long sections. These problems obscure the actual governance decisions.

## User intent and scope
Preserve the cream/forest/orange visual language, local-console access without a login screen, and actual backend controls. Improve the primary HR read → draft → exact review → local outbox flow and the operator shell/navigation. This does not make experimental semantics or fixture integrations production-ready.

## Acceptance criteria
- HR opens with a concise purpose, explicit next step, and a compact numbered three-step progression: start bounded HR session, read/summarize, draft/review follow-up. Progress labels reflect actual state; never pretend a step succeeded or sent a message merely on an HTTP return.
- Present requester/agent/expiry and the start/end actions compactly. Keep complete grants/accounting/provenance and boundary explanation accessible through disclosure. Explain expired/revoked/inactive states next to disabled controls and a deliberate recovery action. Preserve bounded handles, renewal, exact approvals, immutable payloads, expiry invalidation and no automatic replay.
- Put read/summary results and errors next to the source action, draft/approval results next to that action, and lifecycle feedback next to start/end. Distinguish a protected read whose output was withheld from an operation not dispatched. Only display a summary if the real response supplies it. Distinct source/model/action audit links and raw evidence disclosure remain.
- Draft input validation catches missing/invalid email/empty subject/body before dispatch, keyboard accessible. Replace implementation jargon such as 'Use a new proposal key' with a clear explicit new-draft action; do not silently rotate keys or retry mutations. Edits never reuse a previous approval. Keep consumed replay explicit with no duplicate effect.
- Move future adapter explanations out of the primary task flow into compact disclosure/link; preserve availability honesty.
- Improve navigation/discoverability of measured department usage and standards/control evidence (e.g. overview section navigation using the existing route query). Deep links and browser back work, preserve existing routes. Avoid adding a second giant navigation rail or technical explanations to the employee workflow.
- Keep current UI style; mobile 390px and desktop 1440px readable without page-level horizontal overflow. Visible keyboard focus, adequate target sizes, correct disabled/busy states, meaningful error/empty/loading states. No new framework, fonts/network dependencies, or auth changes.
- Record readiness limits excluding authentication: actual issue #51 benign semantic false positive remains; local outbox is not SMTP; generated-key issuer is not real corporate IAM; local telemetry formats/collector are not verified external SIEM/bank deployment; purpose-specific standards evidence is not compliance certification.

## Validation
Meaningful pure frontend unit/contract tests for changed decision presentation and states. Installed-wheel functional/integration/E2E HR flow must retain negative permission/expiry/recovery/approval/payload-mismatch/no-duplicate/outbox and provider effect assertions. Add regression checks for adjacent feedback, invalid draft preventing requests, keyboard and mobile. Use existing .ai test-env helpers in owned worktree only. Run make validate with pinned Hermes source. Run browser_components/shared shell checks appropriate to navigation, inspect actual screenshots rather than merely capture. Freeze final head for independent root review/QA before merge. Separate fixture/control proof from real semantic efficacy; no new inference needed for a UI change.

## Selected skills
Open Mercato om-ux-shape, om-code-review, om-prepare-test-env, om-integration-tests; installed frontend-testing-debugging and frontend-design for preserving existing style and browser evidence. Skills search completed; no extra installation required.
