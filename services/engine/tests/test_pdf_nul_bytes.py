"""NUL bytes must never leave the PDF parser.

Found 2026-09-09 while loading a customer's own documents into the knowledge base: four of
eight real UML PDFs made PostgREST answer

    22P05  "\\u0000 cannot be converted to text"

which the engine surfaces to the user as a 502 DB_ERROR on a perfectly ordinary upload.
Postgres `text` cannot hold a NUL, and `pypdf.extract_text()` emits them from PDFs with broken
font encodings — common in the scanned-and-recombined packages this product exists to read.

Stripped in `parse_pdf_pages` rather than at each writer, because that is the one place every
consumer routes through: the knowledge base (`knowledge.extract_text`), the tender ingest
(`matrix_unmapped`, criteria verbatim text) and past-bid upload all take PDF text from here.
Fixing it at one writer would leave the others failing the same way.
"""

from __future__ import annotations

from app import ingest


class _Page:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


def _reader_of(*texts: str):
    class _Reader:
        pages = [_Page(t) for t in texts]

    return lambda _buf: _Reader()


def test_a_nul_byte_never_leaves_the_pdf_parser(monkeypatch):
    monkeypatch.setattr(
        ingest, "PdfReader", _reader_of("BUREAU OF\x00 INDIAN STANDARDS\x00"),
    )
    pages = ingest.parse_pdf_pages(b"%PDF-1.4 fake")

    assert "\x00" not in pages[0][1], "Postgres text cannot store a NUL; strip it at the source"
    assert pages[0][1] == "BUREAU OF INDIAN STANDARDS", (
        "the NUL is removed, not the characters around it"
    )


def test_a_page_of_only_nuls_reads_as_illegible_not_as_content(monkeypatch):
    """It must land in `illegible_pages` like any other unreadable page, not as a blank
    document that looks ingested."""
    monkeypatch.setattr(ingest, "PdfReader", _reader_of("\x00\x00\x00"))
    pages = ingest.parse_pdf_pages(b"%PDF-1.4 fake")
    assert pages[0][1] == ""


def test_nuls_among_real_text_do_not_discard_the_page(monkeypatch):
    """The failure to avoid in the other direction: dropping a page because it contains a
    NUL would silently lose a licence we can otherwise read."""
    monkeypatch.setattr(ingest, "PdfReader", _reader_of("Usha Martin Ltd\x00, Ranchi 835103"))
    pages = ingest.parse_pdf_pages(b"%PDF-1.4 fake")
    assert pages[0][1] == "Usha Martin Ltd, Ranchi 835103"


def test_other_control_characters_that_postgres_accepts_are_preserved(monkeypatch):
    """Only the NUL is rejected by Postgres. Stripping tabs or newlines would damage the
    layout the page anchors and sentence splitting depend on."""
    monkeypatch.setattr(ingest, "PdfReader", _reader_of("Line one\nLine\ttwo\x00"))
    pages = ingest.parse_pdf_pages(b"%PDF-1.4 fake")
    assert pages[0][1] == "Line one\nLine\ttwo"
