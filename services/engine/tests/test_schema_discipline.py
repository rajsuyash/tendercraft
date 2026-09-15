"""No model schema may carry a field that DECIDES anything (PRD §2.4).

This is the check that would have caught the defect, and it is worth being precise about why
the one that exists could not. `.github/workflows/ci.yml` greps `app/deterministic/` for
`pipeline|google|anthropic|openai` imports and fails the build — that check is correct and
must stay. But `app/analysis.py` is the ADAPTER layer: it is supposed to import from
`pipeline`, and it does not live under `app/deterministic/`. An import grep cannot see a
model deciding eligibility from there, which is exactly where `model_verdict`,
`actual_value_cr` and `exemption_applies` decided it for months.

So the check is structural instead of positional: walk every JSON schema the model is ever
given and refuse a field name that names an outcome. A model that has nowhere to put a
verdict cannot supply one, whatever a hostile tender document tells it to do (G-6) and
whatever a future prompt edit asks for.

Names, not values, on purpose. A field called `actual_value_cr` is a bidder fact the model
cannot have seen; a field called `passed` is a decision. Both are unreachable by any
well-meaning edit that only touches the prompt.
"""

from __future__ import annotations

import re

import pytest

from pipeline import schemas

#: Substrings that name an OUTCOME or a bidder-side FACT. Each one has a story.
BANNED = (
    "verdict",        # model_verdict — decided every non-numeric criterion behind a 0.75 gate
    "actual",         # actual_value_cr — a bidder figure the model was never shown
    "passed",
    "eligible",
    "applies",        # exemption_applies — one bare boolean turned NO-BID into BID
    "is_financial",   # the model self-reporting the field that gated its own output (B-AC4)
    "requires_citation",
    "decision",
    "compliant",
    "qualifies",
)

#: Fields that legitimately contain one of the banned substrings. Empty, and it should stay
#: that way — an entry here is a decision someone must argue for in review.
ALLOWED: frozenset[str] = frozenset()


def _schemas() -> dict[str, dict]:
    return {
        name: obj for name, obj in vars(schemas).items()
        if name.isupper() and isinstance(obj, dict) and "properties" in str(obj)
    }


def _field_names(node, out: list[str]) -> list[str]:
    """Every property name anywhere in a schema, however deeply nested.

    Nesting is the point: `SPEC_PARAMS_SCHEMA` and the answer-miner schema both put their
    real fields two levels down inside an array's `items`, so a check that only reads the
    top-level `properties` would pass while proving nothing about them.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                out.extend(value.keys())
            _field_names(value, out)
    elif isinstance(node, list):
        for item in node:
            _field_names(item, out)
    return out


def test_there_is_more_than_one_schema_to_check():
    """A walk that finds nothing passes exactly as loudly as a walk that finds everything
    clean. Pin the floor so a refactor that renames the module cannot silently disarm this."""
    found = _schemas()
    assert len(found) >= 5, found
    assert "ELIGIBILITY_REQUIREMENT_SCHEMA" in found


@pytest.mark.parametrize("name", sorted(_schemas()))
def test_no_schema_lets_the_model_decide_an_outcome(name):
    fields = _field_names(_schemas()[name], [])
    offending = [
        f for f in fields
        if f not in ALLOWED and any(b in f.lower() for b in BANNED)
    ]
    assert not offending, f"{name} lets the model decide: {offending}"


def test_the_eligibility_schema_carries_no_bidder_side_field_at_all():
    """The stronger claim for the one schema this was actually wrong on. The model is not
    given the profile, so any field describing the bidder would have to be invented."""
    fields = set(_field_names(schemas.ELIGIBILITY_REQUIREMENT_SCHEMA, []))
    assert fields == {
        "check", "operator", "threshold_cr", "fy_count", "fy_labels", "min_count",
        "years_window", "certification_name", "registration_key", "exemption_for",
        "exemption_clause", "raw_text", "confidence",
    }


def test_the_analyzer_prompt_is_never_handed_the_profile():
    """The structural half of the fix, pinned in one line. `extract_requirement` takes no
    profile argument, and the prompt has no token to interpolate one into — so the model
    physically cannot see the bidder's numbers and cannot report them. That is worth more
    than every instruction in the prompt about not reporting them."""
    from pathlib import Path

    from pipeline import analyzer

    text = (Path(analyzer.__file__).resolve().parents[1] / "prompts" / "analyzer.md").read_text()
    assert "{{CRITERION}}" in text
    assert not re.findall(r"\{\{\s*(?!CRITERION)\w+\s*\}\}", text)

    from inspect import signature
    assert list(signature(analyzer.extract_requirement).parameters) == ["criterion_text"]
