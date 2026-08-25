"""Which awards are actually about what was searched for (UML ask 5).

The strings below are real: every "should not match" case was pulled from the live corpus after
a fetch for "wire rope" returned 40 awards, one of which was wire rope.
"""

from __future__ import annotations

import pytest

from app.deterministic.price_history import (
    _pattern,
    category_matches,
    postgrest_filter,
)

#: Verbatim from `award_results` after a live fetch for "wire rope", 2026-08-25.
LIVE_NOISE = [
    "Pressure Roller,Keyboard and Mouse,Teflon Sleeve,Printer Head wire bush",
    "Assembled PC,Print Machine,HDMI CABLWire,Digimore Mic Set,Power Cable",
    "Iron Shed Size 10x10,Garden Light,Aluminium Service Wire 6mm two core",
    "Industrial Partition 40 ft x 7.5 ft for Bulk Store with 3.5 feet wire Mesh",
    "Customized AMC/CMC for Pre-owned Products",
]
LIVE_HIT = "Wire Rope For Wire Rope Barrier"


# ---------- the phrase rule ----------

def test_the_one_real_wire_rope_award_matches():
    assert category_matches("wire rope", LIVE_HIT)


@pytest.mark.parametrize("category", LIVE_NOISE)
def test_none_of_the_live_noise_matches(category):
    """These are what GeM actually returned for "wire rope". Averaging a winning price across
    them and steel rope would be a benchmark someone prices a real bid against."""
    assert not category_matches("wire rope", category)


def test_a_plural_still_matches_the_phrase():
    """GeM writes "Steel Wire Ropes"; a bidder types "wire rope"."""
    assert category_matches("wire rope", "Steel Wire Ropes for Haulage Purposes IS 1856")


def test_a_comma_boundary_does_not_fabricate_a_phrase():
    """GeM joins bundles with commas. "…copper wire, rope ladder…" contains the words in order
    and is not a wire rope — the comma is a word break, not a space."""
    assert not category_matches("wire rope", "Insulated copper wire,Rope ladder 10m")


# ---------- the single-word rule ----------

def test_a_single_word_matches_whole_words_only():
    assert category_matches("rope", "Wire Rope For Wire Rope Barrier")


def test_rope_does_not_match_europe():
    """The reason substring matching had to go. Both halves of the rule agree on this."""
    assert not category_matches("rope", "Europe pattern hand tools")


def test_wire_does_not_match_cablwire():
    """Live string. A substring rule counted this as a wire tender."""
    assert not category_matches("wire", "Assembled PC,HDMI CABLWire,Power Cable")


def test_wire_does_match_a_real_wire_line_item():
    """Precision, not exclusion: someone searching "wire" should still see wire."""
    assert category_matches("wire", "Aluminium Service Wire 6mm two core")


def test_case_and_spacing_do_not_matter():
    assert category_matches("WIRE   ROPE", "wire rope, is 2266")


def test_an_empty_query_matches_everything():
    """"Show me the corpus" is a real request; returning nothing would look like an empty
    database rather than an unfiltered search."""
    assert category_matches("", "anything at all")
    assert category_matches("   ", "anything at all")


def test_a_missing_category_never_matches_a_real_query():
    assert not category_matches("wire rope", None)
    assert category_matches("", None)


# ---------- the SQL half must agree with the Python half ----------

def test_an_empty_query_adds_no_condition():
    assert postgrest_filter("") == {}


def test_a_phrase_becomes_a_bounded_pattern_tolerant_of_spacing():
    """`\\s+` rather than a literal space: the live corpus contains double spaces, and an
    `ilike '%wire rope%'` would silently miss those rows while Python matched them."""
    assert postgrest_filter("wire rope") == {"category": r"imatch.\ywire\s+rope"}


def test_a_single_word_becomes_a_fully_bounded_condition():
    """Closed at both ends, or "rope" matches "ropeway"."""
    assert postgrest_filter("rope") == {"category": r"imatch.\yrope\y"}


def test_a_double_space_in_the_data_matches_in_BOTH_halves():
    """The drift that motivated one shared pattern. Live GeM strings contain double spaces."""
    assert category_matches("wire rope", "Steel  Wire   Rope 6x36")
    assert r"\s+" in postgrest_filter("wire rope")["category"]


def test_a_prefix_does_not_count_as_the_word():
    """A hardwire rope is not a wire rope; a ropeway is not rope."""
    assert not category_matches("wire rope", "Hardwire rope assembly")
    assert not category_matches("rope", "Ropeway cabin spares")


@pytest.mark.parametrize("hostile", ["c+", "(2-core)", ".*", "rope' or '1'='1", "6mm|.*"])
def test_no_user_character_can_reach_the_pattern(hostile):
    """Stronger than escaping: the query is TOKENISED with `[a-z0-9]+`, so a metacharacter is
    dropped rather than escaped and cannot build a greedy or broken pattern — nor reach the
    database as anything but a bounded word. The `re.escape` in `_pattern` is belt-and-braces
    behind this, not the thing doing the work.

    It matters because this string is concatenated into a PostgREST condition.
    """
    condition = postgrest_filter(hostile).get("category", "")
    body = condition.removeprefix("imatch.").replace(r"\y", "").replace(r"\s+", " ")

    assert all(ch.isalnum() or ch == " " for ch in body), body


def test_both_halves_come_from_one_pattern():
    """Not a proof — the SQL half runs in Postgres — but it pins that they are ONE string with
    one substitution (`\\y` -> `\\b`). If someone hand-writes either form again, this fails."""
    for q in ("wire rope", "rope", "6x36"):
        sql = postgrest_filter(q)["category"].removeprefix("imatch.")
        assert sql.replace(r"\y", r"\b") == _pattern(q).replace(r"\y", r"\b")
