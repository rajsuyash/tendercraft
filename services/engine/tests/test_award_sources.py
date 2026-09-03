"""Award history from a second, differently-shaped source (UML ask 5).

Everything here guards one class of bug: a corpus built around one portal quietly turning
another portal's SILENCE into a claim. BidAssist publishes no MSE status, often no ladder
position, and a contract date rather than a bid-close date. Each of those is an absence, and
each has an obvious wrong default — false, "sort by price", "put it in the date column we
already have" — that produces a plausible screen stating something nobody published.
"""

from __future__ import annotations

import pytest

from app.deterministic.price_history import summarise, to_award
from app.discovery import ingest
from app.discovery.registry import Source


def _record(**over) -> dict:
    base = {
        "source_id": "bidassist",
        "award_ref": "AW-9001",
        "portal_ref_no": "IREPS.GOV.IN/77265283",
        "authority": "South Eastern Railway",
        "categories": ["Steel Wire Rope"],
        "contract_date": "2026-05-04T00:00:00Z",
        "participant_count": 3,
        "ladder": [
            {"seller": "USHA MARTIN", "mse": None, "total_price": 100.0,
             "rank": 1, "offered_item": None, "awarded": True},
        ],
    }
    return base | over


# ---------- the corpus key ----------

def test_the_key_qualifies_the_award_with_the_tender_it_belongs_to():
    """Neither half is unique alone. One tender can be awarded in several packages, so the
    tender ref would upsert them over each other; and an award number is issued per portal, so
    on an aggregated feed two portals will eventually collide on one."""
    assert ingest._award_ref(_record()) == "IREPS.GOV.IN/77265283#AW-9001"


@pytest.mark.parametrize("record,expected", [
    ({"portal_ref_no": "X/1", "award_ref": ""}, "X/1"),
    ({"portal_ref_no": "", "award_ref": "AW-2"}, "AW-2"),
    ({"portal_ref_no": "", "award_ref": ""}, None),
])
def test_a_missing_half_degrades_rather_than_producing_a_half_key(record, expected):
    assert ingest._award_ref(record) == expected


def test_a_record_with_no_reference_at_all_is_skipped_not_stored_under_a_made_up_id():
    """A row with no stable key re-inserts itself on every sweep — an unbounded corpus."""
    assert ingest._award_row({"portal_ref_no": "", "award_ref": ""}, "bidassist") is None


# ---------- what a record becomes ----------

def test_the_award_date_goes_in_its_own_column_not_the_bid_close_one():
    """A contract award and a bid closing are weeks apart and are not the same event. Writing
    one into the other's column makes a five-year window compare two different milestones."""
    row = ingest._award_row(_record(), "bidassist")

    assert row["award_date"] == "2026-05-04T00:00:00Z"
    assert row["bid_end_date"] is None


def test_quantity_is_never_written_because_this_source_does_not_publish_it():
    """The implied unit rate divides by quantity. A guessed one produces a per-unit benchmark
    someone prices a real bid against — the number price_history exists to refuse."""
    assert "quantity" not in ingest._award_row(_record(), "bidassist")


def test_several_categories_are_joined_with_commas_so_the_bundle_rule_still_fires():
    """`is_single_category` reads a comma as "unrelated products". A two-category award IS a
    bundle and must suppress the unit rate exactly as GeM's comma-joined string does."""
    row = ingest._award_row(_record(categories=["Steel Wire Rope", "Wire Rope Sling"]),
                            "bidassist")
    award = to_award(row | {"quantity": 10, "participants": 1}, [])

    assert row["category"] == "Steel Wire Rope, Wire Rope Sling"
    assert award.is_single_category is False


# ---------- what a ladder becomes ----------

def test_an_unpublished_mse_status_stays_unknown_rather_than_becoming_a_denial():
    """False would state that a named real company is not a small enterprise. Nobody said so."""
    rows = ingest._award_ladder(_record())
    assert rows[0]["mse"] is None


def test_a_bidder_with_no_published_price_is_dropped_not_stored_at_zero():
    rows = ingest._award_ladder(_record(ladder=[
        {"seller": "A", "total_price": 100.0, "rank": 1, "awarded": True},
        {"seller": "B", "total_price": None, "rank": 2, "awarded": False},
    ]))
    assert [r["seller"] for r in rows] == ["A"]


def test_an_absent_rank_survives_as_absent():
    """Measured on 100 BidAssist awards: only 51 of the 55 multi-bidder ones carry a rank."""
    rows = ingest._award_ladder(_record(ladder=[
        {"seller": "A", "total_price": 100.0, "rank": None, "awarded": True},
    ]))
    assert rows[0]["rank"] is None
    assert rows[0]["awarded"] is True


# ---------- flattening a ladder that has no ranks ----------

def test_without_ranks_the_flagged_winner_wins_and_there_is_no_runner_up():
    """Sorting the rest by price and calling the cheapest L2 would invent a ladder position the
    portal never published — and `undercut_pct` would then be a fabricated competitive spread."""
    a = to_award(
        {"portal_ref_no": "IREPS.GOV.IN/1#AW-1", "source_id": "bidassist", "participants": 3},
        [{"seller": "B", "total_price": "120", "rank": None, "mse": None, "awarded": False},
         {"seller": "A", "total_price": "100", "rank": None, "mse": None, "awarded": True},
         {"seller": "C", "total_price": "90", "rank": None, "mse": None, "awarded": False}],
    )

    assert (a.winner, a.winning_price) == ("A", 100.0)
    assert a.runner_up_price is None
    assert a.undercut_pct is None


