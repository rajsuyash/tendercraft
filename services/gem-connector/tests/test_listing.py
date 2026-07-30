"""Phase 1 tests — the field mapping and the guardrails.

Fixtures are two REAL documents captured from https://bidplus.gem.gov.in/all-bids-data on
2026-07-30, trimmed but not edited. A synthetic fixture here would be worthless: the whole risk
in this file is GeM's actual field shapes (everything list-wrapped, "NA" placeholders, the
parent-vs-item id trap), and a hand-written fixture would encode my assumptions rather than
the portal's behaviour.
"""

from __future__ import annotations

import httpx
import pytest

from app.fetch import (
    ALLOWED_HOSTS,
    BotChallengeDetected,
    FetchRefused,
    GuardedFetcher,
    assert_no_bot_challenge,
)
from app.listing import (
    build_payload,
    extract_csrf_token,
    normalize,
    normalize_ref,
    parse_page,
)

# A services bid with a ministry AND a department.
DOC_SERVICES = {
    "id": "9664201",
    "b_id": [9664201],
    "b_bid_number": ["GEM/2026/R/705308"],
    "b_category_name": ["Custom Bid for Services - SPRING ASSY"],
    "bd_category_name": ["Custom Bid for Services - SPRING ASSY"],
    "b_total_quantity": [1],
    "b_type": [1],
    "b_eval_type": [0],
    "final_start_date_sort": ["2026-07-28T10:00:00Z"],
    "final_end_date_sort": ["2026-07-30T15:43:46Z"],
    "b_bid_number_parent": ["GEM/2026/B/7741502"],
    "b_id_parent": [9555122],
    "is_high_value": [False],
    "b_cat_id": ["services_home_cust"],
    "ba_is_global_tendering": [0],
    "is_rc_bid": [0],
    "ba_official_details_minName": ["Ministry of Defence"],
    "ba_official_details_deptName": ["Department of Defence Production"],
}

# A goods bid whose department is GeM's literal "NA" placeholder, with a multi-code category
# and a truncated b_category_name — all three are real quirks this fixture exists to pin.
DOC_GOODS_NA_DEPT = {
    "id": "9672346",
    "b_bid_number": ["GEM/2026/R/706522"],
    "b_category_name": ["Brinjal,Capsicum,Carrot,Cauliflower,Palak,Fresh peas,Tori,Tinda,Turnip,Raddish,Ghia,Petha,Bittergou"],
    "bd_category_name": ["Brinjal,Capsicum,Carrot,Cauliflower,Palak,Fresh peas,Tori,Tinda,Turnip,Raddish,Ghia,Petha,Bittergourd,Tofu,Green chilies"],
    "b_total_quantity": [225050],
    "final_start_date_sort": ["2026-07-29T15:00:00Z"],
    "final_end_date_sort": ["2026-07-30T15:42:58Z"],
    "b_id_parent": [9455743],
    "b_cat_id": ["home_clea_clea_clea_to48326355,home_clea_clea_broo_to05687514, home_tool_hand_brus_scru"],
    "is_high_value": [True],
    "ba_official_details_minName": ["Ministry of Labour and Employment"],
    "ba_official_details_deptName": ["NA"],
    "bd_details_is_boq": [True],
}


class TestNormalizeRef:
    """F-FR6/F-AC4: exact-match merging only. These are the tests that stop a wrong merge."""

    def test_collapses_case_whitespace_and_separators(self):
        assert normalize_ref("  gem/2026/r/705308 ") == "GEM/2026/R/705308"
        assert normalize_ref("GEM-2026-R-705308") == "GEM/2026/R/705308"
        assert normalize_ref("GEM_2026_R_705308") == "GEM/2026/R/705308"

    def test_is_idempotent(self):
        once = normalize_ref("gem-2026-r-705308")
        assert normalize_ref(once) == once

    def test_distinct_bids_never_collapse_to_one_ref(self):
        # The catastrophic case: two different tenders becoming one opportunity (ET-8).
        a = normalize_ref("GEM/2026/R/705308")
        b = normalize_ref("GEM/2026/R/705309")
        assert a != b

    def test_no_fuzzy_matching(self):
        # A single transposed digit must NOT merge. If someone ever adds edit-distance
        # matching to normalize_ref, this fails.
        assert normalize_ref("GEM/2026/R/705308") != normalize_ref("GEM/2026/R/705380")

    def test_none_and_empty(self):
        assert normalize_ref(None) is None
        assert normalize_ref("   ") is None


