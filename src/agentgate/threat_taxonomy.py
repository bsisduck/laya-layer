"""Versioned explanatory taxonomy. Associations never establish intent or authority."""

import hashlib
import json

from pydantic import JsonValue

from agentgate.contracts import AuditEvent, Reason

VERSION = "laya-threat-v1"
LEVELS = (
    (
        "L0",
        "Accident",
        "Przypadek",
        "Ordinary mistakes and benign controls",
        "Bounded secret/email fixtures and budgets",
        "No PESEL/IBAN/card recognition",
    ),
    (
        "L1",
        "Direct known attempt",
        "Bezpośrednia znana próba",
        "Explicit prohibited instruction, model or operation",
        "Model/tool allowlists and deterministic policy",
        "Not universal jailbreak prevention",
    ),
    (
        "L2",
        "Concealment / evasion",
        "Ukrywanie / omijanie",
        "Representation change, fragmentation or paraphrase",
        "Buffered split-secret checks; experimental semantics",
        "No general base64/Unicode normalization; missed paraphrases",
    ),
    (
        "L3",
        "Indirect content",
        "Treść pośrednia",
        "Untrusted retrieved, document or tool content",
        "Scoped reads and result inspection",
        "Semantic false positives; no active-image exfiltration control",
    ),
    (
        "L4",
        "Agent authority / action abuse",
        "Nadużycie uprawnień / działań",
        "Delegated scope, tool composition or immutable approval",
        "Exact approvals, scoped reads and shared root budgets",
        "No broad multi-step exfiltration correlation or OS sandbox",
    ),
    (
        "L5",
        "Control / supply-chain target",
        "Atak na kontrolę / łańcuch dostaw",
        "Control availability, integrity or artifact provenance",
        "Last-good CAS, durable audit, quotas and metadata intake",
        "No feed signatures or two-person change approval",
    ),
)
LAYERS = (
    ("identity", "Identity / permissions", "Tożsamość / uprawnienia"),
    ("input", "Input", "Wejście"),
    ("data", "Data", "Dane"),
    ("actions", "Actions", "Działania"),
    ("output", "Output", "Wyjście"),
    ("consumption", "Consumption", "Zużycie zasobów"),
    ("supply_chain", "Supply chain", "Łańcuch dostaw"),
)
OWASP = {
    **{
        f"LLM{i:02d}:2025": name
        for i, name in enumerate(
            (
                "Prompt Injection",
                "Sensitive Information Disclosure",
                "Supply Chain",
                "Data and Model Poisoning",
                "Improper Output Handling",
                "Excessive Agency",
                "System Prompt Leakage",
                "Vector and Embedding Weaknesses",
                "Misinformation",
                "Unbounded Consumption",
            ),
            1,
        )
    },
    **{
        f"ASI{i:02d}:2026": name
        for i, name in enumerate(
            (
                "Agent Goal Hijack",
                "Tool Misuse",
                "Identity and Privilege Abuse",
                "Agentic Supply Chain Vulnerabilities",
                "Unexpected Code Execution",
                "Memory and Context Poisoning",
                "Insecure Inter-Agent Communication",
                "Cascading Failures",
                "Human-Agent Trust Exploitation",
                "Rogue Agents",
            ),
            1,
        )
    },
}


def taxonomy() -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "taxonomy_version": VERSION,
        "level_meaning": "Authored scenario types, not severity or live attacker sophistication",
        "runtime_level_status": "unknown",
        "levels": [
            {
                "id": i,
                "name": n,
                "name_pl": pl,
                "assignment": rule,
                "controls": controls,
                "gaps": gaps,
                "coverage": "partial",
            }
            for i, n, pl, rule, controls, gaps in LEVELS
        ],
        "layers": [{"id": i, "name": n, "name_pl": pl} for i, n, pl in LAYERS],
        "owasp": dict(OWASP),
        "sources": [
            "https://genai.owasp.org/llm-top-10/",
            "https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/",
        ],
        "mapping_basis": "Reviewed contextual crosswalk; no confirmed vulnerability or OWASP endorsement",
    }


