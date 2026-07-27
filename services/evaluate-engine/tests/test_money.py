"""Reading a bid total (F14). Money is the most dangerous field in this product.

The bidder engine already recorded the lesson: an RFP saying "Rs. 5 Crore" and a bid saying
"Rs. 12.40 Crore" must not become 50000000 and 12.4, or a qualifying bidder silently fails and
nothing looks wrong. Here the same figure decides the ranking, so the rule is stricter — when
the document is ambiguous we return None and a human types it.
"""

from decimal import Decimal

import pytest

from evaluate.deterministic.money import extract_total, parse_amount


# ── Indian numbering ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("Rs. 5 Crore", 50_000_000),
    ("₹12.40 Crore", 124_000_000),
    ("5 Cr", 50_000_000),
    ("Rs. 45 Lakh", 4_500_000),
    ("₹45.5 lakhs", 4_550_000),
    ("INR 1,20,00,000", 12_000_000),      # 2-2-3 grouping, not 3-3-3
    ("₹70,60,000/-", 7_060_000),          # the /- is decoration
    ("Rs 12,00,000", 1_200_000),
])
def test_parse_amount_reads_indian_conventions(text, expected):
    assert parse_amount(text) == Decimal(expected)


def test_crore_beats_a_bare_number_in_the_same_line():
    """'Rs. 5 Crore (50000000)' must be 5 crore once, not the digits read separately."""
    assert parse_amount("Total Bid Value: Rs. 5 Crore") == Decimal(50_000_000)


@pytest.mark.parametrize("text", ["no figures here", "", "Rs. abc", "12"])
def test_parse_amount_returns_none_when_it_cannot_read(text):
    assert parse_amount(text) is None


@pytest.mark.parametrize("text", ["Rs. ,, Crore", "Rs. ,, Lakh"])
def test_a_figure_made_only_of_separators_is_unreadable(text):
    """`[\\d,]+` matches a bare comma, so a mangled OCR line reaches the parser as ",,".
    It must come back None rather than raising out of an ingest loop."""
    assert parse_amount(text) is None


# ── finding the total on a page ────────────────────────────────────────────────
def test_extracts_a_labelled_total_with_its_page():
    pages = [(1, "cover"), (4, "Item 1 | 58,20,000\nTotal Bid Value (INR): 70,60,000")]
    assert extract_total(pages) == (Decimal(7_060_000), 4)


def test_ignores_line_items_and_reads_only_the_labelled_total():
    """A price schedule is mostly numbers. Only the labelled total is the bid."""
    pages = [(1, "Item 1 | 4,85,000\nItem 2 | 3,10,000\nGrand Total: 7,95,000")]
    assert extract_total(pages) == (Decimal(795_000), 1)


def test_a_repeated_agreeing_total_is_not_a_conflict():
    """A summary page restating the schedule is normal, not ambiguity."""
    pages = [(3, "Total Bid Value: 70,60,000"), (9, "Total Bid Value: 70,60,000")]
    assert extract_total(pages) == (Decimal(7_060_000), 3)


def test_two_disagreeing_totals_route_to_a_human():
    """Picking the larger would be a guess; picking the last would be a guess about layout.
    A wrong total silently reorders the ranking and the audit says a machine read it right."""
    pages = [(3, "Total Bid Value: 70,60,000"), (9, "Grand Total: 82,10,000")]
    assert extract_total(pages) == (None, None)


def test_no_labelled_total_routes_to_a_human():
    pages = [(1, "Item 1 | 4,85,000\nItem 2 | 3,10,000")]
    assert extract_total(pages) == (None, None)


def test_a_zero_total_is_not_accepted():
    """A ₹0 quote is either a parse failure or a bid needing human attention — never a price
    the ranking divides by."""
    assert extract_total([(1, "Total Bid Value: 0")]) == (None, None)


def test_a_labelled_total_that_cannot_be_parsed_routes_to_a_human():
    assert extract_total([(1, "Total Bid Value: as per annexure")]) == (None, None)


def test_empty_input():
    assert extract_total([]) == (None, None)
