#!/usr/bin/env python3
"""How much of a real tender folder can Tesseract actually read, and how fast?

Kept in the repo because this is the script that decides the OCR provider, and that decision
will be revisited. Re-run it rather than reasoning about it.

    services/engine/.venv/bin/python tools/measure-ocr.py "Sample Tender Usha Martin"

WHERE IT SHOULD RUN. The engine is Linux, so the honest place is the measurement image
(`tools/ocr-measure.Dockerfile`). Run on macOS the RECOVERY RATE is still valid — it is the
same Tesseract engine and the same page images — but the SECONDS PER PAGE is a floor, not the
production number: Apple silicon is faster than a Cloud Run vCPU. The report says which
platform produced it, because a timing quoted without its hardware is not a measurement.

A character count is NOT quality. The samples exist so a human reads them before anyone
decides this clears A-FR6's accuracy bar.
"""

from __future__ import annotations

import pathlib
import platform
import subprocess
import sys
import tempfile
import time

from pypdf import PdfReader

MIN_CHARS = 20  # ingest.MIN_CHARS_PER_PAGE — one definition of "legible", not two
DPI = 200       # ocr.py:DPI


def text_layer(pdf: pathlib.Path) -> list[str]:
    try:
        return [(p.extract_text() or "").replace("\x00", "") for p in PdfReader(pdf).pages]
    except Exception as exc:  # noqa: BLE001 — a corrupt file is a result, not a crash
        print(f"  !! unreadable PDF: {exc}")
        return []


def ocr_page(pdf: pathlib.Path, page: int, work: pathlib.Path) -> tuple[str, float]:
    stem = work / f"p{page}"
    t0 = time.monotonic()
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(DPI), "-f", str(page), "-l", str(page),
         str(pdf), str(stem)],
        check=True, capture_output=True, timeout=180,
    )
    img = sorted(work.glob(f"p{page}-*.png"))
    if not img:
        return "", time.monotonic() - t0
    out = subprocess.run(
        ["tesseract", str(img[0]), "stdout"],
        check=True, capture_output=True, timeout=180, text=True,
    )
    return out.stdout, time.monotonic() - t0


def main(root: str) -> None:
    base = pathlib.Path(root)
    pdfs = sorted(base.rglob("*.pdf"))
    print(f"platform: {platform.system()} {platform.machine()}  ·  "
          f"corpus: {len(pdfs)} PDFs under {base}")
    tot_pages = tot_blank = tot_recovered = 0
    tot_secs = 0.0
    samples: list[tuple[str, str]] = []

    for pdf in pdfs:
        layers = text_layer(pdf)
        if not layers:
            continue
        blank = [i for i, t in enumerate(layers, 1) if len(t.strip()) < MIN_CHARS]
        recovered, secs, sample = 0, 0.0, ""
        with tempfile.TemporaryDirectory() as tmp:
            for page in blank:
                try:
                    text, dt = ocr_page(pdf, page, pathlib.Path(tmp))
                except Exception as exc:  # noqa: BLE001
                    print(f"  !! {pdf.name} p{page}: {exc}")
                    continue
                secs += dt
                if len(text.strip()) >= MIN_CHARS:
                    recovered += 1
                    if not sample:
                        sample = " ".join(text.split())[:240]
        tot_pages += len(layers)
        tot_blank += len(blank)
        tot_recovered += recovered
        tot_secs += secs
        if blank:
            print(f"\n{pdf.relative_to(base)}")
            print(f"  pages {len(layers)} · no text layer {len(blank)} · recovered {recovered}"
                  f" · {secs:.1f}s ({secs / max(1, len(blank)):.1f}s/page)")
            if sample:
                print(f"  sample: {sample}")
                samples.append((str(pdf.relative_to(base)), sample))

    print("\n" + "=" * 72)
    print(f"PDFs {len(pdfs)} · pages {tot_pages}")
    print(f"no text layer      {tot_blank} ({tot_blank / max(1, tot_pages):.0%} of pages)")
    print(f"recovered by OCR   {tot_recovered} ({tot_recovered / max(1, tot_blank):.0%} of those)")
    print(f"still unreadable   {tot_blank - tot_recovered}")
    print(f"OCR time           {tot_secs:.0f}s total · "
          f"{tot_secs / max(1, tot_blank):.1f}s/page")
    print(f"\nread these {len(samples)} samples before trusting the rate above.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Sample Tender Usha Martin")
