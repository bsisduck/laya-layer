# Security event export — author review

**Verdict: approve** for the bounded prototype export and documentation change.
This author review does not replace independent review before a production release.

An operator can export existing evidence into three formats with an explicit
tenant selection, stable event IDs and bounded snapshot pagination. The existing
gateway routes, policy decisions, budgets, `audit` command and database schema
are unchanged. Export opens the database read-only and performs no network calls.
The new CLI is protected by host filesystem access, not a new tenant-auth API.

The allowlist excludes raw semantic dictionaries and payload digests in addition
to the content/credential exclusion already enforced by the audit writer. Cursor
advancement follows scanned rows, including empty filtered pages; fixed upper
sequences exclude concurrent appends. Invalid, oversized or mismatched records
fail before stdout is written. Execution uncertainty and post-execution output
denial remain visible to consumers. No source severity or invoice amount is invented.

No blocker, major, minor or nit findings remain in this scope. The implementation
deliberately stops at serialization: durable transport, collector authentication,
acknowledgments, replay/deduplication, vendor mappings and bank deployment checks
are documented as future work. A local scan cursor is not a delivery receipt.

| Validation | Result |
|---|---|
| `make validate` | PASS: config/lock, Ruff/format, strict mypy, 163 tests, source/wheel packaging |
| New export suite | PASS: 28 cases covering real gateway-generated evidence, privacy, tenant/unattributed filters, pagination, read-only state, compatibility and CLI failure behavior |
| Installed CLI against existing demo audit | PASS: 28 records in each of JSONL, ECS-oriented and HEC-envelope formats; valid snapshot metadata |
| Live vendor ingestion / bank endpoint | NOT RUN: no connector or configured target in this slice; no integration claim |

The supplied PDFs were read in full and their scoring pages visually checked.
The assessment preserves the documented scoring discrepancy. Vendor-interface
sources support the design; user-supplied bank research remains explicitly scoped
as discovery context. Original PDFs and private machine paths are not committed.
