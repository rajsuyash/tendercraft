"""The awarded price ladder (UML ask 5), pinned against a real GeM result page.

The fixture is the two tables of `GEM/2026/B/7876746` exactly as the portal served them on
2026-08-16 — backtick rupee glyph, `&nbsp;` padding, the display:none "Under PMA" label and
the HTML comment inside the Rank cell all included. A fixture written from memory would pin
what the parser expects rather than what the portal sends, which is the failure mode this
repo has already been bitten by (docs/known-pitfalls.md, on stubs that return more than the
real query).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.results import (
    RESULT_STATUSES,
    build_results_payload,
    parse_result_page,
    result_path,
    result_stage,
)

FIXTURE = (Path(__file__).parent / "fixtures" / "bid_result_standard.html").read_text()


# --- the query ---------------------------------------------------------------------------

def test_the_payload_asks_for_results_not_open_bids():
    import json

    p = json.loads(build_results_payload(1, "wire rope")["payload"])
    # Measured: `ongoing_bids` returns 737 wire-rope bids, `bidrastatus` returns 61,885.
    assert p["filter"]["bidStatusType"] == "bidrastatus"
    assert p["filter"]["byStatus"] == "bid_awarded"
    assert p["param"]["searchBid"] == "wire rope"


@pytest.mark.parametrize("status", RESULT_STATUSES)
def test_every_published_stage_is_queryable(status):
    assert build_results_payload(1, "", status)


def test_an_unknown_status_is_refused_rather_than_sent():
    """GeM IGNORES an unrecognised status and returns everything with message 'Bid result'.

    Measured: 'bid_won', 'bid_result' and 'awarded' each returned the identical unfiltered
    72,661. Sending one would report a category's entire history as its award history — a
    wrong answer with no error anywhere.
    """
    with pytest.raises(ValueError, match="unknown result status"):
        build_results_payload(1, "wire rope", "bid_won")


# --- which page holds this bid's result ----------------------------------------------------

def test_result_path_follows_gems_own_branching():
    assert result_path({"b_id": [1], "b_eval_type": [2]}).endswith(
        "getBidResultViewSchedule/1")
    assert result_path({"b_id": [2], "b_eval_type": [0], "ba_is_single_packet": [1]}).endswith(
        "getSinglePacketResultView/2")
    assert result_path({"b_id": [3], "b_eval_type": [0], "ba_is_single_packet": [0]}).endswith(
        "getBidResultView/3")


def test_a_missing_field_does_not_pick_the_wrong_page():
    """Solr omits fields rather than nulling them; the default must be the common shape."""
    assert result_path({"b_id": [9]}).endswith("getBidResultView/9")


@pytest.mark.parametrize("code,stage", [
    (0, "not_evaluated"), (1, "tech_evaluated"), (2, "fin_evaluated"), (3, "bid_awarded"),
])
def test_buyer_status_maps_to_the_lifecycle_stage(code, stage):
    assert result_stage({"b_buyer_status": [code]}) == stage


# --- the ladder ----------------------------------------------------------------------------

def test_the_winning_price_and_the_whole_ladder_are_read():
    r = parse_result_page(FIXTURE)
    assert [row.rank for row in r.ladder] == [1, 2, 3]
    assert r.winner.total_price == 9925.00
    assert r.winner.rank == 1
    assert [row.total_price for row in r.ladder] == [9925.00, 11631.00, 11680.00]


def test_the_seller_name_is_clean_of_portal_chrome():
    r = parse_result_page(FIXTURE)
    assert r.winner.seller == "J.S TRADERS"
    # "Under PMA" sits in a display:none span; stripping tags naively welds it onto the name.
    assert "PMA" not in r.winner.seller
    assert "MSE Social Category" not in r.winner.seller


def test_mse_status_is_kept_because_it_changes_who_you_are_bidding_against():
    r = parse_result_page(FIXTURE)
    assert r.winner.mse is True
    assert r.ladder[1].mse is False


def test_participants_include_sellers_who_did_not_win():
    """The competitive field is the point: three qualified, and all three are named."""
    r = parse_result_page(FIXTURE)
    assert len(r.participants) == 3
    assert all(p.status == "Qualified" for p in r.participants)
    assert any(p.seller == "DUTTA ENTERPRISES" for p in r.participants)
    assert r.participants[0].participated_on == "14-08-2026 18:54:13"


def test_the_offered_item_travels_with_the_price():
    r = parse_result_page(FIXTURE)
    assert "Wire Copper Insulated" in (r.winner.offered_item or "")


def test_a_page_with_no_published_prices_yields_an_empty_ladder_not_a_zero_price():
    """Before financial evaluation only the participants table renders. Reading it positionally
    would report a ladder of ₹0 bids — a fabricated fact, which is worse than no answer."""
    participants_only = FIXTURE.split("<!--TABLE-->")[0]
    r = parse_result_page(participants_only)
    assert r.ladder == ()
    assert r.winner is None
    assert len(r.participants) == 3


def test_an_unreadable_row_is_dropped_rather_than_defaulted():
    broken = FIXTURE.replace('<span class="bid_price">\n                                                                                9925.00</span>', "<span class='bid_price'>N/A</span>")
    r = parse_result_page(broken)
    assert all(row.total_price > 0 for row in r.ladder)


def test_the_serialised_shape_names_the_winner_explicitly():
    d = parse_result_page(FIXTURE).as_dict()
    assert d["winner"]["rank"] == 1
    assert d["participant_count"] == 3
    assert len(d["ladder"]) == 3


# --- the guardrail gap this work closed ----------------------------------------------------

def test_a_portals_own_captcha_now_halts_the_run():
    """Written up on 2026-08-07 and left open: `assert_no_bot_challenge` looked only for the
    commercial vendors, so it returned CLEAN on `/view_contracts`, which is captcha-gated on
    both search forms. A clean check read as permission. The failure it enables is silent —
    submit a blank captcha field, get an empty result set, record "no contracts found"."""
    from app.fetch import BotChallengeDetected, assert_no_bot_challenge

    view_contracts_markup = (
        '<label>Enter captcha code<span class="red req_date_bid">*</span></label>'
        '<input name="captcha_entered1" id="captcha_entered1">'
        '<input type="hidden" name="h_captcha1">'
    )
    with pytest.raises(BotChallengeDetected):
        assert_no_bot_challenge(view_contracts_markup, "/view_contracts")


def test_the_result_pages_we_do_read_are_still_clean():
    """The corollary. If the new markers were too broad they would halt the surface this
    feature depends on, and the price ladder would silently stop being collected."""
    from app.fetch import assert_no_bot_challenge

    assert_no_bot_challenge(FIXTURE, "/bidding/bid/getBidResultView/1")


# --- "no match" is an answer, not a failure -------------------------------------------------

def test_gem_reporting_no_data_is_an_empty_result_not_an_exception():
    """GeM answers a query that matched nothing with an HTTP-200 body carrying code 404.

    parse_page raised on it, which was harmless for the listing sweep (it never asks a question
    with no answer) and fatal for the per-bid status check, where "no" is the expected answer
    most of the time. Found live: /bid-results?status=tech_evaluated 500'd.
    """
    import json as _json

    from app.listing import parse_page

    total, docs = parse_page(_json.dumps({"code": 404, "message": "No data found"}))
    assert (total, docs) == (0, [])


def test_a_genuine_fault_still_raises():
    """Only the known empty-set message is treated as empty; anything else is still a fault."""
    import json as _json

    from app.listing import parse_page

    with pytest.raises(ValueError, match="503"):
        parse_page(_json.dumps({"code": 503, "message": "Service unavailable"}))
    with pytest.raises(ValueError, match="404"):
        parse_page(_json.dumps({"code": 404, "message": "Blocked by WAF"}))
