"""Ingestion glue — PDF parse guard + per-page extraction aggregation (no live model)."""

from __future__ import annotations

import pytest

from app import ingest
from app.envelope import ApiError
from pipeline.extractor import ExtractedCriterion


def test_parse_pdf_rejects_garbage():
    with pytest.raises(ApiError) as e:
        ingest.parse_pdf_pages(b"definitely not a pdf")
    assert e.value.code == "BAD_DOCUMENT"
    assert e.value.status == 400


def test_short_page_flagged_illegible_not_extracted(monkeypatch):
    monkeypatch.setattr("pipeline.extractor.extract_from_page", lambda t, p: [])
    result = ingest.ingest_pages([(1, "tiny")])  # < 20 chars -> scan/illegible (EC-1)
    assert result["illegible_pages"] == [1]
    assert result["extracted"] == 0


def _crit(conf, page, needs):
    return ExtractedCriterion(
        verbatim_text="x",
        category="eligibility",
        requirement_level="mandatory",
        confidence=conf,
        anchor_page=page,
        anchor_clause="4.1(a)",
        evidence_required="",
        evaluation_weight=None,
        needs_confirmation=needs,
    )


def test_aggregates_criteria_and_counts_low_confidence(monkeypatch):
    def fake(text, page):
        return [_crit(0.6, page, True), _crit(0.9, page, False)]

    monkeypatch.setattr("pipeline.extractor.extract_from_page", fake)
    result = ingest.ingest_pages([(1, "a long enough page of real tender text here")])
    assert result["extracted"] == 2
    assert result["low_confidence"] == 1
    assert result["criteria_rows"][0]["anchor_page"] == 1
    assert result["criteria_rows"][0]["confirmed"] is False  # nothing auto-confirmed


def test_empty_clause_stored_as_null(monkeypatch):
    def fake(text, page):
        c = _crit(0.9, page, False)
        return [ExtractedCriterion(**{**c.__dict__, "anchor_clause": ""})]

    monkeypatch.setattr("pipeline.extractor.extract_from_page", fake)
    result = ingest.ingest_pages([(1, "a long enough page of real tender text here")])
    assert result["criteria_rows"][0]["anchor_clause"] is None


# ---------- package ingest: spreadsheets + multi-document anchors ----------
def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_spreadsheet_reads_one_page_per_sheet_with_the_sheet_as_locator():
    data = _xlsx({
        "BOQ": [["Item", "Qty"], ["Rack Server", 4]],
        "Eligibility": [["Turnover", "INR 10 Cr"]],
    })
    pages = ingest.parse_spreadsheet_pages("boq.xlsx", data)
    assert [p.document for p in pages] == ["boq.xlsx · BOQ", "boq.xlsx · Eligibility"]
    assert [p.page for p in pages] == [1, 2]
    assert "Rack Server | 4" in pages[0].text
    assert "INR 10 Cr" in pages[1].text


def test_csv_is_readable_as_a_tender_document():
    pages = ingest.parse_document_pages("boq.csv", b"Item,Amount\nRack Server,5820000\n")
    assert len(pages) == 1
    assert "Rack Server | 5820000" in pages[0].text


def test_unsupported_format_is_refused_not_read_as_bytes():
    with pytest.raises(ApiError) as e:
        ingest.parse_document_pages("scan.tiff", b"\x00\x01")
    assert e.value.code == "UNSUPPORTED_FORMAT"
    assert e.value.status == 400


def test_package_numbers_globally_and_maps_back_to_local_pages():
    docs = [
        ingest.SourcePage("NIT.pdf", 1, "a"),
        ingest.SourcePage("NIT.pdf", 2, "b"),
        ingest.SourcePage("Annexure-II.pdf", 1, "c"),
    ]
    pages, index = ingest.number_package(docs)
    # The extractor sees a page number unique across the package...
    assert pages == [(1, "a"), (2, "b"), (3, "c")]
    # ...but page 3 of the package is page 1 of the annexure, which is what a human opens.
    assert (index[3].document, index[3].page) == ("Annexure-II.pdf", 1)


def test_criterion_anchor_is_rewritten_to_its_own_document():
    from app.tenders import _relocate

    _, index = ingest.number_package([
        ingest.SourcePage("NIT.pdf", 1, "a"),
        ingest.SourcePage("Annexure-II.pdf", 4, "b"),
    ])
    row = _relocate({"verbatim_text": "x", "anchor_page": 2, "anchor_clause": "3.1"}, index)
    assert (row["anchor_document"], row["anchor_page"]) == ("Annexure-II.pdf", 4)


def test_criterion_off_the_end_of_the_package_keeps_no_anchor():
    # A hallucinated page must not become a plausible wrong citation — unanchored means the
    # lock gate refuses it (A-AC5), which is the right outcome for something nobody can check.
    from app.tenders import _relocate

    _, index = ingest.number_package([ingest.SourcePage("NIT.pdf", 1, "a")])
    row = _relocate({"verbatim_text": "x", "anchor_page": 99}, index)
    assert row["anchor_page"] is None and row["anchor_document"] is None


def test_anchor_label_names_the_document_and_never_doubles_a_clause_prefix():
    from app.deterministic.types import SourceAnchor

    assert SourceAnchor(4, "3.1", "Annexure-II.pdf").label() == "Annexure-II.pdf · p.4 · Cl. 3.1"
    assert SourceAnchor(4, "Annexure-VII").label() == "p.4 · Annexure-VII"
    assert SourceAnchor(12, "").label() == "p.12"
