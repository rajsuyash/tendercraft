"""The OCR fallback's bounds and its refusal to fail loudly.

Every test here is about what happens when OCR is NOT available or does not work, because that
is the common case: the engine image is Linux and the macOS Vision adapter cannot run there.
A page that could not be OCR'd must look exactly as illegible as it does today — never an
exception, never an empty string presented as content, and never text paired with the wrong
page number.

The recognition quality itself is not unit-testable without shipping a fixture image; it is
proven against real customer scans in the M1 demo instead.
"""

from __future__ import annotations

import subprocess

from app import ocr


def test_no_pages_requested_does_no_work(monkeypatch):
    called = []
    monkeypatch.setattr(ocr.subprocess, "run", lambda *a, **k: called.append(a))
    assert ocr.ocr_pdf_pages(b"%PDF", []) == {}
    assert called == []


def test_unavailable_returns_nothing_rather_than_raising(monkeypatch):
    """Linux, or any machine without the toolchain. 'No OCR here' is a deployment fact."""
    monkeypatch.setattr(ocr, "available", lambda: False)
    assert ocr.ocr_pdf_pages(b"%PDF", [1, 2, 3]) == {}


def test_available_is_false_without_pdftoppm(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    assert ocr.available() is False


def test_the_page_cap_is_enforced_and_announced(monkeypatch, caplog):
    """A partial OCR that looks complete is the capped-sweep failure again."""
    monkeypatch.setattr(ocr, "MAX_PAGES", 2)
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "_binary", lambda: None)  # stop before doing work

    with caplog.at_level("WARNING"):
        ocr.ocr_pdf_pages(b"%PDF", [1, 2, 3, 4, 5])

    assert any("capped at 2" in r.getMessage() for r in caplog.records), (
        "the cap must be announced; a silent truncation reads as a complete OCR"
    )


def test_a_render_failure_drops_that_page_only(monkeypatch, tmp_path):
    """One unrenderable page must not fail a 57-page document."""
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "_binary", lambda: tmp_path / "fake-binary")

    def _run(argv, **kwargs):
        if argv[0] == "pdftoppm":
            raise subprocess.CalledProcessError(1, argv)
        raise AssertionError("adapter must not run when nothing rendered")

    monkeypatch.setattr(ocr.subprocess, "run", _run)
    assert ocr.ocr_pdf_pages(b"%PDF", [1, 2]) == {}


def test_a_protocol_mismatch_discards_everything(monkeypatch, tmp_path):
    """Text paired with the WRONG page is worse than a page nobody could read: a citation
    would then anchor to a page that does not contain the sentence."""
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "_binary", lambda: tmp_path / "fake-binary")

    def _run(argv, **kwargs):
        if argv[0] == "pdftoppm":
            # Simulate a successful render by creating the file the module globs for.
            stem = argv[-1]
            open(f"{stem}-1.png", "wb").close()
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        # Two pages rendered, ONE block returned.
        return subprocess.CompletedProcess(argv, 0, "only one block", "")

    monkeypatch.setattr(ocr.subprocess, "run", _run)
    assert ocr.ocr_pdf_pages(b"%PDF", [1, 2]) == {}


def test_text_is_paired_with_its_own_page_and_nuls_are_stripped(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "_binary", lambda: tmp_path / "fake-binary")

    def _run(argv, **kwargs):
        if argv[0] == "pdftoppm":
            open(f"{argv[-1]}-1.png", "wb").close()
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        out = ocr._PAGE_BREAK.join(["page four\x00 text", "   ", "page nine text"])
        return subprocess.CompletedProcess(argv, 0, out, "")

    monkeypatch.setattr(ocr.subprocess, "run", _run)
    result = ocr.ocr_pdf_pages(b"%PDF", [4, 7, 9])

    assert result == {4: "page four text", 9: "page nine text"}, (
        "a blank block is an unreadable page, not an empty document"
    )
    assert "\x00" not in result[4]


def test_the_temp_directory_is_always_removed(monkeypatch, tmp_path):
    """A worker OCR-ing every upload would otherwise fill the disk with rendered PNGs."""
    seen: list[str] = []
    real_mkdtemp = ocr.tempfile.mkdtemp

    def _mkdtemp(**kwargs):
        d = real_mkdtemp(**kwargs)
        seen.append(d)
        return d

    monkeypatch.setattr(ocr.tempfile, "mkdtemp", _mkdtemp)
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "_binary", lambda: tmp_path / "fake-binary")
    monkeypatch.setattr(
        ocr.subprocess, "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "x")),
    )

    ocr.ocr_pdf_pages(b"%PDF", [1])

    import os
    assert seen and not os.path.exists(seen[0])
