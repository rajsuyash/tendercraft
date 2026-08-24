"""What fields does GeM actually publish? Key names only — never values.

Two jobs, and the second is why this ships rather than being a throwaway script.

**1. Answering "is X available without a login?"** The honest way to settle whether a portal
exposes something is to enumerate what it exposes, not to reason about what a portal probably
does. UML's ask 4 turns on exactly this question for clarifications and additional-document
requests, and it was answered by inference for two weeks before anyone looked.

**2. Detecting schema drift.** `extract_csrf_token` fails loudly when the page structure
changes, but a *field* quietly disappearing from the Solr document is silent: `_first` returns
None, `normalize` emits a record with a null, and the feed keeps working with a hole in it. A
scheduled diff of this output is how that gets noticed in a day instead of a quarter.

**Why returning key names is not reproduction (§8).** GeM's copyright policy governs the
*contents* of the site. A field name is the shape of the response, which is the same for every
bid and describes no tender. Values never leave this module — `_describe` records a type and
whether something was present, and deliberately has no branch that copies a value out. The one
exception is nothing: there is no `sample_value` parameter, because the first time someone adds
one "just for debugging" it will be a buyer's name in a log.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

#: Substrings worth flagging in a field name. Not a filter — everything is returned — but a
#: probe whose output is 90 keys is useless if the reader has to spot the interesting one.
INTERESTING = (
    "corrigend", "clarif", "amend", "addend", "revis", "extend",
    "document", "doc_", "_doc", "attach", "annexure",
    "status", "stage", "eval", "query", "reply", "response",
)


def _kind(value: Any) -> str:
    """The shape of a value, never the value."""
    if isinstance(value, list):
        inner = _kind(value[0]) if value else "empty"
        return f"list[{inner}]"
    return type(value).__name__


def _is_empty(value: Any) -> bool:
    if isinstance(value, list):
        return not value or all(_is_empty(v) for v in value)
    if isinstance(value, str):
        return not value.strip()
    return value is None


def describe_fields(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Union of key names across `docs`, with presence counts and value SHAPES.

    Presence and emptiness are reported separately on purpose: a key that is present on every
    record and empty on every record is a field GeM defined and does not populate, which is a
    different answer to "can we have this?" than the key being absent altogether. Reading the
    first as availability is how a feature gets built against a column of nulls.
    """
    kinds: dict[str, Counter] = {}
    present, non_empty = Counter(), Counter()

    for doc in docs:
        for key, value in doc.items():
            present[key] += 1
            kinds.setdefault(key, Counter())[_kind(value)] += 1
            if not _is_empty(value):
                non_empty[key] += 1

    fields = [
        {
            "key": key,
            "present_in": present[key],
            "non_empty_in": non_empty[key],
            "kinds": sorted(kinds[key]),
            "interesting": any(marker in key.lower() for marker in INTERESTING),
        }
        for key in sorted(present)
    ]
    return {
        "docs_sampled": len(docs),
        "field_count": len(fields),
        "fields": fields,
        "flagged": [f["key"] for f in fields if f["interesting"]],
        "note": "Key names and value shapes only. No field values are read or returned "
                "(docs/discovery/source-gem.md §8).",
    }
