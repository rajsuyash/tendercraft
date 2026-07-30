"""Phase 2 tests — the eligibility parser.

Golden fixtures are three REAL bid documents fetched from bidplus.gem.gov.in on 2026-07-30,
byte-for-byte as served. They are here because this parser's entire risk is GeM's actual
template variation, and every single gap found during development came from a document shape I
had not seen — not from a case I could have imagined. In particular the high-value fixture is
what revealed that EMD has two mutually exclusive shapes.

**They are NOT committed.** This repository is public, and GeM's copyright policy forbids
reproducing its content without prior written permission (docs/discovery/source-gem.md §8) — so
publishing them here would breach, from this very module, the clause the module exists to
respect. `uv run python -m tests.fetch_fixtures` regenerates them; see fixtures/README.md.

Consequence to keep in mind: the golden assertions below SKIP on a machine without fixtures,
including CI. Everything that encodes a dangerous rule — `parse_amount`'s unit refusal, section
bounding, the tri-state booleans, the non-PDF guard — is fixture-free and always runs.

Chosen to span the template space:
  * `services`  — turnover + estimated value, EMD/ePBG explicitly "No"
  * `high`      — ₹250 Cr turnover, EMD as an *amount*, ePBG as a *percentage*, experience years
  * `boq`       — turnover and experience genuinely ABSENT (proves None means absent, not missed)
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from app.document import (
    _section,
    _yes_no,
    fetch_bid_document,
    parse_amount,
    parse_bid_document,
    parse_lines,
)
from app.fetch import GuardedFetcher

FIXTURES = Path(__file__).parent / "fixtures"


def _load(shape: str) -> bytes:
    """Resolve by prefix: the parent-bid id in each filename changes as bids close, so the
    fetch script cannot produce stable names."""
    matches = sorted(FIXTURES.glob(f"gem-{shape}-*.pdf"))
    if not matches:
        pytest.skip(
            f"no gem-{shape}-*.pdf fixture — run `uv run python -m tests.fetch_fixtures` "
            "(fixtures are gitignored: public repo, GeM reproduction clause)"
        )
    return matches[0].read_bytes()


def _pdf_bytes(shape: str) -> bytes:
    return _load(shape)


@pytest.fixture(scope="module")
def services() -> dict:
    return parse_bid_document(_load("services-bid"))


@pytest.fixture(scope="module")
def high_value() -> dict:
    return parse_bid_document(_load("high"))


@pytest.fixture(scope="module")
def boq() -> dict:
    return parse_bid_document(_load("boq"))


class TestParseAmount:
    """Indian numbering. A Lakh/Crore slip is a 100x error that still looks like a plausible
    rupee figure, and it lands on the one comparison that decides eligibility."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("5 Lakh (s)", 500_000),
            ("25000 Lakh (s)", 2_500_000_000),
            ("3.93 (in lakhs)", 393_000),
            ("2 Crore", 20_000_000),
            ("1.5 crores", 15_000_000),
            ("5458313.82", 5_458_314),  # rounded: paise never decide eligibility
            ("31200000", 31_200_000),
            ("1,20,000", 120_000),  # Indian digit grouping
            ("Rs 5 Lakh", 500_000),
        ],
    )
    def test_known_units(self, raw, expected):
        assert parse_amount(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "Not Applicable", "NA"])
    def test_no_number_is_none(self, raw):
        assert parse_amount(raw) is None

    @pytest.mark.parametrize("raw", ["5 Million", "5 Billion", "5 thousand", "12 percent"])
    def test_an_unknown_unit_is_refused_not_assumed_to_be_rupees(self, raw):
        # The dangerous default: falling through to rupees would read "5 Million" as ₹5 and
        # hand a bidder a Likely-eligible they do not have (ET-1). None is the safe answer.
        assert parse_amount(raw) is None


class TestYesNo:
    def test_tri_state(self):
        assert _yes_no("Yes") is True
        assert _yes_no("No") is False
        # None, not False: "we could not read the row" and "no EMD is required" are different
        # facts, and collapsing them tells a bidder they need no bank guarantee.
        assert _yes_no(None) is None
        assert _yes_no("Refer ATC") is None