def taxonomy_digest() -> str:
    return hashlib.sha256(
        json.dumps(taxonomy(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


# Finite control associations; operational errors not listed here remain unmapped.
ASSOCIATIONS: dict[Reason, tuple[tuple[str, ...], tuple[str, ...]]] = {
    **{
        r: (("identity",), ("LLM06:2025", "ASI03:2026"))
        for r in (
            Reason.AUTHENTICATION_REQUIRED,
            Reason.INVALID_CREDENTIAL,
            Reason.IDENTITY_OVERRIDE,
        )
    },
    Reason.RESOURCE_NOT_ALLOWED: (("identity", "data"), ("LLM06:2025", "ASI03:2026")),
    Reason.MODEL_NOT_ALLOWED: (("identity",), ("LLM06:2025", "ASI02:2026")),
    **{
        r: (("identity", "actions"), ("LLM06:2025", "ASI02:2026"))
        for r in (
            Reason.UNKNOWN_OPERATION,
            Reason.OPERATION_NOT_ALLOWED,
            Reason.RECIPIENT_DOMAIN_NOT_ALLOWED,
        )
    },
    **{
        r: (("identity", "actions"), ("LLM06:2025", "ASI09:2026"))
        for r in (
            Reason.REQUIRES_APPROVAL,
            Reason.APPROVAL_DENIED,
            Reason.APPROVAL_EXPIRED,
            Reason.APPROVAL_APPROVED,
            Reason.APPROVAL_MISMATCH,
        )
    },
    **{
        r: (("consumption",), ("LLM10:2025",))
        for r in (
            Reason.BUDGET_EXCEEDED,
            Reason.SEMANTIC_BUDGET_EXCEEDED,
            Reason.REQUIRED_SEMANTIC_UNAVAILABLE,
        )
    },
    Reason.AUDIT_UNAVAILABLE: (("supply_chain",), ("LLM03:2025", "ASI04:2026")),
    Reason.CONTROLS_CHANGED: (("supply_chain",), ("LLM03:2025", "ASI04:2026")),
}


def threat_context(event: AuditEvent) -> dict[str, JsonValue]:
    layers: set[str] = set()
    owasp: set[str] = set()
    for reason in event.reason_codes:
        association = ASSOCIATIONS.get(reason)
        if association:
            layers.update(association[0])
            owasp.update(association[1])
        if reason in (Reason.SECRET_IN_INPUT, Reason.SECRET_IN_OUTPUT, Reason.EMAIL_REDACTED):
            layers.add("data")
            owasp.add("LLM02:2025")
            if reason == Reason.SECRET_IN_INPUT and event.operation in (
                "chat.completions",
                "mail.send",
            ):
                layers.add("input")
            elif (
                reason == Reason.SECRET_IN_OUTPUT
                or event.event_type == "output_blocked"
                or (
                    reason == Reason.EMAIL_REDACTED
                    and event.operation in ("documents.read", "memory.query")
                    and event.event_type == "action_completed"
                )
            ):
                layers.add("output")
        if reason in (
            Reason.SEMANTIC_BLOCKED,
            Reason.SEMANTIC_ABSTAIN,
            Reason.SEMANTIC_INCOMPLETE,
            Reason.SEMANTIC_INVALID,
        ):
            if event.event_type == "output_blocked":
                layers.add("output")
            elif event.event_type == "action_denied":
                layers.add("input")
            owasp.update(("LLM01:2025", "ASI01:2026"))
    return {
        "schema_version": 1,
        "taxonomy_version": VERSION,
        "candidate_levels": [],
        "level_status": "unknown",
        "basis": "control_context_only",
        "intent": "not_assessed",
        "layers": [i for i, _, _ in LAYERS if i in layers],
        "owasp": [i for i in sorted(owasp)],
    }
