# Production readiness beyond authentication

Laya Sec Layer is a working local prototype on a trusted computer. The no-login
local console remains intentional. This review excludes authentication and does
not certify a production deployment. See [release evidence](release-evidence.md)
for accepted commits and independent QA, and [HR workflow](hr-workflow.md) for the
exact supported journey.

## Working local demo

Registered document/scoped-tool REST and MCP requests use deterministic scope,
budget, output-release and audit controls. The synthetic HR facade uses those
same services, bounded sessions and immutable exact approvals. Approval creates
no message; explicit resume writes to the local fixture outbox, with replay
retaining one record. Department usage distinguishes known settlement from
unknown/reserved work. Console UX tests demonstrate presentation and navigation;
installed fixture tests demonstrate the tested control paths and effects.

## Production blockers and unverified integrations

- Actual standard Laya v2/enforce blocked the ordinary HR candidate output.
  [Issue 51](https://github.com/bsisduck/laya-sec-agent/issues/51) and the
  [retained HR observation](hr-release-observation.md) record the false positive,
  zero provider attempts and withheld output. Frozen missed attacks, poor scores
  and experimental CoreML results remain in the [semantic evidence](semantic-v2-evidence.md).
  Passing classifier/provider fixtures do not resolve this quality blocker.
- Mail is a local outbox, not SMTP. Dev merge and Finance payment adapters are
  unavailable examples. Real executors need separately reviewed downstream
  permissions, failure/reconciliation behavior and effect evidence.
- The optional issuer exchange was verified with generated keys and controlled
  clients, not real corporate IAM; see [issuer limits](issuer-exchange.md).
- Audit delivery is a local collector contract lab. ECS-oriented and HEC formats
  are not verified external SIEM, vendor or bank deployment; see
  [telemetry delivery](telemetry-delivery.md).
- Purpose-specific [standards associations](standards-evidence.md) connect
  controls to evidence and remaining obligations; they are not compliance
  certification or legal conclusions.
- The single-host SQLite/process-private HR state has documented restart, backup
  and rollback limits. Multi-host availability, sustained load/capacity, disaster
  recovery drills and native-client bypass isolation need deployment-specific
  verification against the [architecture](../AgentGate_Full_Project_Architecture.md).

## Dependency and test evidence

On 4 October 2026 the root reviewer supplied read-only PyPI `pip-audit` results:
34 locked gateway/MCP packages, 117 installed LiteLLM Python packages and 35
installed standard-semantic Python packages; each set had zero known
vulnerabilities and zero skips. Gateway scope used
`uv export --locked --no-dev --extra mcp --no-emit-project`, then
`pip-audit --no-deps --disable-pip` against that exported lock. The other two
audits used their actual installed Python site-packages. These are separate
environments, not a deduplicated total. No packages changed. The audit excludes
the Ollama binary, model assets, OS, npm development harness and unknown
vulnerabilities; it is not security certification.

The [release ledger](release-evidence.md) separates deterministic tests, installed
fixture effects and actual semantic observations. The issue 53 author evidence
is recorded in [console UX validation](local-console-ux-validation.md). Root
independent review and installed QA remain required before merge/install. No new
real inference is needed to validate this UI change, and no passing UI or setup
check is reported as real-model efficacy.