class TestNormalizeNeverInfers:
    """F-FR1's hard rule, and the reason ET-7 exists. These three assertions are the point of
    the whole module: a guessed value here becomes a silent wrong exclusion downstream."""

    @pytest.mark.parametrize("doc", [DOC_SERVICES, DOC_GOODS_NA_DEPT])
    def test_value_and_emd_are_null_because_the_listing_lacks_them(self, doc):
        record = normalize(doc)
        assert record["estimated_value"] is None
        assert record["emd"] is None

    def test_geography_is_null_even_when_the_department_names_a_state(self):
        doc = dict(DOC_SERVICES)
        doc["ba_official_details_deptName"] = ["Higher Education Department Jammu and Kashmir"]
        assert normalize(doc)["geography"] is None

    def test_prebid_is_null(self):
        assert normalize(DOC_SERVICES)["prebid_at"] is None


class TestNormalize:
    def test_maps_the_core_fields(self):
        record = normalize(DOC_SERVICES)
        assert record["source_id"] == "gem_bidplus"
        assert record["portal_ref_no"] == "GEM/2026/R/705308"
        assert record["authority"] == "Ministry of Defence · Department of Defence Production"
        assert record["category_codes"] == ["services_home_cust"]
        assert record["published_at"] == "2026-07-28T10:00:00Z"
        assert record["closing_at"] == "2026-07-30T15:43:46Z"

    def test_document_url_uses_the_PARENT_id_not_the_item_id(self):
        # The trap: /showbidDocument/<item_id> returns a 200 for the wrong bid rather than an
        # error, so this is unobservable in production without an assertion.
        record = normalize(DOC_SERVICES)
        assert record["document_urls"] == ["https://bidplus.gem.gov.in/showbidDocument/9555122"]
        assert "9664201" not in record["document_urls"][0]

    def test_drops_gems_NA_department_placeholder(self):
        record = normalize(DOC_GOODS_NA_DEPT)
        assert record["authority"] == "Ministry of Labour and Employment"
        assert "NA" not in record["authority"]

    def test_prefers_the_complete_category_name(self):
        # b_category_name is truncated mid-word ("Bittergou"); bd_category_name is complete.
        record = normalize(DOC_GOODS_NA_DEPT)
        assert record["title"].endswith("Green chilies")

    def test_splits_and_trims_category_codes(self):
        record = normalize(DOC_GOODS_NA_DEPT)
        assert len(record["category_codes"]) == 3
        assert record["category_codes"][2] == "home_tool_hand_brus_scru"  # leading space trimmed

    def test_missing_parent_id_yields_no_document_url_rather_than_a_broken_one(self):
        doc = {k: v for k, v in DOC_SERVICES.items() if k != "b_id_parent"}
        assert normalize(doc)["document_urls"] == []

    def test_snapshot_ref_is_stable_and_content_addressed(self):
        first = normalize(DOC_SERVICES)["raw_snapshot_ref"]
        assert first.startswith("sha256:")
        assert first == normalize(dict(DOC_SERVICES))["raw_snapshot_ref"]
        mutated = dict(DOC_SERVICES) | {"b_total_quantity": [2]}
        assert normalize(mutated)["raw_snapshot_ref"] != first

    def test_does_not_mutate_its_input(self):
        before = dict(DOC_SERVICES)
        normalize(DOC_SERVICES)
        assert DOC_SERVICES == before