def test_a_published_rank_still_beats_the_awarded_flag():
    """Where the source published a ladder, the ladder is the answer — the flag is the fallback
    for feeds that publish only who won."""
    a = to_award(
        {"portal_ref_no": "GEM/2026/B/9", "source_id": "gem_bidplus", "participants": 2},
        [{"seller": "A", "total_price": "100", "rank": 1, "mse": True, "awarded": False},
         {"seller": "B", "total_price": "120", "rank": 2, "mse": False, "awarded": False}],
    )
    assert (a.winner, a.runner_up_price) == ("A", 120.0)


def test_an_unknown_mse_reaches_the_screen_as_unknown_not_as_false():
    a = to_award({"portal_ref_no": "X", "source_id": "bidassist", "participants": 1},
                 [{"seller": "A", "total_price": "100", "rank": 1, "mse": None,
                   "awarded": True}])
    assert a.winner_is_mse is None
    assert a.as_dict()["winner_is_mse"] is None


def test_the_generated_date_is_preferred_over_either_source_column():
    a = to_award({"portal_ref_no": "X", "source_id": "bidassist", "participants": 0,
                  "observed_date": "2026-05-04T00:00:00Z", "bid_end_date": None}, [])
    assert a.award_date == "2026-05-04T00:00:00Z"


# ---------- the summary, once two feeds are mixed ----------

def test_the_summary_separates_mse_unknown_from_mse_did_not_win():
    """"2 of 20" would read as eighteen wins by large firms when most are simply unpublished."""
    a = to_award({"portal_ref_no": "1", "source_id": "gem_bidplus", "participants": 1},
                 [{"seller": "A", "total_price": "100", "rank": 1, "mse": True}])
    b = to_award({"portal_ref_no": "2", "source_id": "bidassist", "participants": 1},
                 [{"seller": "B", "total_price": "200", "rank": 1, "mse": None}])
    s = summarise([a, b])

    assert s["mse_wins"] == 1
    assert s["mse_unknown"] == 1


def test_the_summary_names_which_feeds_it_blended():
    """A median across portals is only defensible if the screen can say what it averaged."""
    a = to_award({"portal_ref_no": "1", "source_id": "gem_bidplus", "participants": 0}, [])
    b = to_award({"portal_ref_no": "2", "source_id": "bidassist", "participants": 0}, [])
    assert summarise([a, b, b])["by_source"] == {"gem_bidplus": 1, "bidassist": 2}


# ---------- the sweep ----------

def test_an_unconfigured_feed_reports_itself_instead_of_raising(monkeypatch):
    """This runs from the scheduler beside other jobs. One unset variable must not take the
    rest of the sweep down — and `configured: false` is the visible form of an absence that
    GEM_CONNECTOR_URL already taught us reads as "the market is quiet"."""
    monkeypatch.setattr(ingest, "for_market", lambda market: ())

    report = ingest.refresh_licensed_awards()

    assert report["configured"] is False
    assert report["stored"] == 0


def test_a_source_cleared_to_READ_is_not_thereby_cleared_to_SHOW(monkeypatch):
    """The two permissions come apart on a licensed feed, and the registry's live BidAssist row
    is the case: G-8 acquisition was ratified, the partner agreement governing onward display to
    a non-licensee has not been read. The gate sits at ingest rather than at the screen, because
    a corpus holding the rows is one query away from displaying them."""
    monkeypatch.setattr(ingest, "for_market", lambda market: (
        Source(source_id="bidassist", market="IN", connector_url="http://c.test",
               tier="T1-licensed", terms_reviewed="2026-08-29", reviewer="owner",
               display_reviewed=""),
    ))
    monkeypatch.setattr(ingest, "_connector", _never_called)

    report = ingest.refresh_licensed_awards()

    assert (report["configured"], report["cleared"]) == (True, False)
    assert report["stored"] == 0
    assert "display" in report["reason"]


def test_the_live_registry_still_has_that_gate_shut():
    """Pinned so enabling the feed is a deliberate edit with a contract behind it, not the
    side effect of someone touching this file for another reason."""
    from app.discovery.registry import REGISTRY

    bidassist = next(s for s in REGISTRY if s.source_id == "bidassist")
    assert bidassist.display_reviewed == ""


def _never_called(*args, **kwargs):
    raise AssertionError("the connector must not be reached before the gate is checked")


def test_the_sweep_stores_every_record_because_a_feed_has_no_query_to_be_loose_about(
    monkeypatch,
):
    """`refresh_awards` discards off-topic rows because GeM's search ORs the query's words.
    There is no query here, so discarding anything would be an exclusion no user authored
    (G-9); the category search happens at read time on the stored corpus."""
    monkeypatch.setattr(ingest, "for_market", lambda market: (
        Source(source_id="bidassist", market="IN", connector_url="http://c.test",
               tier="T1-licensed", terms_reviewed="2026-08-29", reviewer="owner",
               display_reviewed="2026-09-03"),
    ))
    monkeypatch.setattr(ingest, "_connector", lambda *a, **k: {
        "count": 2, "feed_source_id": "feed-1", "complete": True,
        "records": [_record(), _record(award_ref="AW-9002",
                                       categories=["Hydraulic Hose"])],
    })
    written: list[tuple[str, list]] = []
    monkeypatch.setattr(ingest.db, "upsert_award_result", lambda row: row["portal_ref_no"])
    monkeypatch.setattr(ingest.db, "replace_award_prices",
                        lambda rid, ladder: written.append((rid, ladder)))

    report = ingest.refresh_licensed_awards()

    assert report["stored"] == 2
    assert report["feed_source_id"] == "feed-1"
    assert len(written) == 2
