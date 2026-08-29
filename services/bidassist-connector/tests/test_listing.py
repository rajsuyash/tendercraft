"""BidAssist normaliser tests — the F-FR1 contract, and the four ways this source can lie.

**The fixtures here are synthetic, and that is deliberate.** The TED connector commits real
captured notices because TED is EU open data with no reproduction clause. BidAssist is a paid
commercial feed whose reproduction terms we have not reviewed, so these fixtures reproduce the
*shape* measured on 2026-08-29 — field names, types, epoch-millisecond timestamps, the signed
CloudFront querystring — with invented content. Same discipline as the GeM connector, whose
fixtures are also kept out of the repo.

Every constant asserted below was measured against the live API, not assumed:
page size 20, epoch-ms timestamps, `data`/`last` envelope, HTTP 200 on refusal, and an award
ladder that really does carry more than one bidder.
"""

from __future__ import annotations

import pytest

from app.listing import (
    PAGE_SIZE,
    build_body,
    iso_from_millis,
    money,
    normalize,
    normalize_award,
    normalize_ref,
    parse_page,
    qualified_ref,
)

SIGNED = (
    "https://d3dhalnpawfxbg.cloudfront.net/tendersDataFiles%2Fireps.gov.in%2FNIT.pdf"
    "?Expires=1788603059&Signature=AAAA~BBBB__&Key-Pair-Id=K1VKVH9VMD9S2C"
)
SIGNED_ROTATED = (
    "https://d3dhalnpawfxbg.cloudfront.net/tendersDataFiles%2Fireps.gov.in%2FNIT.pdf"
    "?Expires=1799999999&Signature=ZZZZ~YYYY__&Key-Pair-Id=K1VKVH9VMD9S2C"
)

TENDER = {
    "tenderId": "b530d8a4-a523-4d79-8008-1a1d4f8b3d06",
    "sourceTenderId": "01261188-STORES/TKJ/RCF",
    "tenderNoticeNo": "01261188",
    "sourceUrl": "ireps.gov.in",
    "source": "OFB",
    "tenderDescription": "Safety Wire Rope Assly",
    "tenderDetails": "Safety Wire Rope Assly",
    "authority": {"name": "Rail Coach Factory"},
    "location": {"city": "Kapurthala", "state": "Punjab", "country": "India"},
    "sector": ["Electrical Cables And Wires", "Metals and Non-Metals"],
    "value": "277452.22",
    "isTenderValueEstimated": False,
    "emd": None,
    "currency": "INR",
    "postingDate": 1784034300000,
    "bidDeadline": 1785909600000,
    "preBidMeetingDate": None,
    "boqItemsCount": 1,
    "corrigendumInfo": [{"publishedDate": 1785750480000, "title": "Corrigendum 2"}],
    "documents": [{"name": "NIT.pdf", "documentKey": SIGNED, "type": "NOTICE"}],
    "workflowStatus": "PUBLISHED",
}


class TestTheReferenceCannotMergeTwoTenders:
    """F-AC4 is zero-tolerance: two distinct tenders shown as one deletes a tender from the
    user's world with no error message anywhere. On an aggregated feed the realistic way that
    happens is a notice number that is unique on its own portal and duplicated across ten."""

    def test_reference_is_qualified_by_the_portal_that_issued_it(self) -> None:
        assert qualified_ref(TENDER) == "IREPS.GOV.IN/01261188/STORES/TKJ/RCF"

    def test_same_notice_number_on_two_portals_stays_two_references(self) -> None:
        railways = qualified_ref({**TENDER, "sourceUrl": "ireps.gov.in"})
        telangana = qualified_ref({**TENDER, "sourceUrl": "tender.telangana.gov.in"})
        assert railways != telangana

    def test_a_row_with_no_portal_reference_still_gets_a_stable_key(self) -> None:
        # Not merely defensive: a row with no key re-inserts on every sweep, and an unbounded
        # corpus is a worse failure than an unmergeable row.
        bare = {k: v for k, v in TENDER.items() if k not in ("sourceTenderId", "tenderNoticeNo")}
        assert qualified_ref(bare) == "BIDASSIST/B530D8A4-A523-4D79-8008-1A1D4F8B3D06"

    def test_reference_normalisation_is_separators_and_case_only(self) -> None:
        assert normalize_ref(" gem/2026/b/7876746 ") == "GEM/2026/B/7876746"
        assert normalize_ref("GEM-2026-B-7876746") == "GEM/2026/B/7876746"
        assert normalize_ref("   ") is None


