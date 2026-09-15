"""The OCR fallback's bounds and its refusal to fail loudly.

Every test here is about what happens when OCR is NOT available or does not work. A page that
could not be OCR'd must look exactly as illegible as it does today — never an exception, never
an empty string presented as content, and never text paired with the wrong page number.

The recognition quality itself is not unit-testable without shipping a fixture image; it is
proven against the real customer corpus in docs/ocr-measurement.md instead.
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
    # Fail every render so nothing downstream needs a real pdftoppm/tesseract.
    monkeypatch.setattr(
        ocr.subprocess, "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "x")),
    )

    with caplog.at_level("WARNING"):
        ocr.ocr_pdf_pages(b"%PDF", [1, 2, 3, 4, 5])

    assert any("capped at 2" in r.getMessage() for r in caplog.records), (
        "the cap must be announced; a silent truncation reads as a complete OCR"
    )


def test_a_render_failure_drops_that_page_only(monkeypatch, tmp_path):
    """One unrenderable page must not fail a 57-page document."""
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr.tempfile, "mkdtemp", lambda **kw: str(tmp_path))

    def _run(argv, **kwargs):
        if argv[0] == "pdftoppm":
            page = argv[argv.index("-f") + 1]
            if page == "2":
                raise subprocess.CalledProcessError(1, argv)
            open(f"{argv[-1]}-1.png", "wb").close()
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        return subprocess.CompletedProcess(argv, 0, "page one recognised text here", "")

    monkeypatch.setattr(ocr.subprocess, "run", _run)
    assert ocr.ocr_pdf_pages(b"%PDF", [1, 2]) == {1: "page one recognised text here"}


def test_text_is_paired_with_its_own_page_and_nuls_are_stripped(monkeypatch, tmp_path):
    """Per-page reads mean there is no shared protocol to desynchronise: page 7's render
    simply fails to render an image at all, and the loop moves on."""
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr.tempfile, "mkdtemp", lambda **kw: str(tmp_path))

    def _run(argv, **kwargs):
        if argv[0] == "pdftoppm":
            page = argv[argv.index("-f") + 1]
            if page == "7":
                raise subprocess.CalledProcessError(1, argv)  # unrenderable page
            open(f"{argv[-1]}-1.png", "wb").close()
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        page = str(argv[1])
        if "p9-" in page:
            return subprocess.CompletedProcess(argv, 0, "   ", "")  # blank recognition
        return subprocess.CompletedProcess(argv, 0, "page four\x00 text", "")

    monkeypatch.setattr(ocr.subprocess, "run", _run)
    result = ocr.ocr_pdf_pages(b"%PDF", [4, 7, 9])

    assert result == {4: "page four text"}, (
        "page 7 never rendered and page 9's blank recognition is an unreadable page, "
        "not an empty document"
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
    monkeypatch.setattr(
        ocr.subprocess, "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "x")),
    )

    ocr.ocr_pdf_pages(b"%PDF", [1])

    import os
    assert seen and not os.path.exists(seen[0])


class TestTheLinuxAdapter:
    """`app/ocr.py` shipped macOS-only and was wired to nothing, so production read no scans
    at all. The seam it already exposes — `available()` and `ocr_pdf_pages` — is unchanged;
    only what sits behind it is new. Tesseract was chosen on measurement, not preference:
    docs/ocr-measurement.md carries the rate, the timings and the samples a human read.
    """

    def test_tesseract_makes_ocr_available_without_swift(self, monkeypatch):
        from app import ocr

        monkeypatch.setattr(
            ocr.shutil, "which",
            lambda name: f"/usr/bin/{name}" if name in ("pdftoppm", "tesseract") else None,
        )
        assert ocr.available() is True, "poppler + tesseract on Linux is enough"

    def test_no_tesseract_means_unavailable_not_an_error(self, monkeypatch):
        # "No OCR here" is an ordinary deployment fact. Callers check; they never catch.
        from app import ocr

        monkeypatch.setattr(
            ocr.shutil, "which",
            lambda name: "/usr/bin/pdftoppm" if name == "pdftoppm" else None,
        )
        assert ocr.available() is False

    def test_each_page_is_read_independently(self, monkeypatch, tmp_path):
        """One subprocess per page, so a single unreadable page cannot desynchronise the rest.

        The macOS adapter batched pages and split the output on a record separator, then
        discarded the WHOLE batch when the block count disagreed — correct, but it meant one
        bad page cost sixty. Per-page removes the protocol, so there is nothing to disagree.
        """
        from app import ocr

        def fake_run(argv, **kw):
            if argv[0] == "pdftoppm":
                page = argv[argv.index("-f") + 1]
                (tmp_path / f"p{page}-1.png").write_bytes(b"png")
                return subprocess.CompletedProcess(argv, 0, b"", b"")
            if "p2-" in argv[1]:  # page 2's image cannot be read
                raise subprocess.CalledProcessError(1, argv)
            return subprocess.CompletedProcess(
                argv, 0, "RECOVERED TEXT WELL OVER THE TWENTY CHARACTER FLOOR", ""
            )

        monkeypatch.setattr(ocr.tempfile, "mkdtemp", lambda **kw: str(tmp_path))
        monkeypatch.setattr(ocr.subprocess, "run", fake_run)
        monkeypatch.setattr(ocr, "available", lambda: True)

        out = ocr.ocr_pdf_pages(b"%PDF-", [1, 2, 3])

        assert set(out) == {1, 3}, "page 2 failing must not take 1 and 3 with it"
        assert all("RECOVERED" in t for t in out.values())

    def test_a_page_that_reads_as_whitespace_is_not_returned(self, monkeypatch, tmp_path):
        # Recovering nothing is a real answer. An empty string would read downstream as
        # "read successfully, said nothing", which is a different and false claim.
        from app import ocr

        def fake_run(argv, **kw):
            if argv[0] == "pdftoppm":
                (tmp_path / "p1-1.png").write_bytes(b"png")
                return subprocess.CompletedProcess(argv, 0, b"", b"")
            return subprocess.CompletedProcess(argv, 0, "   \n  ", "")

        monkeypatch.setattr(ocr.tempfile, "mkdtemp", lambda **kw: str(tmp_path))
        monkeypatch.setattr(ocr.subprocess, "run", fake_run)
        monkeypatch.setattr(ocr, "available", lambda: True)

        assert ocr.ocr_pdf_pages(b"%PDF-", [1]) == {}
