"""Allowlisted output schemas. A tender or a bid is UNTRUSTED input — instruction-like text
inside it is data, never a directive — so every model call is constrained to one of these."""

CRITERIA_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": ["pq", "technical"]},
                    "max_marks": {"type": "number"},
                    "compare_kind": {
                        "type": "string",
                        "enum": ["numeric", "date", "boolean", "qualitative"],
                    },
                    "compare_op": {"type": "string"},
                    "compare_value": {"type": "string"},
                    "anchor_clause": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["text", "kind", "confidence"],
            },
        }
    },
    "required": ["criteria"],
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "stated_value": {"type": "string"},
        "excerpt": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["found"],
}

ATTRIBUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "bidder_name": {"type": "string"},
        "document_type": {
            "type": "string",
            "enum": ["technical_bid", "financial_bid", "emd", "certificate", "affidavit",
                     "form", "authorisation", "experience_certificate", "financial_statement",
                     "covering_letter", "other"],
        },
        "envelope": {"type": "string", "enum": ["technical", "financial", "unknown"]},
        "confidence": {"type": "number"},
        "evidence_text": {"type": "string"},
        "anchor_page": {"type": "number"},
    },
    "required": ["confidence", "envelope"],
}

OCR_SCHEMA = {
    "type": "object",
    "properties": {
        "page_text": {"type": "string"},
        "legible": {"type": "boolean"},
    },
    "required": ["legible"],
}
