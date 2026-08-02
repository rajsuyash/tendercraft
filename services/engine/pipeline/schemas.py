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
                    # The model proposes a class; app.deterministic.drafting decides.
                    # requires_citation / is_financial are NOT model-supplied — they were,
                    # and that made the B-AC4 hard gate unreachable (the prompt told the
                    # model to always report is_financial:false).
                    "proposed_class": {"type": "string", "enum": ["claim", "narrative"]},
                },
                "required": ["text", "proposed_class"],
            },
        },
    },
    "required": ["has_sufficient_evidence", "sentences"],
}

# Long-form section output. Carries STRUCTURE (heading, order, subsections) — which
# DRAFT_SCHEMA cannot, which is why a proposal was one flat paragraph per criterion.
# Note what is absent from the class enum: "assembled" and "placeholder" are Python-only,
# so a model can never claim to be a transclusion (B-FR3) or a sourcing placeholder (B-FR2).
SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "has_sufficient_context": {"type": "boolean"},
        "confidence": {"type": "number"},
        "subsections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "order": {"type": "number"},
                    "sentences": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "citations": {"type": "array", "items": {"type": "string"}},
                                "proposed_class": {
                                    "type": "string",
                                    "enum": ["claim", "narrative"],
                                },
                            },
                            "required": ["text", "proposed_class"],
                        },
                    },
                },
                "required": ["heading", "sentences"],
            },
        },
    },
    "required": ["has_sufficient_context", "confidence", "subsections"],
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


# Relevance band (F-FR11) — the model's fit signal for one tender against a vendor capability.
#
# `band`, never a score. The PRD is explicit that a decimal implies a precision this signal does
# not have, and a bidder shown 0.62 will reason about the second digit. The enum makes an
# out-of-range answer impossible rather than merely unlikely.
#
# `matched_capability` is the citation: the part of the bidder's OWN statement that makes the
# tender fit. Empty means the model could not point at one, which the caller treats as low —
# the same cite-or-flag discipline the drafter follows (G-5).
RELEVANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "opportunity_id": {"type": "string"},
                    "band": {"type": "string", "enum": ["high", "medium", "low"]},
                    "rationale": {"type": "string"},
                    "matched_capability": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["opportunity_id", "band", "rationale", "confidence"],
            },
        }
    },
    "required": ["results"],
}


#: Keyword suggestions (F-FR11 support). Bounded and closed: `source` is an enum so a proposal
#: cannot claim an origin we did not give it, and `evidence` is required so every term can be
#: checked against the text it came from before a human accepts it.
KEYWORDS_SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "source": {
                        "type": "string",
                        "enum": ["statement", "existing", "website"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["keyword", "source", "evidence"],
            },
        }
    },
    "required": ["keywords"],
}
