"""Allowlisted model-output schemas (G-6).

Tender text is untrusted; the model may only emit JSON matching these shapes — no free
text, no tool calls. Anything off-schema is rejected by the client and routed to fallback.
"""

from app.deterministic.spec_params import PARAM_KEYS
from app.deterministic.types import CheckType

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

# What a pre-bid gate DEMANDS. Not what the bidder has, and not whether they clear it.
#
# What is absent here is the design. The previous schema (`CRITERION_EVAL_SCHEMA`) carried
# `model_verdict`, `actual_value_cr` and `exemption_applies`, and app/analysis.py let all
# three decide: a numeric branch compared two model-supplied numbers with no confidence or
# evidence check at all, so a model at confidence 0.01 produced a hard PASS, and one `true`
# on `exemption_applies` turned NO-BID into BID with no clause resolved anywhere.
#
#   - `verdict` — absent. The model deciding its own result is the defect being fixed.
#   - `actual_value_cr` — absent. The bidder's own number is a row Python holds. The model is
#     not even shown the profile any more, so it cannot report one.
#   - `evidence_ids` — absent. Python names the rows it actually used; a model cannot
#     hallucinate an id it was never given.
#   - `gap_note` — absent. Python formats the shortfall from the two numbers it just
#     compared, which is strictly better prose and cannot be wrong.
#   - `exemption_applies` — replaced by `exemption_for` (which CLASSES the tender's own text
#     grants) plus the clause. Whether this bidder is in one of those classes is a profile
#     lookup, not an opinion.
#
# `check` is rendered from `deterministic/types.CheckType` — the enum IS the G-6 allowlist,
# the same shape SPEC_PARAMS_SCHEMA uses for its registry keys.
ELIGIBILITY_REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "check": {"type": "string", "enum": [c.value for c in CheckType]},
        "operator": {"type": "string", "enum": [">=", "<=", ">", "<", "=="], "nullable": True},
        "threshold_cr": {"type": "number", "nullable": True},
        "fy_count": {"type": "integer", "nullable": True},
        "fy_labels": {"type": "array", "items": {"type": "string"}},
        "min_count": {"type": "integer", "nullable": True},
        "years_window": {"type": "integer", "nullable": True},
        "certification_name": {"type": "string", "nullable": True},
        "registration_key": {
            "type": "string",
            "enum": ["udyam", "mse", "msme", "dpiit", "startup", "gst", "pan", "cin"],
            "nullable": True,
        },
        "exemption_for": {
            "type": "array",
            "items": {"type": "string",
                      "enum": ["mse", "msme", "udyam", "dpiit", "startup", "make_in_india"]},
        },
        "exemption_clause": {"type": "string"},
        "raw_text": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["check", "raw_text", "confidence"],
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


#: Requirement -> answer pairs mined from a bid the client already SUBMITTED (G-FR3).
#: `answer_text` must be copied verbatim from the document — the deterministic layer verifies
#: that it actually appears in the source before storing, so a paraphrase is dropped rather
#: than stored. Reuse is only worth anything if the words are the ones the evaluator accepted.
ANSWER_PAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "pairs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "requirement_text": {"type": "string"},
                    "answer_text": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["requirement_text", "answer_text", "confidence"],
            },
        }
    },
    "required": ["pairs"],
}

# Module H — free-text spec -> typed parameters. EXTRACTION ONLY.
#
# There is deliberately NO verdict field here, and that absence is the point. The older
# CRITERION_EVAL_SCHEMA carried `model_verdict`, `actual_value_cr` and `exemption_applies`,
# and app/analysis.py let all three decide — a model deciding eligibility, which PRD §2.4
# forbids. Module H never repeated it, and the eligibility path has now been rebuilt the same
# way (ELIGIBILITY_REQUIREMENT_SCHEMA above): the model reads, `app/deterministic/` decides,
# and the two are separated at the schema rather than at the router, where a future edit
# could quietly rejoin them.
#
# `param_key` is an enum rendered from the registry — the G-6 allowlist. A hostile tender
# document cannot invent a parameter name any more than it can invent a criterion category, and
# an unregistered key never reaches a comparison.
#
# `equivalence` is absent on purpose too: whether a requirement permits an equivalent is derived
# in Python from the requirement's own text (spec_params.allows_equivalent). Letting the model
# report the field that softens its own result is the `is_financial` defect in
# docs/known-pitfalls.md.
SPEC_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "parameters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "param_key": {"type": "string", "enum": list(PARAM_KEYS)},
                    "kind": {"type": "string", "enum": ["numeric", "enum"]},
                    # As STATED in the text. Never converted by the model — spec_params owns
                    # unit conversion, so a hallucinated conversion cannot reach a verdict.
                    "unit": {"type": "string", "nullable": True},
                    "num_min": {"type": "number", "nullable": True},
                    "num_max": {"type": "number", "nullable": True},
                    "enum_value": {"type": "string", "nullable": True},
                    # The substring this came from. A parameter with no visible source is an
                    # assertion, and the extractor is not permitted to make one.
                    "raw_text": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["param_key", "kind", "raw_text", "confidence"],
            },
        }
    },
    "required": ["parameters"],
}
