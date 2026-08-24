"""The probe reports shape, and must never report content."""

from __future__ import annotations

from app.schema_probe import describe_fields


def test_presence_and_emptiness_are_counted_separately():
    """A key GeM defines but never fills is a different answer to "can we have this?" than a
    key that is absent — reading the first as availability builds a feature on a null column."""
    result = describe_fields([
        {"b_corrigendum": []},
        {"b_corrigendum": []},
        {"b_corrigendum": ["2"]},
    ])
    field = next(f for f in result["fields"] if f["key"] == "b_corrigendum")

    assert field["present_in"] == 3
    assert field["non_empty_in"] == 1


def test_a_whitespace_string_counts_as_empty():
    """GeM pads absent values rather than omitting them; " " is not data."""
    field = describe_fields([{"k": "  "}, {"k": "x"}])["fields"][0]
    assert field["non_empty_in"] == 1


def test_no_field_value_appears_anywhere_in_the_output():
    """§8: the shape of a response describes no tender. A value would."""
    secret = "Usha Martin Limited"
    dumped = repr(describe_fields([{"b_seller": [secret], "b_price": [4_661_420]}]))

    assert secret not in dumped
    assert "4661420" not in dumped and "4_661_420" not in dumped
    assert "b_seller" in dumped  # the name is the point


def test_interesting_keys_are_flagged_not_filtered():
    """Everything is returned. Flagging is for the reader, and a filter here would decide in
    advance what the probe is allowed to discover — which is the mistake it exists to fix."""
    result = describe_fields([{"b_clarification_date": [], "b_price": []}])

    assert result["flagged"] == ["b_clarification_date"]
    assert {f["key"] for f in result["fields"]} == {"b_clarification_date", "b_price"}


def test_an_empty_sample_does_not_crash():
    """A query matching nothing is a normal answer, not a failure."""
    assert describe_fields([]) | {} == describe_fields([])
    assert describe_fields([])["field_count"] == 0