class TestPayloadAndParsing:
    def test_payload_carries_page_and_ongoing_filter(self):
        body = build_payload(7)
        assert '"page":7' in body["payload"]
        assert '"bidStatusType":"ongoing_bids"' in body["payload"]

    def test_parse_page_reads_solr_shape(self):
        raw = '{"status":1,"code":200,"message":"Bid result","response":{"response":{"numFound":48476,"start":0,"docs":[{"b_bid_number":["GEM/2026/R/1"]}]}}}'
        total, docs = parse_page(raw)
        assert total == 48476
        assert len(docs) == 1

    def test_parse_page_raises_on_a_non_200_body(self):
        with pytest.raises(ValueError, match="code 403"):
            parse_page('{"code":403,"message":"Forbidden","response":{"response":{}}}')

    def test_extract_csrf_token(self):
        html = "<script>data: {'payload': x, 'csrf_bd_gem_nk': 'b469ee32e1fddfd5e5b215737d698044'}</script>"
        assert extract_csrf_token(html) == "b469ee32e1fddfd5e5b215737d698044"

    def test_missing_csrf_token_fails_loudly(self):
        # Otherwise every POST 403s and it looks like the portal blocked us (EC-8).
        with pytest.raises(ValueError, match="page structure changed"):
            extract_csrf_token("<html>no token here</html>")


class TestCappedRead:
    """Regression: the byte cap must not corrupt a compressed response.

    GeM gzips /all-bids. `iter_bytes()` yields DECODED bytes, so rebuilding the response with
    the original `content-encoding: gzip` header made httpx gunzip an already-gunzipped body
    and raise DecodingError. It presented as "the portal is failing", which is the worst kind
    of bug — it points away from itself. Caught by the first live sweep, not by a unit test,
    which is why this one exists.
    """

    def _fetcher_returning(self, body: bytes, headers: dict[str, str]) -> GuardedFetcher:
        import gzip

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /resources/\n")
            return httpx.Response(200, headers=headers, content=gzip.compress(body))

        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            headers={"User-Agent": "test"},
        )
        return GuardedFetcher(client=client)

    def test_gzipped_response_decodes_to_text(self):
        payload = b'{"code":200,"response":{"response":{"numFound":1,"docs":[]}}}'
        fetcher = self._fetcher_returning(
            payload, {"content-encoding": "gzip", "content-type": "text/html; charset=UTF-8"}
        )
        try:
            response = fetcher.get("/all-bids-data")
            assert response.text == payload.decode()
            total, docs = parse_page(response.text)
            assert total == 1 and docs == []
        finally:
            fetcher.close()

    def test_transfer_encoding_headers_are_stripped_from_the_rebuilt_response(self):
        fetcher = self._fetcher_returning(b"hello", {"content-encoding": "gzip"})
        try:
            response = fetcher.get("/all-bids")
            assert "content-encoding" not in response.headers
            assert response.text == "hello"
        finally:
            fetcher.close()


class TestGuardrails:
    def test_allowlist_is_exactly_the_one_host(self):
        assert ALLOWED_HOSTS == frozenset({"bidplus.gem.gov.in"})

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.com/all-bids",
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "https://bidplus.gem.gov.in.evil.example.com/x",  # suffix trick
        ],
    )
    def test_off_allowlist_hosts_are_refused(self, url):
        fetcher = GuardedFetcher()
        try:
            with pytest.raises(FetchRefused, match="allowlist"):
                fetcher.get(url)
        finally:
            fetcher.close()

    @pytest.mark.parametrize(
        "body",
        [
            "<html>Please enable JavaScript and cookies to continue</html>",
            "<div class='g-recaptcha'></div>",
            "<script src='/cdn-cgi/challenge-platform/jschl.js'></script>",
            "<html>Incapsula incident ID</html>",
        ],
    )
    def test_a_bot_challenge_halts_the_run(self, body):
        # G-8: the correct response to being challenged is to stop, not to get better at
        # looking like a browser.
        with pytest.raises(BotChallengeDetected):
            assert_no_bot_challenge(body, "/all-bids")

    def test_an_ordinary_page_is_not_flagged_as_a_challenge(self):
        assert_no_bot_challenge("<html>GeM | All Bids on GeM</html>", "/all-bids")

    def test_reset_session_drops_every_cookie(self):
        fetcher = GuardedFetcher()
        try:
            fetcher._client.cookies.set("TS0174a79d", "x", domain="bidplus.gem.gov.in")
            assert len(fetcher._client.cookies) == 1
            fetcher.reset_session()
            assert len(fetcher._client.cookies) == 0
        finally:
            fetcher.close()
