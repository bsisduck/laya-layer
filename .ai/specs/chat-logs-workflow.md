# Chat, Logs and Workflow — UX handoff

Intent: help local operators understand a governed conversation, inspect real
execution evidence and find the applicable controls without a large navigation
rail. Actor: an operator opening the packaged, login-free local console.

Choose three persistent top links and contextual subordinate links. A single
combined dashboard obscures the difference between authored examples and audit;
a drawer makes three choices harder to reach. Preserve the cream/forest/orange
identity with a compact editorial header, history rail and readable process map.

## Behavior

- Empty/unknown hash opens Chat. Chat contains four labelled synthetic histories:
  authorized HR read/summary, outside-scope data/egress denial, exact invitation
  review pending, retrieved-content injection denial. Each includes role/context,
  request/response, reason/layers, operation/data, policy, effects and next step.
  Selecting a case performs no API call. No composer or approval control exists
  in examples. Live HR workspace is the prominent actual execution entry.
- Logs opens the existing timeline, using only server events, filters and details.
  Operations, Department usage and Audit export remain contextual destinations.
- Workflow shows five request steps and Consumption/Supply chain rails. Clicking
  a step opens its implementation/gap detail. Actions splits read checks from
  consequential writes and destructive/irreversible proposals. Hard denies are
  final; permitted exact approval precedes server revalidation/dispatch. Reads
  require scope and checks. Undeclared operations are denied, unimplemented.
- All old hashes/query routes survive, with the correct primary parent active.
  Native links preserve keyboard and browser history. Dirty editors confirm
  departure; rejection restores the full previous hash. Session expiry clears
  private state; recovery does not retry mutations. No backend contracts change.
- Workflow associates GDPR Articles 9/22 with scoped access, filtering, exact
  review and audit, without claiming compliance or sensitive-category detection.
  Existing AI Act/DORA/OWASP evidence remains reachable. Articles 20/30 distinguish subject portability from organizational RoPA.
  Audit JSONL is not portability; technical logs are not a complete RoPA.

## States and recovery

| State | Display / action |
|---|---|
| Examples | “Synthetic scenarios · no requests or side effects”; select a case or open Live HR workspace |
| Loading | “Loading operator state…” with aria-busy; navigation stays available |
| Empty logs | “No matching events. Run an action or change the filters.” |
| Error | Service diagnostic plus “No current data to display. Check the service and refresh.” |
| Expired session | Existing bounded local recovery or credential unlock; deliberate retry only |
| Dirty policy | Existing discard confirmation; cancel retains editor and route |

## AI behavior and evidence limits

Rules first: this redesign introduces no AI. Canned responses are authored text,
not inference or audit. Existing HR generation retains the actual API, permission,
output and exact approval boundary. Requested capabilities are not an inventory;
implementation labels derive from source inspection. Real semantic accuracy is
outside this change. Legal associations link official sources, not certification.

## Acceptance and validation

All three top links visible at 360/390/768/1440px; no page overflow; keyboard,
aria-current, deep links and back/forward work. Contracts cover grouping, complete
example metadata and hard-deny/approval semantics. Installed browser tests verify
case switches cause zero protected calls; real logs and error/empty/loading;
layer details and branches; dirty-policy/session recovery. Existing installed HR,
exact approval and outbox suite runs with its declared provider fixture. Run
make setup then make validate and serial browser gates, inspect screenshots,
stop only owned QA services, and record exact head/results. Operator task success
and clear example/live distinction are the intended outcome; preserving real
execution/zero-effect denial assertions is the guardrail. No usability study or
real-model quality improvement is claimed. Independent review remains with root.
