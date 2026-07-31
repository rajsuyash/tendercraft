"""TED normaliser tests — the language selection and the F-FR1 contract.

The fixture is a REAL notice shape captured from api.ted.europa.eu on 2026-07-31, trimmed. Unlike
the GeM connector's fixtures this one IS committed: TED is EU open data with no reproduction
clause, so nothing here is a licence problem.
"""

from __future__ import annotations

import pytest

from app.listing import (
    build_body,
    market_to_country,
    normalize,
    normalize_ref,
    parse_page,
    pick_language,
)

NOTICE = {
    "publication-number": "530016-2026",
    "notice-title": {
        "fra": "France – Travaux de construction – Travaux de résidentialisation",
        "eng": "France – Building construction work – Residentialisation works",
        "hun": "Franciaország – Épületépítési munkák",
    },
    "buyer-name": {"fra": ["BATIGERE HABITAT, Ile de France"]},
    "buyer-country": ["FRA"],
    "deadline-receipt-request": ["2026-09-04T12:00:00+02:00"],
    "publication-date": "2026-07-31+02:00",
    "classification-cpv": ["45210000", "44316500", "45210000"],
    "place-of-performance": ["FR107", "FRA"],
    "notice-type": "cn-standard",
    "procedure-type": "open",
    "links": {
        "html": {"FRA": "https://ted.europa.eu/fr/notice/-/detail/530016-2026",
                 "ENG": "https://ted.europa.eu/en/notice/-/detail/530016-2026"},
        "pdf": {"FRA": "https://ted.europa.eu/fr/notice/530016-2026/pdf"},
    },
}


class TestLanguageIsSelectedNeverTranslated:
    """The product's position is that a tender is a legal document shown verbatim. TED publishes
    the same notice in 24 languages, so serving French means CHOOSING the French one."""

    def test_the_market_language_wins(self):
        record = normalize(NOTICE, "FR")
        assert record["title"].startswith("France – Travaux")
        assert record["notice_language"] == "fr"

    def test_a_different_market_selects_its_own_language(self):
        text, lang = pick_language(NOTICE["notice-title"], "DE")
        # No German on this notice, so English is the readable fallback — not a dropped notice.
        assert lang == "en"
        assert text.startswith("France – Building")

    def test_a_notice_in_no_preferred_language_is_still_returned(self):
        # Hungarian only. Dropping it would be a discovery miss (ET-7); reading it imperfectly
        # is merely inconvenient.
        text, lang = pick_language({"hun": "Franciaország – Épületépítési munkák"}, "FR")
        assert text.startswith("Franciaország")
        assert lang == "hu"

    def test_the_recorded_language_is_what_was_actually_chosen(self):
        # This value decides what language the DRAFTER must write in, so it must describe the
        # text we stored, not the market we asked for.
        record = normalize({**NOTICE, "notice-title": {"eng": "English only notice"}}, "FR")
        assert record["title"] == "English only notice"
        assert record["notice_language"] == "en"

    @pytest.mark.parametrize("value", [None, "", [], {}])
    def test_missing_titles_do_not_raise(self, value):
        text, lang = pick_language(value, "FR")
        assert text is None and lang is None

    def test_a_plain_string_title_still_works(self):
        assert pick_language("Marché de services", "FR") == ("Marché de services", None)


class TestTheFFR1Contract:
    def test_core_fields(self):
        record = normalize(NOTICE, "FR")
        assert record["source_id"] == "ted"
        assert record["market"] == "FR"
        assert record["portal_ref_no"] == "530016/2026"
        assert record["authority"] == "BATIGERE HABITAT, Ile de France"
        assert record["closing_at"] == "2026-09-04T12:00:00+02:00"

    def test_cpv_is_deduped_and_keeps_the_main_code_first(self):
        # A prefix rule matches the list; the main classification must lead it.
        assert normalize(NOTICE, "FR")["category_codes"] == ["45210000", "44316500"]

    def test_geography_is_read_not_inferred(self):
        # GeM left this null because a state name guessed out of a department string is the
        # plausible inference ET-7 punishes. TED publishes NUTS codes, so it is a read.
        assert normalize(NOTICE, "FR")["geography"] == "FR107, FRA"

    def test_absent_money_stays_absent(self):
        record = normalize(NOTICE, "FR")
        assert record["estimated_value"] is None
        assert record["emd"] is None

    def test_the_document_link_is_in_the_market_language(self):
        assert normalize(NOTICE, "FR")["document_urls"] == [
            "https://ted.europa.eu/fr/notice/-/detail/530016-2026"
        ]

    def test_snapshot_ref_is_content_addressed(self):
        first = normalize(NOTICE, "FR")["raw_snapshot_ref"]
        assert first.startswith("sha256:")
        assert normalize({**NOTICE, "notice-type": "other"}, "FR")["raw_snapshot_ref"] != first

    def test_normalize_does_not_mutate_its_input(self):
        before = dict(NOTICE)
        normalize(NOTICE, "FR")
        assert NOTICE == before


class TestMergeKeyDiscipline:
    """F-AC4: two distinct tenders must never collapse into one."""

    def test_formatting_variants_collapse(self):
        assert normalize_ref("530016-2026") == normalize_ref(" 530016/2026 ") == "530016/2026"

    def test_adjacent_publication_numbers_stay_separate(self):
        assert normalize_ref("530016-2026") != normalize_ref("530017-2026")

    def test_no_fuzzy_matching(self):
        refs = {normalize_ref(r) for r in ("530016-2026", "530061-2026", "530016-2025")}
        assert len(refs) == 3


class TestQuery:
    def test_it_asks_only_for_open_notices(self):
        # TED's archive reaches the 1990s; without this the sweep spends its budget on tenders
        # that closed decades ago.
        body = build_body(1, 100, "FR")
        assert "deadline-receipt-request>=today()" in body["query"]

    def test_newest_first_so_the_incremental_frontier_is_page_one(self):
        assert "SORT BY publication-date DESC" in build_body(1, 100, "FR")["query"]

    def test_market_selects_the_buyer_country(self):
        assert "buyer-country=FRA" in build_body(1, 100, "FR")["query"]
        assert "buyer-country=DEU" in build_body(1, 100, "DE")["query"]
        assert market_to_country("ES") == "ESP"

    def test_a_search_term_widens_rather_than_narrows(self):
        # It adds a title clause to ACQUIRE more on a targeted sweep; it never removes anything
        # from what a workspace can see. Exclusion is the deterministic rule engine's job (G-9).
        body = build_body(1, 100, "FR", 'conseil "stratégie"')
        assert "notice-title~" in body["query"]
        assert body["query"].count('"') % 2 == 0, "unbalanced quotes would break the query"

    def test_parse_page_reads_the_ted_envelope(self):
        total, notices = parse_page('{"totalNoticeCount": 7047, "notices": [{"a": 1}]}')
        assert total == 7047 and len(notices) == 1

    def test_parse_page_raises_on_an_unexpected_shape(self):
        with pytest.raises(ValueError, match="no notices"):
            parse_page('{"message": "Value not supported", "error": {}}')
