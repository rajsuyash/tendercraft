"""Ingestion — tender document -> per-page text -> extracted criteria (Module A).

Text-based PDFs are parsed with pypdf. Scanned PDFs (image-only pages) yield little text
and route to manual review (EC-1); OCR of scans is a later step. Extraction runs per page
so every criterion keeps its page anchor (A-AC3).
"""

from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor

from pypdf import PdfReader

from .deterministic.tender_meta import extract_tender_meta
from .deterministic.types import EXTRACTION_CONFIRM_THRESHOLD
from .envelope import ApiError

# A page with almost no extractable text is probably a scan — flag for manual OCR (EC-1).
_MIN_CHARS_PER_PAGE = 20
# Per-page extraction is one Gemini call each; sequential is minutes on a real RFP.
# Fan out across pages, bounded so we don't hammer the API. Order restored after.
_EXTRACT_WORKERS = int(os.environ.get("INGEST_EXTRACT_WORKERS", "8"))


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

    illegible_pages = [p for p, t in pages if len(t) < _MIN_CHARS_PER_PAGE]
    legible = [(p, t) for p, t in pages if len(t) >= _MIN_CHARS_PER_PAGE]

    # One Gemini call per page, fanned out. pool.map preserves input order and `legible` is
    # page-ascending, so rows stay page-ascending without a re-sort (anchors ordered, A-AC3).
    with ThreadPoolExecutor(max_workers=_EXTRACT_WORKERS) as pool:
        per_page = pool.map(lambda pt: extract_from_page(pt[1], pt[0]), legible)

    rows: list[dict] = []
    low_conf = 0
    for criteria in per_page:
        for c in criteria:
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

    # The document states its own identity on page one. Reading it is why a bid stops
    # being called "rfp.pdf" on every screen.
    meta = extract_tender_meta([text for _page, text in pages])

    return {
        "meta": meta,
        "criteria_rows": rows,
        "extracted": len(rows),
        "low_confidence": low_conf,
        "illegible_pages": illegible_pages,
        "confirm_threshold": EXTRACTION_CONFIRM_THRESHOLD,
    }
