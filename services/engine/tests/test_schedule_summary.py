"""A line that states no specification is not an unassessed product line.

Every live line item comes from NIT prose rather than a BOQ row, so the schedule legitimately
contains "Past Performance 30 %" and "Compliance of BoQ specification". A manufacturing
envelope cannot answer those, and counting them as unknown buries the real verdicts.

The distinction is only available AFTER extraction has run — before that, zero parameters means
"not read yet". `specs_extracted_at` is what separates the two, which is why the summary takes
it rather than inferring it from the rows.
"""

from __future__ import annotations

from app.spec_service import _summarise


def _line(state: str, parameters_read: int) -> dict:
    return {"catalogue_state": state, "parameters_read": parameters_read}


def test_before_extraction_nothing_is_called_a_non_product_line():
    lines = [_line("unknown", 0), _line("unknown", 0)]
    s = _summarise(lines, extracted=False)
    assert s["not_a_product_line"] == 0
    assert s["unknown"] == 2
    assert s["awaiting_read"] == 2


def test_after_extraction_a_line_with_no_parameters_is_not_a_product_line():
    lines = [_line("unknown", 0), _line("creatable", 3)]
    s = _summarise(lines, extracted=True)
    assert s["not_a_product_line"] == 1
    assert s["awaiting_read"] == 0
    # It must leave the unknown bucket, or the two are still conflated on screen.
    assert s["unknown"] == 0
    assert s["creatable"] == 1


def test_the_buckets_always_add_up_to_the_total():
    # One function computes every counter, so a screen can never show a number nothing
    # explains (docs/known-pitfalls.md: four counters describing one object will disagree).
    lines = [_line("published", 2), _line("creatable", 1),
             _line("not_creatable", 4), _line("unknown", 2), _line("unknown", 0)]
    s = _summarise(lines, extracted=True)
    assert (s["published"] + s["creatable"] + s["not_creatable"]
            + s["unknown"] + s["not_a_product_line"]) == s["total"] == 5
