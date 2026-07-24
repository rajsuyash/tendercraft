"""Allowlisted model-output schemas (G-6).

Tender text is untrusted; the model may only emit JSON matching these shapes — no free
text, no tool calls. Anything off-schema is rejected by the client and routed to fallback.
"""

# Knowledge-base document classification (auto-derive metadata from ingested text).
KB_DOC_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "doc_type": {
            "type": "string",
            "enum": [
                "financial", "certification", "completion", "undertaking",
                "cv", "company_profile", "other",
            ],
        },
        "valid_to": {"type": "string", "nullable": True},  # ISO date the doc expires, or null
        "structured_fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                "required": ["key", "value"],
            },
        },
    },
    "required": ["name", "doc_type"],
}

# Per-criterion eligibility evaluation against the vendor profile.
# The model EXTRACTS values and proposes a verdict; the deterministic layer DECIDES
# (compare_numeric for numeric, the 0.75 router for fuzzy) — §2.4.
CRITERION_EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "check_type": {
            "type": "string",
            "enum": ["numeric", "date", "experience", "registration", "other"],
        },
        "required_value_cr": {"type": "number", "nullable": True},
        "operator": {"type": "string", "enum": [">=", "<=", ">", "<", "=="], "nullable": True},
        "actual_value_cr": {"type": "number", "nullable": True},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "model_verdict": {"type": "string", "enum": ["pass", "fail", "needs_review"]},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
        "gap_note": {"type": "string"},
        "exemption_applies": {"type": "boolean"},
        "exemption_clause": {"type": "string"},
    },
    "required": ["check_type", "model_verdict", "confidence", "rationale", "evidence_ids"],
}

# Drafter output — narrative sentences, each tagged for the deterministic cite-or-flag check.
DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "has_sufficient_evidence": {"type": "boolean"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "string"}},
                    "requires_citation": {"type": "boolean"},
                    "is_financial": {"type": "boolean"},
                },
                "required": ["text", "requires_citation", "is_financial"],
            },
        },
    },
    "required": ["has_sufficient_evidence", "sentences"],
}

# Gemini responseSchema (OpenAPI subset) for criteria extraction.
CRITERIA_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "verbatim_text": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["eligibility", "technical", "financial", "terms"],
                    },
                    "requirement_level": {
                        "type": "string",
                        "enum": ["mandatory", "desirable", "self_attestation"],
                    },
                    "evidence_required": {"type": "string"},
                    "evaluation_weight": {"type": "number", "nullable": True},
                    "confidence": {"type": "number"},
                    "anchor_clause": {"type": "string"},
                },
                "required": [
                    "verbatim_text",
                    "category",
                    "requirement_level",
                    "confidence",
                    "anchor_clause",
                ],
            },
        }
    },
    "required": ["criteria"],
}