class TestSectionBounding:
    """The regression that matters most in this file.

    `/Required` appears under both `/EMD Detail` and `/ePBG Detail`. When the EMD section has no
    `/Required` of its own — which is what every high-value bid looks like — an unbounded scan
    reads the ePBG row and reports it as the EMD answer.
    """

    def test_a_section_stops_at_the_next_heading(self):
        lines = [
            "/EMD Detail",
            "  /EMD Amount        31200000",
            "/ePBG Detail",
            "  /Required          No",
        ]
        emd = _section(lines, "/EMD Detail")
        assert any("/EMD Amount" in line for line in emd)
        assert not any("/Required" in line for line in emd)

    def test_emd_does_not_inherit_epbgs_required_row(self):
        lines = [
            "/EMD Detail",
            "/ePBG Detail",
            "  /Required          No",
        ]
        assert _section(lines, "/EMD Detail") == []


class TestTemplateShapes:
    """The field logic, over synthetic line-sets in GeM's layout.

    These describe the template rather than any one bid, so they need no GeM content and always
    run in CI — which is the only regression coverage this parser has there, the real documents
    being uncommittable. Written from the shapes observed in live bids on 2026-07-30.
    """

    LOW_VALUE = [
        "     /Bid End Date/Time           10-06-2026 14:00:00",
        "     /Ministry/State Name         Ministry Of Steel",
        "     /Organisation Name           Bhilai Steel Plant",
        "/Minimum Average Annual Turnover of the              5 Lakh (s)",
        "bidder (For 3 Years)",
        "     / Estimated Bid Value in INR (Inclusive of all   5458313.82",
        "/EMD Detail",
        "     /Required                    No",
        "/ePBG Detail",
        "     /Required                    No",
        "/MSE Purchase Preference",
        "     /MSE Purchase Preference     Yes",
    ]

    HIGH_VALUE = [
        "/Minimum Average Annual Turnover of the              25000 Lakh (s)",
        "     /Years of Past Experience Required for          3 Year (s)",
        "/EMD Detail",
        "     /EMD Amount                  31200000",
        "/ePBG Detail",
        "     /ePBG Percentage(%)          5.00",
        "/MII Compliance",
        "     /MII Compliance              Yes",
    ]

    def test_low_value_shape(self):
        f = parse_lines(self.LOW_VALUE)
        assert f["min_avg_annual_turnover_inr"] == 500_000
        assert f["estimated_value_inr"] == 5_458_314
        assert f["emd_required"] is False and f["emd_amount_inr"] is None
        assert f["epbg_required"] is False
        assert f["mse_purchase_preference"] is True
        assert f["ministry"] == "Ministry Of Steel"

    def test_high_value_shape_reads_emd_as_an_amount(self):
        # The gap that mattered: no /Required row exists here, and reporting None would hide a
        # ₹3.12 crore deposit behind an "unknown".
        f = parse_lines(self.HIGH_VALUE)
        assert f["emd_required"] is True
        assert f["emd_amount_inr"] == 31_200_000
        assert f["epbg_required"] is True
        assert f["epbg_percentage"] == "5.00"
        assert f["min_avg_annual_turnover_inr"] == 2_500_000_000
        assert f["past_experience_required_raw"] == "3 Year (s)"

    def test_absent_fields_are_none_not_zero(self):
        f = parse_lines(["/EMD Detail", "     /Required   No"])
        assert f["min_avg_annual_turnover_inr"] is None
        assert f["estimated_value_inr"] is None
        assert f["past_experience_required_raw"] is None
        assert f["epbg_required"] is None  # no ePBG section at all — unknown, not False

    def test_the_guidance_boilerplate_is_not_parsed_as_a_value(self):
        # Present in every GeM document, and it contains a number later in the sentence.
        f = parse_lines([
            "3. Estimated Bid Value indicated above is being declared solely for the purpose",
            "of guidance on EMD amount and for determining the Eligibility Criteria related to",
        ])
        assert f["estimated_value_inr"] is None

    def test_documents_required_comes_from_the_block_above_the_label(self):
        f = parse_lines([
            "                              Experience Criteria,Bidder Turnover,Certificate",
            "                              (Requested in ATC)",
            "  /Document required          *In case any bidder is seeking exemption from",
            "from seller                   Turnover Criteria, the supporting documents",
        ])
        assert f["documents_required_from_seller"] == (
            "Experience Criteria,Bidder Turnover,Certificate (Requested in ATC)"
        )
        assert "In case any bidder" not in f["documents_required_from_seller"]

    def test_emd_section_does_not_read_epbgs_required_row(self):
        f = parse_lines(["/EMD Detail", "/ePBG Detail", "     /Required   Yes"])
        assert f["emd_required"] is None      # EMD section is genuinely empty
        assert f["epbg_required"] is True


