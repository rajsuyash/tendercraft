"""The scanned half of a tender must be read, after the response, and must never break it.

Measured on a real customer corpus (docs/ocr-measurement.md): 52% of 478 pages carried no text
layer, and that half was almost entirely the bidder's own certificates. `app/ocr.py` shipped
working and nothing called it, so every one of those pages was dropped at `ingest.py`'s
legibility floor and never looked at again.

Every test here is about the pass being *invisible when it fails* and *honest when it does not*:
an upload that already returned 200 cannot be un-returned, so a failure inside this pass has
nowhere to surface except a log line and a NULL stamp.
"""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from app import tenders


def _pdf(*page_texts: str) -> bytes:
    """A PDF with one blank page per argument. Text layers are added by monkeypatching the
    parser — building real ones needs a font library this engine does not carry, and the thing
    under test is the wiring, not pypdf."""
    writer = PdfWriter()
    for _ in page_texts:
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def scanned(monkeypatch):
    """A two-page package: page 1 legible, page 2 a scan (no text layer)."""
    from app import ingest

    monkeypatch.setattr(
        ingest, "parse_pdf_pages",
        lambda data: [(1, "Tender document. Bidders shall hold a valid ISO 9001."), (2, "")],
    )
    return [("nit.pdf", _pdf("a", "b"))]


def _capture(monkeypatch, *, title=tenders.PLACEHOLDER_TITLE):
    """Stub every write the pass can make and hand back what it actually did."""
    seen: dict = {"criteria": [], "unmapped": [], "stamped": [], "title": [], "meta": []}
    monkeypatch.setattr(tenders.db, "get_tender", lambda t, w: {"id": t, "title": title})
    monkeypatch.setattr(tenders.db, "insert_criteria",
                        lambda w, t, rows: seen["criteria"].extend(rows) or [])
    monkeypatch.setattr(tenders.db, "insert_unmapped",
                        lambda w, t, rows: seen["unmapped"].extend(rows) or [])
    monkeypatch.setattr(tenders.db, "mark_ocr_complete",
                        lambda w, t, n: seen["stamped"].append((w, t, n)))
    monkeypatch.setattr(tenders.db, "set_tender_title",
                        lambda t, w, new: seen["title"].append(new))
    monkeypatch.setattr(tenders.db, "set_tender_meta",
                        lambda t, w, num, auth: seen["meta"].append((num, auth)))
    return seen


def _extractor(monkeypatch, per_page):
    """Patch the model call. `per_page` maps a page's TEXT to the criteria it yields."""
    from pipeline import extractor

    class _C:
        def __init__(self, text, page):
            self.verbatim_text, self.anchor_page = text, page
            self.category, self.requirement_level = "technical", "mandatory"
            self.confidence, self.needs_confirmation = 0.9, False
            self.anchor_clause = self.evidence_required = ""
            self.evaluation_weight = None

    called: list[int] = []

    def _extract(text, page):
        called.append(page)
        found = per_page.get(text)
        return [_C(found, page)] if found else []

    monkeypatch.setattr(extractor, "extract_from_page", _extract)
    return called


# ── the feature ────────────────────────────────────────────────────────────────────────────

def test_a_scanned_page_reaches_the_extractor_after_the_pass(monkeypatch, scanned):
    """The whole point. Page 2 had no text layer, so ingest dropped it; OCR reads it and the
    criterion it carries is inserted with an anchor a human can turn to."""
    seen = _capture(monkeypatch)
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)
    monkeypatch.setattr(tenders.ocr, "ocr_pdf_pages",
                        lambda data, pages: {2: "The bidder shall hold a valid PESO licence."})
    pages_extracted = _extractor(
        monkeypatch, {"The bidder shall hold a valid PESO licence.": "valid PESO licence"},
    )

    tenders._ocr_quietly("ws-1", "t-1", scanned)

    assert pages_extracted == [2], "only the recovered page may cost a model call"
    assert [c["verbatim_text"] for c in seen["criteria"]] == ["valid PESO licence"]
    assert seen["criteria"][0]["anchor_page"] == 2
    assert seen["criteria"][0]["anchor_document"] == "nit.pdf"
    assert seen["stamped"] == [("ws-1", "t-1", 1)]


def test_the_already_legible_page_is_not_re_extracted(monkeypatch, scanned):
    """Page 1 was extracted during ingest. Re-reading it would double both the spend and the
    criteria — the tender would grow a second copy of every requirement on every upload."""
    _capture(monkeypatch)
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)
    monkeypatch.setattr(tenders.ocr, "ocr_pdf_pages", lambda data, pages: {2: "x" * 50})
    pages_extracted = _extractor(monkeypatch, {})

    tenders._ocr_quietly("ws-1", "t-1", scanned)

    assert 1 not in pages_extracted


