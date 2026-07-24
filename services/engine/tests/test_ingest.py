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
