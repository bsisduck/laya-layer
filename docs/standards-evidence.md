# Standards evidence associations

The operations view links each association to an implemented control, local
executable/documented evidence and a remaining obligation. These associations are
project interpretations, not legal advice, certification, compliance assessment,
legal risk score or bank integration. Applicability depends on the actual purpose,
system and deployment. Fixture control tests are not real-model evaluations.

Official sources rechecked 4 October 2026:

| Framework / provision | Local control and evidence | Remaining obligation |
|---|---|---|
| [RODO/GDPR Articles 9 and 22](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng) | Classification ACLs/filtering (`docs/document-slice.md`, `tests/test_gateway.py`); exact approvals and separate human authority (`docs/delegated-authority.md`, `tests/test_authority.py`). | Labels do not establish a legal basis for special-category processing. Review clicks do not establish Article 22 compliance or meaningful human involvement. Controller assesses conditions, automated decisions/effects/exceptions and safeguards. |
| [AI Act Annex III point 4 / Article 6](https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng) | Scoped authority and immutable audit (`docs/delegated-authority.md`); synthetic read/summary/message-review workspace (`docs/hr-workflow.md`). | No candidate ranking or hiring decision is implemented. HR use alone does not establish high-risk classification: intended purpose and applicable exceptions matter. |
| [AI Act Article 12](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-12) | Durable intent and ledger/terminal audit transaction (`docs/budgets.md`, `tests/test_models.py`, `tests/test_department_usage.py`). | Full system logging, retention and high-risk traceability require system-specific evidence. |
| [AI Act Article 14](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14) | Exact review and hard denials (`docs/scoped-tools.md`, `tests/test_authority.py`). | Competence, authority, interpretation, intervention and automation-bias safeguards remain organizational/system obligations. |
| [AI Act Article 26](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-26), [Commission context](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai) | Privileged operations, minimized audit and local delivery acknowledgments (`docs/control-plane-contract.md`, `docs/telemetry-delivery.md`). | Deployer instructions, monitoring, notifications and other applicable duties remain. No application-deadline claim is made. |
| [DORA official ESMA context](https://www.esma.europa.eu/publications-and-data/interactive-single-rulebook/dora) | Bounded controls, uncertain reservations and deterministic failure tests (`docs/budgets.md`, `tests/test_models.py`); local collector contract lab (`docs/telemetry-delivery.md`). | Entity-level ICT risk governance, incident classification/reporting, resilience testing and third-party arrangements need separate evidence. Local acknowledgments do not establish universal SIEM delivery. |
| [OWASP LLM Top 10, edition 2025](https://genai.owasp.org/llm-top-10/) | LLM02 disclosure/filtering; LLM06 agency/scoped execution; LLM10 consumption/reservation/freeze (`docs/threat-model.md`, `tests/test_models.py`). | Versioned associations, not certification, complete prevention or observed attack counts. |
| [OWASP Agentic Top 10, edition 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) | ASI02 tool misuse and ASI03 identity/privilege/exact grants; ASI09 trust exploitation/approval context (`docs/threat-model.md`, `tests/test_authority.py`). | Native host paths and ungoverned agents remain outside the protected boundary. No claim that these are the latest editions. |

EUR-Lex's exact ELI pages challenged the read-only fetch. GDPR text was separately
verified through the official [consolidated ELI text](https://eur-lex.europa.eu/eli/reg/2016/679/)
and [EDPB AI-model opinion](https://www.edpb.europa.eu/system/files/2024-12/edpb_opinion_202428_ai-models_en.pdf).
The Commission's official article/annex explorer identifies its text as based on
the 27 July 2026 consolidation; Annex III point 4 and Articles 12, 14 and 26 were
checked there. These checks support purpose-based wording only, without recalling
or inferring deadlines. ESMA's [DORA overview](https://www.esma.europa.eu/da/node/207346)
and official OWASP edition pages support the context/version associations.

The UI's evidence links target repository documents/tests, not generated reports
or raw private telemetry. Actual acknowledgments, backlog and delivery errors stay
visible in the existing audit delivery panel. Frozen semantic failures remain in
their existing evidence. The department report cannot allocate classifier GPU or
model cost per department; remote department export remains unavailable.
