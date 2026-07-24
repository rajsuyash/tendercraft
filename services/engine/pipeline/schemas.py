"""Allowlisted model-output schemas (G-6).

Tender text is untrusted; the model may only emit JSON matching these shapes — no free
text, no tool calls. Anything off-schema is rejected by the client and routed to fallback.
"""

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
