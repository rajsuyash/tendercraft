"""OCR fallback for pages that carry no extractable text.

WHY THIS EXISTS. Measured on a real customer's tender folder (Usha Martin, 2026-09-09): 480
pages, and only 48% carried extractable text. The unreadable half was almost entirely the
BIDDER's own documents — proven-supply self-certifications, licences, local-content
declarations — which is precisely the evidence the product needs and the only material a house
style or answer library could ever be built from. Without OCR, half of what a customer hands us
is invisible, and the half that is invisible is the half that is theirs.

WHAT THIS IS NOT. `tools/vision_ocr.swift` is macOS-only, so this is the LOCAL proof. The engine
image is Linux and cannot run it: `available()` returns False there and every caller degrades to
"no text", exactly as today. A Linux adapter and its validation against the same pages is M2.
Enabling this as though it were the production answer would leave scans silently unread in the
one place it matters.

SAFETY. Document content never reaches a command line. `pdftoppm` and the adapter are invoked
with fixed argv shapes and paths this module generates inside a temp directory it owns and
deletes; no shell, no globbing, no caller-supplied strings as arguments (G-6). Every call is
bounded by page count, resolution and wall-clock timeout, because a 500-page scan must not be
able to occupy a worker indefinitely.

COST. Zero. Vision ships with macOS and no page leaves the machine, which also keeps the
data-residency question out of the way while the approach is being proven.
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

#: Emitted by the Swift adapter between pages. A record separator, so it cannot collide with
#: anything Vision returns as text.
_PAGE_BREAK = "\x1eTENDERCRAFT_PAGE_BREAK\x1e"

#: Bounds. A scanned tender package is routinely 50+ pages and a customer can upload several;
#: these exist so one document cannot occupy a worker indefinitely.
MAX_PAGES = int(os.environ.get("OCR_MAX_PAGES", "60"))
DPI = int(os.environ.get("OCR_DPI", "200"))          # legible for 8-10pt certificate text
TIMEOUT_S = int(os.environ.get("OCR_TIMEOUT_S", "300"))

_ADAPTER_SRC = Path(__file__).resolve().parents[3] / "tools" / "vision_ocr.swift"
_BUILT: Path | None = None


def _binary() -> Path | None:
    """Compile the adapter once per process, or None where it cannot be built.

    Compiled rather than run through `swift` each time: the interpreter re-parses on every
    invocation, and this is called per document.
    """
    global _BUILT
    if _BUILT is not None:
        return _BUILT if _BUILT.exists() else None
    if not _ADAPTER_SRC.exists() or not shutil.which("swiftc"):
        return None
    out = Path(tempfile.gettempdir()) / "tendercraft-vision-ocr"
    if not out.exists():
        try:
            subprocess.run(
                ["swiftc", "-O", "-o", str(out), str(_ADAPTER_SRC)],
                check=True, capture_output=True, timeout=180,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("OCR adapter did not build; scans stay unreadable: %s", exc)
            return None
    _BUILT = out
    return out


def available() -> bool:
    """Can this process OCR at all? False on Linux, and on any machine without the toolchain.

    Callers must check rather than catch: "no OCR here" is an ordinary deployment fact, not an
    error, and a page that could not be read must look the same as it does today.
    """
    return bool(shutil.which("pdftoppm")) and _binary() is not None


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

    binary = _binary()
    if binary is None:
        return {}

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
        if not rendered:
            return {}

        try:
            proc = subprocess.run(
                [str(binary), *(str(p) for _, p in rendered)],
                check=True, capture_output=True, timeout=TIMEOUT_S, text=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("OCR adapter failed on %d pages: %s", len(rendered), exc)
            return {}

        parts = proc.stdout.split(_PAGE_BREAK)
        if len(parts) != len(rendered):
            # A mismatch means the adapter and this module disagree about the protocol. Return
            # nothing rather than pairing text with the wrong page: a citation anchored to the
            # wrong page is worse than a page nobody could read.
            log.warning("OCR returned %d blocks for %d pages; discarding",
                        len(parts), len(rendered))
            return {}
        # NUL bytes: Postgres text cannot store one (see app/ingest.parse_pdf_pages).
        return {
            page: parts[i].replace("\x00", "").strip()
            for i, (page, _) in enumerate(rendered)
            if parts[i].strip()
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
