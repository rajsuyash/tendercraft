"""Document ingestion — PDF bytes -> per-page text, with an honest quality gate.

Ported by COPY from the bidder engine's app/ingest.py. Not imported: the F13 wall forbids a
shared module between the two products, and `tools/check-wall.sh` fails the build on a stray
`from app…`. Duplication is the cheaper failure here.

Text PDFs are parsed with pypdf. Image-only scans yield almost no text and are REPORTED as
illegible rather than passed through silently — a bidder disqualified because page 14 was a
photograph is the worst outcome this product can produce.
"""

from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor

from pypdf import PdfReader

from .envelope import ApiError

# A page with almost no extractable text is probably a scan.
_MIN_CHARS_PER_PAGE = 20
# One model call per page; sequential is minutes on a real RFP. Bounded fan-out.
_WORKERS = int(os.environ.get("EVAL_EXTRACT_WORKERS", "8"))
# Below this, a human confirms before the value is trusted.
CONFIRM_THRESHOLD = 0.80


def parse_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    """(page_number, text) per page, 1-indexed."""
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — any parse failure is a bad upload
        raise ApiError(400, "BAD_DOCUMENT", f"could not read PDF: {exc}") from exc

    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, 1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:  # noqa: BLE001 — one bad page must not 500 the upload
            text = ""
        pages.append((i, text))
    return pages


def split_legible(pages: list[tuple[int, str]]) -> tuple[list[tuple[int, str]], list[int]]:
    """(legible pages, illegible page numbers). The caller surfaces the latter to the officer."""
    legible = [(p, t) for p, t in pages if len(t) >= _MIN_CHARS_PER_PAGE]
    illegible = [p for p, t in pages if len(t) < _MIN_CHARS_PER_PAGE]
    return legible, illegible


def map_pages(fn, pages: list[tuple[int, str]]) -> list:
    """Fan `fn(page_no, text)` across pages, preserving input order.

    pool.map keeps order and `pages` is page-ascending, so results stay page-ascending — which
    is what keeps extracted anchors in reading order without a re-sort.
    """
    if not pages:
        return []
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        return list(pool.map(lambda pt: fn(pt[0], pt[1]), pages))
