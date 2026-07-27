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