def test_a_page_ocr_could_not_read_stays_exactly_as_illegible(monkeypatch, scanned):
    """Tesseract returning three characters of noise is not a recovered page. It must not be
    counted, extracted from, or presented as content."""
    seen = _capture(monkeypatch)
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)
    monkeypatch.setattr(tenders.ocr, "ocr_pdf_pages", lambda data, pages: {2: "\\|-"})
    pages_extracted = _extractor(monkeypatch, {})

    tenders._ocr_quietly("ws-1", "t-1", scanned)

    assert pages_extracted == [], "sub-floor OCR output must not reach the extractor"
    assert seen["criteria"] == []
    assert seen["stamped"] == [("ws-1", "t-1", 0)]


def test_unavailable_ocr_changes_nothing_at_all(monkeypatch, scanned):
    """Linux without the toolchain, or a stripped image. "No OCR here" is a deployment fact,
    and the tender must look precisely as it did before this feature existed — including an
    unstamped row, because no read happened."""
    seen = _capture(monkeypatch)
    monkeypatch.setattr(tenders.ocr, "available", lambda: False)
    monkeypatch.setattr(tenders.ocr, "ocr_pdf_pages",
                        lambda *a: pytest.fail("must not OCR when unavailable"))

    tenders._ocr_quietly("ws-1", "t-1", scanned)

    assert seen == {"criteria": [], "unmapped": [], "stamped": [], "title": [], "meta": []}


# ── the stamp means what it says ───────────────────────────────────────────────────────────

def test_a_pass_that_recovered_nothing_is_still_stamped(monkeypatch, scanned):
    """"We read the scans and none of them were legible" is a real answer. A NULL stamp would
    make it permanently indistinguishable from "no OCR ever ran here"."""
    seen = _capture(monkeypatch)
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)
    monkeypatch.setattr(tenders.ocr, "ocr_pdf_pages", lambda data, pages: {})

    tenders._ocr_quietly("ws-1", "t-1", scanned)

    assert seen["stamped"] == [("ws-1", "t-1", 0)]


def test_a_pass_that_raised_is_not_stamped(monkeypatch, scanned):
    """A read that blew up did not happen, so NULL is the true value. A try/finally around the
    stamp would break exactly this, which is why the stamp sits inside the try."""
    seen = _capture(monkeypatch)
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("pdftoppm segfaulted")

    monkeypatch.setattr(tenders.ocr, "ocr_pdf_pages", boom)

    tenders._ocr_quietly("ws-1", "t-1", scanned)  # must not raise

    assert seen["stamped"] == [], "a pass that failed must not be recorded as a pass that ran"


def test_a_failure_inside_the_pass_never_raises(monkeypatch, scanned, caplog):
    """The upload returned 200 minutes ago. There is nowhere for this to surface except a log
    line, and an exception escaping a BackgroundTask is a 500 nobody is listening for."""
    seen = _capture(monkeypatch)
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)
    monkeypatch.setattr(tenders.ocr, "ocr_pdf_pages",
                        lambda d, p: {2: "The bidder shall hold a valid PESO licence."})
    _extractor(monkeypatch,
               {"The bidder shall hold a valid PESO licence.": "valid PESO licence"})
    monkeypatch.setattr(tenders.db, "insert_criteria",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("postgrest down")))

    with caplog.at_level("ERROR"):
        tenders._ocr_quietly("ws-1", "t-1", scanned)

    assert any("background OCR failed" in r.getMessage() for r in caplog.records)
    assert seen["stamped"] == [], "a write that failed mid-pass must leave the row unstamped"


# ── naming a tender whose cover page was a scan ────────────────────────────────────────────

def test_a_placeholder_title_is_replaced_from_the_recovered_cover_page(monkeypatch):
    """The failure this closes: page one is a scan, so `display_title` has no title, no number
    and no authority, and every screen says "Untitled tender" forever."""
    from app import ingest

    monkeypatch.setattr(ingest, "parse_pdf_pages", lambda data: [(1, "")])
    seen = _capture(monkeypatch, title=tenders.PLACEHOLDER_TITLE)
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)
    monkeypatch.setattr(
        tenders.ocr, "ocr_pdf_pages",
        lambda data, pages: {1: "Tender No. MAHA/DMA/2026/0917\nOffice of the Collector"},
    )
    _extractor(monkeypatch, {})

    tenders._ocr_quietly("ws-1", "t-1", [("scan.pdf", _pdf("a"))])

    assert seen["title"] == ["MAHA/DMA/2026/0917 · Office of the Collector"]
    assert seen["meta"] == [("MAHA/DMA/2026/0917", "Office of the Collector")]


def test_a_tender_that_already_has_a_name_is_never_renamed(monkeypatch, scanned):
    """A parsed title, or a filename a human chose, must never be replaced by a backfill —
    and a placeholder is only produced when the document stated no title, no number AND no
    authority, so a named tender has facts here that noisier OCR text could overwrite."""
    seen = _capture(monkeypatch, title="Supply of Steel Wire Rope to Oil India")
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)
    monkeypatch.setattr(
        tenders.ocr, "ocr_pdf_pages",
        lambda data, pages: {2: "Tender No. GARBLED/0OO1\nDepartment of Nonsense"},
    )
    _extractor(monkeypatch, {})

    tenders._ocr_quietly("ws-1", "t-1", scanned)

    assert seen["title"] == [], "a real title must survive the OCR pass"
    assert seen["meta"] == [], "and so must the identity it was derived from"