class TestAVendorEstimateNeverReachesARule:
    """`estimated_value` is read by value-band rules. A number the vendor inferred, sitting in
    that field, becomes an exclusion nobody authored — the same reason TED leaves it null."""

    def test_a_real_value_is_published(self) -> None:
        assert normalize(TENDER)["estimated_value"] == pytest.approx(277452.22)

    def test_an_inferred_value_is_withheld_but_not_hidden(self) -> None:
        record = normalize({**TENDER, "isTenderValueEstimated": True})
        assert record["estimated_value"] is None
        assert record["source_fields"]["value_is_vendor_estimate"] is True
        assert record["source_fields"]["vendor_estimated_value"] == pytest.approx(277452.22)

    def test_absent_money_stays_absent_rather_than_zero(self) -> None:
        record = normalize({**TENDER, "value": None, "emd": ""})
        assert record["estimated_value"] is None
        assert record["emd"] is None
        assert money("0") is None


class TestTheSnapshotHashTracksTheTenderNotTheSignature:
    """CloudFront regenerates `Signature` and `Expires` on every fetch. Hashing them would make
    `raw_snapshot_ref` change on every sweep for an unchanged tender — a change signal that
    always fires reports nothing."""

    def test_rotating_the_signature_does_not_change_the_snapshot(self) -> None:
        first = normalize(TENDER)["raw_snapshot_ref"]
        rotated = normalize({
            **TENDER,
            "documents": [{"name": "NIT.pdf", "documentKey": SIGNED_ROTATED, "type": "NOTICE"}],
        })["raw_snapshot_ref"]
        assert first == rotated

    def test_changing_the_deadline_does_change_the_snapshot(self) -> None:
        moved = normalize({**TENDER, "bidDeadline": 1785909600000 + 86_400_000})
        assert moved["raw_snapshot_ref"] != normalize(TENDER)["raw_snapshot_ref"]

    def test_the_live_signed_url_is_still_what_gets_emitted(self) -> None:
        record = normalize(TENDER)
        assert record["document_urls"] == [SIGNED]
        # The expiry is recorded so a dead link can be explained rather than just 403 at a user.
        assert record["source_fields"]["documents_expire_at"] == "2026-09-05T10:10:59+00:00"


class TestTheFFR1Shape:
    def test_timestamps_become_utc_iso(self) -> None:
        record = normalize(TENDER)
        assert record["published_at"] == "2026-07-14T13:05:00+00:00"
        assert record["closing_at"] == "2026-08-05T06:00:00+00:00"
        assert record["prebid_at"] is None
        assert iso_from_millis(0) is None and iso_from_millis(None) is None

    def test_the_overlap_with_our_own_gem_sweep_is_labelled_not_dropped(self) -> None:
        # ~43% of the sampled feed was GeM, which `gem_bidplus` already sweeps. The duplicate
        # is deliberate: visible and annoying beats invisible and destructive.
        gem = normalize({**TENDER, "sourceUrl": "bidplus.gem.gov.in"})
        assert gem["source_fields"]["overlaps_source"] == "gem_bidplus"
        assert normalize(TENDER)["source_fields"]["overlaps_source"] is None

    def test_core_fields(self) -> None:
        record = normalize(TENDER)
        assert record["source_id"] == "bidassist"
        assert record["market"] == "IN"
        assert record["notice_language"] == "en"
        assert record["title"] == "Safety Wire Rope Assly"
        assert record["authority"] == "Rail Coach Factory"
        assert record["geography"] == "Kapurthala, Punjab"
        assert record["category_codes"] == ["Electrical Cables And Wires", "Metals and Non-Metals"]
        assert record["source_fields"]["portal_host"] == "ireps.gov.in"
        assert record["source_fields"]["corrigendum_count"] == 1


