"""Sweeping a REGISTERED category, where GeM filtered rather than us (migration 0036).

The measurement these pin, taken on the live portal 2026-08-25 over the same window and the
same two-portal-requests-per-row cost:

    fullText  q='wire rope'       44,640 matching · 10 fetched · 0 kept
    exact     q='Steel Wire Rope'      6 matching ·  6 fetched · 6 kept, all with ladders

So the on-topic check has two jobs depending on who did the filtering, and the wrong one in
either place is a silent data fault rather than an error.
"""

from __future__ import annotations

import pytest

from app.discovery.ingest import _is_on_topic

#: Verbatim from the live corpus after a fullText fetch for "wire rope".
LIVE_NOISE = "Assembled PC,Print Machine,HDMI CABLWire,Digimore Mic Set,Power Cable"


# ---------- fullText: the portal ORed the words, so the phrase rule decides ----------

def test_full_text_still_discards_what_the_portal_ored_in():
    assert not _is_on_topic("wire rope", LIVE_NOISE, "fullText")


def test_full_text_keeps_a_real_match_on_the_phrase_rule():
    assert _is_on_topic("wire rope", "Wire Rope For Wire Rope Barrier", "fullText")


# ---------- exact: the portal matched the whole field, so equality decides ----------

def test_exact_keeps_the_category_it_asked_for():
    assert _is_on_topic("Steel Wire Rope", "Steel Wire Rope", "exact")


def test_exact_ignores_case_on_what_came_back():
    """Only the OUTBOUND query is case-sensitive. What GeM returns is whatever GeM stored, and
    re-deciding its case here would discard a row the portal itself matched."""
    assert _is_on_topic("Steel Wire Rope", "STEEL WIRE ROPE", "exact")


def test_exact_tolerates_the_portals_inconsistent_spacing():
    """A double space occurs in the live corpus. It is not meaningful and must not be."""
    assert _is_on_topic("Steel Wire Rope", "Steel  Wire   Rope", "exact")


def test_exact_rejects_a_neighbour_rather_than_trusting_the_portal():
    """`exact` should make this check a no-op. It stays because "should" is doing work in that
    sentence: if the portal's behaviour ever changes, the corpus is protected and the count
    surfaces it, rather than a wider category quietly being stored as a narrower one."""
    assert not _is_on_topic("Steel Wire Rope", "Steel Wire Rope Sling", "exact")
    assert not _is_on_topic("Steel Wire Rope", "Galvanized Steel Wire Rope", "exact")


def test_a_comma_in_a_registered_name_matches_ITSELF():
    """The regression this function exists for.

    `category_matches` treats a comma as an uncrossable barrier, because under fullText a
    comma joins two unrelated products and "Insulated copper wire,Rope ladder" must not read
    as the phrase "wire rope". Applied to an EXACT match that rule discards a row for failing
    to match its own name — GeM writes multi-item categories that way and a seller can be
    registered under one, so this is a real row, not a hypothetical.
    """
    bundle = "Brinjal,Capsicum,Carrot,Cauliflower"
    assert _is_on_topic(bundle, bundle, "exact")

    from app.deterministic.price_history import category_matches
    assert not category_matches(bundle, bundle)  # why the exact branch cannot reuse it


@pytest.mark.parametrize("missing", [None, ""])
def test_a_record_with_no_category_is_never_on_topic_under_exact(missing):
    assert not _is_on_topic("Steel Wire Rope", missing, "exact")
