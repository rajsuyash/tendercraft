"""OCR fallback for pages that carry no extractable text.

WHY THIS EXISTS. Measured on a real customer's tender folder (Usha Martin, 2026-09-09): 480
pages, and only 48% carried extractable text. The unreadable half was almost entirely the
BIDDER's own documents — proven-supply self-certifications, licences, local-content
declarations — which is precisely the evidence the product needs and the only material a house
style or answer library could ever be built from. Without OCR, half of what a customer hands us
is invisible, and the half that is invisible is the half that is theirs.

THE ENGINE. Tesseract, chosen on measurement rather than preference: task A1
(docs/ocr-measurement.md) ran it against that same real corpus and it recovered 242 of 248
previously-unreadable pages (98%), at zero marginal cost, with samples read by a human before
adoption. Revisit with that script, not with an opinion.

SAFETY. Document content never reaches a command line. `pdftoppm` and `tesseract` are invoked
with fixed argv shapes and paths this module generates inside a temp directory it owns and
deletes; no shell, no globbing, no caller-supplied strings as arguments (G-6). Every call is
bounded by page count, resolution and wall-clock timeout, because a 500-page scan must not be
able to occupy a worker indefinitely.

COST. Zero. Both binaries are open source and run inside the engine's own container; no page
ever leaves it, which also keeps the data-residency question out of the way.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

log = logging.getLogger("tendercraft.engine")

#: The OCR engine. Tesseract because A1 measured it against the real customer corpus and it
#: cleared the bar at zero marginal cost — 242 of 248 unreadable pages recovered, samples read
#: by a human. docs/ocr-measurement.md carries the numbers.
_TESSERACT = "tesseract"

#: Bounds. A scanned tender package is routinely 50+ pages and a customer can upload several;
#: these exist so one document cannot occupy a worker indefinitely.
MAX_PAGES = int(os.environ.get("OCR_MAX_PAGES", "60"))
DPI = int(os.environ.get("OCR_DPI", "200"))          # legible for 8-10pt certificate text
TIMEOUT_S = int(os.environ.get("OCR_TIMEOUT_S", "300"))


def available() -> bool:
    """Can this process OCR at all?

    Callers must check rather than catch: "no OCR here" is an ordinary deployment fact, not an
    error, and a page that could not be read must look exactly as illegible as it already was.
    """
    return bool(shutil.which("pdftoppm")) and bool(shutil.which(_TESSERACT))


def ocr_pdf_pages(data: bytes, pages: Sequence[int]) -> dict[int, str]:
    """OCR the given 1-indexed PDF pages. Returns {page: text} for whatever succeeded.

    Never raises and never partially fails the caller: a page that cannot be rendered or read
    is simply absent from the result, which leaves it exactly as illegible as it already was.
    """
    wanted = sorted({p for p in pages if p >= 1})[:MAX_PAGES]
    if not wanted or not available():
        return {}
    if len(pages) > MAX_PAGES:
        # Said out loud rather than silently truncated: a partial OCR that looks complete is
        # the same class of failure as a capped sweep that reports success.
        log.warning("OCR capped at %d pages; %d requested", MAX_PAGES, len(pages))

    work = Path(tempfile.mkdtemp(prefix="tc-ocr-"))
    try:
        src = work / "in.pdf"
        src.write_bytes(data)
        rendered: list[tuple[int, Path]] = []
        for page in wanted:
            stem = work / f"p{page}"
            try:
                subprocess.run(
                    ["pdftoppm", "-png", "-r", str(DPI),
                     "-f", str(page), "-l", str(page), str(src), str(stem)],
                    check=True, capture_output=True, timeout=TIMEOUT_S,
                )
            except (subprocess.SubprocessError, OSError):
                continue
            # pdftoppm decides the suffix width from the page count; glob our own stem rather
            # than guessing between p1-1.png and p1-01.png.
            matches = sorted(work.glob(f"p{page}-*.png"))
            if matches:
                rendered.append((page, matches[0]))

        out: dict[int, str] = {}
        for page, image in rendered:
            try:
                proc = subprocess.run(
                    [_TESSERACT, str(image), "stdout"],
                    check=True, capture_output=True, timeout=TIMEOUT_S, text=True,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                # One page, one failure. The batched macOS adapter discarded all sixty pages
                # when its page-break protocol disagreed; per-page has no protocol to disagree
                # with — nothing here can desynchronise the rest.
                log.warning("OCR failed on page %d: %s", page, exc)
                continue
            # NUL bytes: Postgres text cannot store one (app/ingest.parse_pdf_pages).
            text = proc.stdout.replace("\x00", "").strip()
            if text:
                out[page] = text
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)