# ── the budget ─────────────────────────────────────────────────────────────────────────────

def test_the_package_budget_is_shared_across_documents_and_announced(monkeypatch, caplog):
    """`ocr_pdf_pages` caps each CALL at MAX_PAGES, so a package of scanned annexures would fan
    out to N times the cap — and every recovered page is a model call. One budget for the
    package, and a truncation that says so rather than looking complete."""
    from app import ingest

    monkeypatch.setattr(ingest, "parse_pdf_pages", lambda data: [(1, ""), (2, ""), (3, "")])
    monkeypatch.setattr(tenders.ocr, "MAX_PAGES", 4)
    monkeypatch.setattr(tenders.ocr, "available", lambda: True)
    _capture(monkeypatch)
    _extractor(monkeypatch, {})

    asked: list[list[int]] = []
    monkeypatch.setattr(tenders.ocr, "ocr_pdf_pages",
                        lambda data, pages: asked.append(list(pages)) or {})

    docs = [("a.pdf", _pdf("x", "x", "x")), ("b.pdf", _pdf("x", "x", "x"))]
    with caplog.at_level("WARNING"):
        tenders._ocr_quietly("ws-1", "t-1", docs)

    assert asked == [[1, 2, 3], [1]], "the second document gets what is left, not a fresh cap"
    assert any("budget exhausted" in r.getMessage() for r in caplog.records)


# ── the wiring (the four above would all pass with the route left unconnected) ─────────────

def test_the_ingest_ROUTE_actually_runs_the_ocr_pass_after_responding(monkeypatch):
    """When this pattern was built for schedule extraction, every unit test passed with the
    route completely unwired; only a route-level test caught it. Real request, real
    BackgroundTasks, and the pass runs after the 200 rather than inside it."""
    from fastapi.testclient import TestClient

    from app.auth import AuthedUser, get_current_user
    from app.main import create_app

    ran: list[tuple] = []
    monkeypatch.setattr(tenders, "_process_ingest",
                        lambda ws, docs, name, pursuit: {"tender_id": "t-9", "pages": 1})
    monkeypatch.setattr(tenders, "_extract_quietly", lambda ws, t: None)
    monkeypatch.setattr(tenders, "_ocr_quietly",
                        lambda ws, t, docs: ran.append((ws, t, docs)))

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws-9", role="admin",
    )
    with TestClient(app) as client:
        r = client.post("/api/tenders/ingest", files={"file": ("nit.pdf", b"%PDF-1.4")})

    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(ran) == 1, "ingest must queue the OCR pass"
    assert ran[0][:2] == ("ws-9", "t-9")
    # The bytes have to travel with the task: nothing in this engine persists an uploaded
    # file, so there is no later moment at which these pages could be fetched again.
    assert ran[0][2] == [("nit.pdf", b"%PDF-1.4")]


def test_the_schedule_read_is_queued_BEFORE_the_ocr_pass(monkeypatch):
    """BackgroundTasks run in order, and the OCR pass can take minutes. Ahead of the schedule
    read it would park that read behind itself for no gain — OCR-recovered criteria do not
    become line items either way, because `replace_line_items` deletes the schedule before
    writing and would discard the parameters the schedule read just paid a model for."""
    order: list[str] = []

    class FakeBackground:
        def add_task(self, fn, *args, **kwargs):
            order.append(fn.__name__)

    background = FakeBackground()
    tenders._schedule_extraction(background, "ws-1", "t-1")
    tenders._schedule_ocr(background, "ws-1", "t-1", [])

    assert order == ["_extract_quietly", "_ocr_quietly"]


def test_readiness_reports_what_ocr_recovered(monkeypatch):
    """The ingest response was sent before the pass started and page text is never persisted,
    so the tender row is the only record. Echoed by the handler that already loads that row."""
    from fastapi.testclient import TestClient

    from app import db, readiness_routes
    from app.auth import AuthedUser, get_current_user
    from app.main import create_app

    monkeypatch.setattr(db, "get_tender", lambda t, w: {
        "id": t, "ocr_completed_at": "2026-09-15T10:00:00+00:00", "ocr_pages_recovered": 77,
    })
    monkeypatch.setattr(readiness_routes, "_readiness_payload", lambda w, t: {"summary": {}})

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: AuthedUser(
        user_id="u1", workspace_id="ws-1", role="admin",
    )
    with TestClient(app) as client:
        r = client.get("/api/tenders/t-1/readiness")

    assert r.status_code == 200
    assert r.json()["data"]["ocr_pages_recovered"] == 77
    assert r.json()["data"]["ocr_completed_at"] == "2026-09-15T10:00:00+00:00"
