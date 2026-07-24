"""Ingestion — tender document -> per-page text -> extracted criteria (Module A).

Text-based PDFs are parsed with pypdf. Scanned PDFs (image-only pages) yield little text
and route to manual review (EC-1); OCR of scans is a later step. Extraction runs per page
so every criterion keeps its page anchor (A-AC3).
"""

from __future__ import annotations

import io

from pypdf import PdfReader

from .deterministic.types import EXTRACTION_CONFIRM_THRESHOLD
from .envelope import ApiError

# A page with almost no extractable text is probably a scan — flag for manual OCR (EC-1).
_MIN_CHARS_PER_PAGE = 20


def parse_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    """Return (page_number, text) for each page. 1-indexed pages."""
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — any parse failure is a bad upload, surfaced as 400
        raise ApiError(400, "BAD_DOCUMENT", f"could not read PDF: {exc}") from exc

    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, 1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:  # noqa: BLE001 — a single unreadable page shouldn't 500; treat as illegible
            text = ""
        pages.append((i, text))
    return pages


def ingest_pages(pages: list[tuple[int, str]]) -> dict:
    """Run the extractor over pages; return criteria rows + ingestion stats.

    Imported lazily so unit tests can monkeypatch the extractor without a live key.
    """
    from pipeline.extractor import extract_from_page

    rows: list[dict] = []
    low_conf = 0
    illegible_pages: list[int] = []

    for page_no, text in pages:
        if len(text) < _MIN_CHARS_PER_PAGE:
            illegible_pages.append(page_no)
            continue
        for c in extract_from_page(text, page_no):
            if c.needs_confirmation:
                low_conf += 1
            rows.append(
                {
                    "verbatim_text": c.verbatim_text,
                    "category": c.category,
                    "requirement_level": c.requirement_level,
                    "confidence": c.confidence,
                    "confirmed": False,
                    "anchor_page": c.anchor_page,
                    "anchor_clause": c.anchor_clause or None,
                    "evidence_required": c.evidence_required or None,
                    "evaluation_weight": c.evaluation_weight,
                }
            )

    return {
        "criteria_rows": rows,
        "extracted": len(rows),
        "low_confidence": low_conf,
        "illegible_pages": illegible_pages,
        "confirm_threshold": EXTRACTION_CONFIRM_THRESHOLD,
    }