AWARD = {
    "bidAwardId": "b029296e-a54f-4138-a2aa-f9840fcf2f38",
    "sourceBidAwardId": "WR/15262037102827",
    "tenderId": "9f264981-c724-446a-b4bf-62415c346bdb",
    "sourceTenderId": "15262037102827-WR",
    "sourceUrl": "ireps.gov.in",
    "aocDescription": "SAFETY WIRE ROPE ASSLY FOR FIAT IR BOGIE",
    "authority": {"name": "Western Railway"},
    "location": {"city": "Mumbai", "state": "Maharashtra"},
    "category": ["Metals and Non-Metals"],
    "contractValue": "636633.60",
    "isContractValueEstimated": False,
    "contractDate": 1779215400000,
    "contractPeriod": "92",
    "documents": [],
    "bidderDetails": [
        {"bidderName": "M/s. SECOND PLACE LTD", "bidValue": "700000.00",
         "bidRank": 2, "isAwarded": False, "offeredMake": "-"},
        {"bidderName": "M/s. HEFTECH EQUIPMENTS COMPANY", "awardedValue": "636633.6",
         "bidValue": "636633.6", "bidRank": 1, "isAwarded": True, "offeredMake": "-"},
        {"bidderName": "M/s. UNRANKED BIDDER", "bidValue": "812000.00",
         "bidRank": None, "isAwarded": False},
    ],
}


class TestTheAwardLadder:
    """The ladder is real on this source — measured over 100 awards: 55 with more than one
    bidder, 51 of those carrying an explicit rank, 44 with more than one priced bidder."""

    def test_the_ladder_is_ordered_by_the_rank_the_source_published(self) -> None:
        ladder = normalize_award(AWARD)["ladder"]
        assert [r["rank"] for r in ladder] == [1, 2, None]
        assert ladder[0]["seller"] == "M/s. HEFTECH EQUIPMENTS COMPANY"

    def test_an_unranked_bidder_is_kept_and_never_given_an_invented_rank(self) -> None:
        # Sorting by price and calling the position a rank would manufacture a ladder rung the
        # portal never published.
        assert normalize_award(AWARD)["ladder"][-1]["rank"] is None

    def test_mse_is_unknown_and_never_false(self) -> None:
        # BidAssist publishes no MSE status. Rendering unknown as False states that a real
        # company is not a small enterprise — a claim nobody made.
        assert all(r["mse"] is None for r in normalize_award(AWARD)["ladder"])

    def test_the_winner_is_the_awarded_bidder_not_merely_the_first_row(self) -> None:
        result = normalize_award(AWARD)
        assert result["winner"]["seller"] == "M/s. HEFTECH EQUIPMENTS COMPANY"
        assert result["winner"]["awarded"] is True
        assert result["participant_count"] == 3
        assert result["contract_value"] == pytest.approx(636633.60)

    def test_an_award_with_no_bidders_does_not_invent_a_winner(self) -> None:
        empty = normalize_award({**AWARD, "bidderDetails": []})
        assert empty["ladder"] == [] and empty["winner"] is None


class TestOnlyTheAllowlistedFilterIsEverSent:
    """Probed 2026-08-29: `SEARCH`, `STATE` and an invented key were refused, but `KEYWORD` was
    ACCEPTED and returned a page identical to the unfiltered control. A filter the server
    silently ignores is worse than one it rejects, because the response looks like an answer —
    the same trap GeM's `bidStatusType` set. This test is what stops the next key being added
    without being measured first."""

    def test_the_body_carries_exactly_one_filter_key(self) -> None:
        body = build_body("6a9042ff8f88b942e5ca51d5", 0)
        assert list(body["filters"]) == ["FEED_SOURCE_ID"]
        assert body["filters"]["FEED_SOURCE_ID"] == ["6a9042ff8f88b942e5ca51d5"]

    def test_page_size_is_the_vendor_cap_not_a_preference(self) -> None:
        # 20 works; 25, 30, 50 and 100 all return `invalid page size or page number`.
        assert PAGE_SIZE == 20
        assert build_body("feed", 3) == {
            "filters": {"FEED_SOURCE_ID": ["feed"]}, "pageNumber": 3, "pageSize": 20,
        }


class TestThePageEnvelope:
    def test_last_flag_terminates_the_sweep(self) -> None:
        assert parse_page({"data": [TENDER], "last": False}) == ([TENDER], False)
        assert parse_page({"data": [], "last": True}) == ([], True)

    def test_a_refusal_body_is_not_mistaken_for_an_empty_page(self) -> None:
        # The vendor answers HTTP 200 with data:null on a rejected request. An empty page and a
        # refused one must never look the same to a caller.
        with pytest.raises(ValueError):
            parse_page({"data": None, "success": False, "errorCode": "EIPS400"})
