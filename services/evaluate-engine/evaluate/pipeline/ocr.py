"""Vision-model OCR fallback for pages with no usable text layer (F16, decision D7).

Runs ONLY on pages `ingest.split_legible` already classified as illegible. That is the whole
cost control: a text-layer PDF triggers zero calls, and the tender-wide page budget bounds the
rest. No new vendor and no new credential — this is the same EVAL_MODEL_API_KEY the rest of the
pipeline uses.

The asymmetry that shapes every decision here: reporting a readable page as illegible costs an
officer a manual read. Reporting an unreadable page as readable, or inventing a figure on it,
costs a bidder their bid. Bias toward "illegible" on every ambiguous path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..ingest import render_page_png
from .client import ModelError, generate_json
from .schemas import OCR_SCHEMA

_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "ocr_page.md"

# Below this, whatever came back is not a transcription. Matches ingest._MIN_CHARS_PER_PAGE:
# the same bar the text-layer path uses, so a page cannot be "illegible" to one and fine to
# the other.
_MIN_CHARS = 20


@dataclass(frozen=True)
class OcrResult:
    page_no: int
    text: str
    legible: bool
    budget_exceeded: bool = False


def ocr_page(pdf_bytes: bytes, page_no: int) -> OcrResult:
    """Transcribe one page. Never raises — an unreadable page is a result, not an error."""
    try:
        png = render_page_png(pdf_bytes, page_no)
    except Exception:  # noqa: BLE001 — a page that will not rasterise is simply illegible
        return OcrResult(page_no, "", False)

    try:
        out = generate_json(_PROMPT.read_text(), OCR_SCHEMA, image_png=png)
    except ModelError:
        return OcrResult(page_no, "", False)

    text = (out.get("page_text") or "").strip()
    legible = bool(out.get("legible")) and len(text) >= _MIN_CHARS
    # If the model says illegible, believe it even when it also returned text. The reverse —
    # claiming legible on an empty transcription — is the failure that qualifies a bidder on
    # fiction, so the length check overrides the flag in that direction only.
    return OcrResult(page_no, text if legible else "", legible)


def ocr_pages(pdf_bytes: bytes, page_numbers: list[int], *, budget: int) -> list[OcrResult]:
    """OCR each illegible page up to the tender's remaining budget (ENV-9).

    Pages past the budget come back flagged rather than silently skipped: F16-ERR1 surfaces
    them to the officer with an override. A silent skip is indistinguishable from a blank page.
    """
    out: list[OcrResult] = []
    for i, page_no in enumerate(page_numbers):
        if i >= budget:
            out.append(OcrResult(page_no, "", False, budget_exceeded=True))
            continue
        out.append(ocr_page(pdf_bytes, page_no))
    return out


# ── eval hook (evals/ocr) ──────────────────────────────────────────────────────
def score_eval_case(case: dict) -> tuple[bool, str]:
    expect = case["expect"]

    if case.get("inject") == "budget_exceeded":
        results = ocr_pages(b"", [1, 2], budget=0)
        if not all(r.budget_exceeded for r in results):
            return False, "budget exhaustion did not flag the skipped pages"
        if any(r.legible for r in results):
            return False, "a page past the budget was reported legible"
        return True, ""

    if case.get("inject") == "model_error":
        import evaluate.pipeline.client as client_mod

        original = client_mod.generate_json
        client_mod.generate_json = _raise_model_error
        try:
            got = ocr_page(_fixture_bytes(case), 1)
        finally:
            client_mod.generate_json = original
        return (not got.legible, "" if not got.legible else "model failure reported legible")

    fixture = Path(__file__).resolve().parents[2] / case["fixture"]
    if not fixture.exists():
        return False, f"fixture missing: {case['fixture']} (create it alongside the component)"

    got = ocr_page(fixture.read_bytes(), 1)
    if expect.get("legible") is False:
        if got.legible:
            return False, ("an illegible page was reported legible — "
                           "this qualifies a bidder on fiction")
        return True, ""
    if not got.legible:
        return False, "a legible page was reported illegible"
    for needle in expect.get("text_contains", []):
        if needle not in got.text:
            return False, f"transcription missing {needle!r}"
    return True, ""


def _fixture_bytes(case: dict) -> bytes:
    p = Path(__file__).resolve().parents[2] / case.get("fixture", "")
    return p.read_bytes() if p.exists() else b""


def _raise_model_error(*_args, **_kwargs):
    raise ModelError("injected")
