"""Price history (UML ask 5): the numbers, and the one this module refuses to invent."""

from __future__ import annotations

import pytest

from app.deterministic.price_history import Award, summarise, to_award


def _award(**over) -> Award:
    base = {
        "portal_ref_no": "GEM/2026/B/1", "source_id": "gem_bidplus",
        "category": "Wire Rope IS 2266",
        "department": "ONGC", "quantity": 100.0, "award_date": "2026-01-01T00:00:00Z",
        "winner": "J.S TRADERS", "winner_is_mse": True, "winning_price": 10000.0,
        "runner_up_price": 12000.0, "participants": 3, "source_url": "https://x.test/1",
    }
    return Award(**(base | over))


# --- the refusal that matters ---------------------------------------------------------------

def test_a_bundled_bid_yields_no_unit_price():
    """A real record from the live feed: four unrelated items in one bid. Dividing the total by
    quantity produces a per-unit figure someone would price a real bid against — confidently
    wrong, and worse than nothing."""
    a = _award(category="Wire Copper Insulated,Fevi Quick,Throttle Spray,Wire Connector Thimble")
    assert a.is_single_category is False
    assert a.implied_unit_price is None


@pytest.mark.parametrize("category", [
    "Wire Rope and Slings", "Rope + Fittings", "Rope, Thimble",
])
def test_every_bundling_marker_suppresses_the_unit_price(category):
    assert _award(category=category).implied_unit_price is None


def test_a_single_category_bid_with_a_quantity_does_yield_a_unit_price():
    assert _award().implied_unit_price == 100.0


def test_a_missing_or_zero_quantity_yields_no_unit_price():
    assert _award(quantity=None).implied_unit_price is None
    assert _award(quantity=0).implied_unit_price is None


def test_a_missing_category_yields_no_unit_price():
    assert _award(category=None).implied_unit_price is None


# --- the competitive spread ------------------------------------------------------------------

def test_the_undercut_says_how_much_room_the_winner_had():
    assert _award(winning_price=9000.0, runner_up_price=12000.0).undercut_pct == 25.0


def test_a_single_bidder_has_no_undercut_rather_than_a_zero():
    """Nobody to undercut is not "won by 0%" — that would read as a photo finish."""
    assert _award(runner_up_price=None).undercut_pct is None


# --- the summary ------------------------------------------------------------------------------

def test_typical_price_is_the_median_so_one_giant_award_cannot_move_it():
    """Government award values are wildly skewed; a mean would land past every observation."""
    awards = [_award(winning_price=p) for p in (9000, 10000, 11000, 400_000_000)]
    s = summarise(awards)
    assert s["typical_winning_price"] == 10500.0
    assert s["highest_winning_price"] == 400_000_000


def test_typical_is_suppressed_below_the_floor_rather_than_shown_small():
    """Two awards is not a market rate, and the word 'typical' carries more authority than
    the evidence behind it."""
    s = summarise([_award(winning_price=9000), _award(winning_price=11000)])
    assert s["typical_winning_price"] is None
    assert s["with_published_price"] == 2
    assert s["min_awards_for_typical"] == 3


def test_the_summary_says_how_many_awards_could_carry_a_unit_price():
    """A null unit price usually means 'these were bundles', not 'no data'. Without the
    denominator the user concludes the wrong one."""
    awards = [_award(category="Wire Rope IS 2266") for _ in range(3)] + [
        _award(category="Rope,Thimble,Grease") for _ in range(4)]
    s = summarise(awards)
    assert s["single_category_awards"] == 3
    assert s["typical_unit_price"] == 100.0
    assert s["awards"] == 7


def test_an_empty_history_reports_zeroes_not_an_error():
    s = summarise([])
    assert s["awards"] == 0
    assert s["typical_winning_price"] is None
    assert s["first_award"] is None


def test_the_date_span_is_the_five_year_window_the_ask_names():
    s = summarise([
        _award(award_date="2021-04-01T00:00:00Z"),
        _award(award_date="2026-08-01T00:00:00Z"),
        _award(award_date="2023-01-01T00:00:00Z"),
    ])
    assert s["first_award"] == "2021-04-01T00:00:00Z"
    assert s["last_award"] == "2026-08-01T00:00:00Z"


def test_mse_wins_are_counted_because_they_change_who_you_compete_with():
    s = summarise([_award(winner_is_mse=True), _award(winner_is_mse=False),
                   _award(winner_is_mse=True)])
    assert s["mse_wins"] == 2


# --- flattening a stored record ---------------------------------------------------------------

def test_the_winner_is_rank_one_and_the_runner_up_is_rank_two():
    a = to_award(
        {"portal_ref_no": "GEM/2026/B/9", "category": "Wire Rope", "quantity": "50",
         "participants": 3, "bid_end_date": "2026-01-01T00:00:00Z"},
        [{"rank": 2, "seller": "B", "total_price": "120", "mse": False},
         {"rank": 1, "seller": "A", "total_price": "100", "mse": True},
         {"rank": 3, "seller": "C", "total_price": "130", "mse": False}],
    )
    assert (a.winner, a.winning_price, a.winner_is_mse) == ("A", 100.0, True)
    assert a.runner_up_price == 120.0
    assert a.implied_unit_price == 2.0


def test_a_result_with_no_published_ladder_is_kept_without_inventing_a_price():
    """Before financial evaluation the page has participants but no prices. The record is real;
    the price is not yet, and a zero would be a fabricated fact."""
    a = to_award({"portal_ref_no": "GEM/2026/B/9", "participants": 4}, [])
    assert a.winning_price is None
    assert a.participants == 4
    assert summarise([a])["with_published_price"] == 0