class TestRealDocumentInvariants:
    """Against real bytes, assert only what must hold for ANY GeM bid document.

    Deliberately not asserting this bid's specific numbers: fixtures are regenerated from
    whatever is open on the portal that day, so value-pinned assertions would fail on every
    refresh and the fetch script would be unusable. The specific numbers are covered by
    TestTemplateShapes above.
    """

    @pytest.mark.parametrize("shape", ["services-bid", "high", "boq"])
    def test_bid_number_shape(self, shape):
        fields = parse_bid_document(_load(shape))
        assert re.match(r"GEM/\d{4}/[BR]/\d+", fields["bid_number"] or "")

    @pytest.mark.parametrize("shape", ["services-bid", "high", "boq"])
    def test_parsed_amounts_agree_with_their_own_raw_strings(self, shape):
        fields = parse_bid_document(_load(shape))
        assert fields["min_avg_annual_turnover_inr"] == parse_amount(
            fields["min_avg_annual_turnover_raw"]
        )
        assert fields["estimated_value_inr"] == parse_amount(fields["estimated_value_raw"])

    @pytest.mark.parametrize("shape", ["services-bid", "high", "boq"])
    def test_an_emd_amount_always_implies_required(self, shape):
        fields = parse_bid_document(_load(shape))
        if fields["emd_amount_inr"]:
            assert fields["emd_required"] is True
        if fields["epbg_percentage"]:
            assert fields["epbg_required"] is True

    @pytest.mark.parametrize("shape", ["services-bid", "high", "boq"])
    def test_no_gem_boilerplate_leaks_into_a_fact_field(self, shape):
        fields = parse_bid_document(_load(shape))
        docs = fields["documents_required_from_seller"] or ""
        assert "In case any bidder" not in docs
        assert "declared solely for the purpose" not in docs

    def test_the_boq_fixture_really_lacks_a_turnover_row(self):
        # Guards the meaning of None: if a future regression returned None for everything, the
        # other fixtures' invariants would still pass. This one asserts a known absence.
        fields = parse_bid_document(_load("boq"))
        assert fields["min_avg_annual_turnover_raw"] is None


class TestFetchGuard:
    def _fetcher(self, body: bytes, content_type: str = "application/pdf") -> GuardedFetcher:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /resources/\n")
            return httpx.Response(200, headers={"content-type": content_type}, content=body)

        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            headers={"User-Agent": "test"},
        )
        return GuardedFetcher(client=client)

    def test_an_empty_body_is_refused(self):
        # GeM answers an unknown id with 200 + content-type application/pdf + ZERO bytes.
        # Hit for real by passing a bid number where a parent id belongs.
        fetcher = self._fetcher(b"")
        try:
            with pytest.raises(ValueError, match="did not return a PDF"):
                fetch_bid_document(fetcher, 12345)
        finally:
            fetcher.close()

    def test_an_html_error_page_is_refused_rather_than_parsed(self):
        fetcher = self._fetcher(b"<!DOCTYPE html><html>Error</html>")
        try:
            with pytest.raises(ValueError, match="did not return a PDF"):
                fetch_bid_document(fetcher, 12345)
        finally:
            fetcher.close()

    def test_a_real_pdf_passes_through(self):
        body = _pdf_bytes("services-bid")
        fetcher = self._fetcher(body)
        try:
            assert fetch_bid_document(fetcher, 9375631).startswith(b"%PDF")
        finally:
            fetcher.close()
