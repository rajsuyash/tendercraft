"""Archive intake (F14). A ZIP dropped by an officer is untrusted input.

The officer is not the attacker here — a bidder is. The archive an officer drops came from a
portal, and its contents were uploaded by the firms being evaluated. Traversal entries, lying
size headers and absolute paths are all things a hostile submission can contain, and none of
them produce a visible symptom if we simply read them.

The other half of these tests is about SILENCE: an officer who drops 600 files and sees 500
rows has no way to learn which hundred bids are missing, and a missing bid produces no error
anywhere downstream. So every bound raises rather than truncating.
"""

import io
import zipfile

import pytest

from evaluate.envelope import ApiError
from evaluate.ingest import (
    is_archive,
    parse_pages,
    rejected_entries,
    sha256_of,
    unpack_archive,
)

BIG = 10_000_000
MANY = 1_000


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ── detection ──────────────────────────────────────────────────────────────────
def test_detects_an_archive_by_magic_bytes_not_only_by_extension():
    """Portals rename downloads. `bids.dat` holding a ZIP is still a ZIP."""
    data = _zip({"a.pdf": b"x"})
    assert is_archive("bids.dat", data) is True
    assert is_archive("bids.zip", b"not a zip") is True   # extension is also honoured
    assert is_archive("bid.pdf", b"%PDF-1.7") is False


# ── the hostile cases ──────────────────────────────────────────────────────────
def test_traversal_entries_are_refused_and_reported():
    data = _zip({"../../etc/passwd": b"x", "ok.pdf": b"%PDF-"})
    out = unpack_archive(data, max_files=MANY, max_bytes=BIG)
    assert [n for n, _ in out] == ["ok.pdf"]
    # Refused, but never silently: the officer is told what we would not read.
    assert rejected_entries(data) == ["passwd (path removed)"]


def test_a_refused_entry_name_is_sanitised_before_it_is_ever_echoed():
    """Regression, and it was a live one.

    These names are authored by the BIDDER and travel into an audit payload, an API response
    and a screen. Echoed verbatim, `../../etc/passwd` tripped Supabase's WAF and 403'd the
    whole request — so one crafted entry in one bid failed the officer's entire upload with an
    opaque database error. A bidder must not be able to do that.
    """
    for hostile in ["../../etc/passwd", "..\\..\\windows\\system32\\config\\sam", "/etc/shadow"]:
        got = rejected_entries(_zip({hostile: b"x"}))
        assert got, f"{hostile} should have been refused and reported"
        assert ".." not in got[0]
        assert "/" not in got[0] and "\\" not in got[0]


def test_sanitising_never_produces_an_empty_name():
    """A name that is nothing but traversal tokens still has to render as something."""
    got = rejected_entries(_zip({"../..": b"x"}))
    assert got == ["(unnamed) (path removed)"]


def test_absolute_paths_are_refused():
    data = _zip({"/tmp/evil.pdf": b"x", "ok.pdf": b"%PDF-"})
    assert [n for n, _ in unpack_archive(data, max_files=MANY, max_bytes=BIG)] == ["ok.pdf"]


def test_macos_resource_forks_are_refused_without_being_called_a_breach():
    """Every ZIP made on a Mac carries these. They are noise, not an attack."""
    data = _zip({"__MACOSX/._a.pdf": b"x", "a.pdf": b"%PDF-"})
    assert [n for n, _ in unpack_archive(data, max_files=MANY, max_bytes=BIG)] == ["a.pdf"]


def test_nested_directories_are_flattened_to_their_filename():
    """Portal downloads arrive foldered by bidder; the folder name is not evidence of who
    submitted the file, so it is dropped and attribution reads the document instead."""
    data = _zip({"Bidder A/technical.pdf": b"%PDF-"})
    assert [n for n, _ in unpack_archive(data, max_files=MANY, max_bytes=BIG)] == \
        ["technical.pdf"]


def test_too_many_entries_raises_rather_than_truncating():
    data = _zip({f"f{i}.pdf": b"x" for i in range(12)})
    with pytest.raises(ApiError) as exc:
        unpack_archive(data, max_files=10, max_bytes=BIG)
    assert exc.value.code == "ARCHIVE_TOO_LARGE"
    # The limit is named, so the officer knows what to do about it.
    assert "10" in exc.value.message


def test_oversized_expansion_raises_rather_than_truncating():
    data = _zip({"big.pdf": b"x" * 5000})
    with pytest.raises(ApiError) as exc:
        unpack_archive(data, max_files=MANY, max_bytes=1000)
    assert exc.value.code == "ARCHIVE_TOO_LARGE"


def test_a_corrupt_archive_is_a_named_error_not_a_crash():
    with pytest.raises(ApiError) as exc:
        unpack_archive(b"PK\x03\x04 garbage", max_files=MANY, max_bytes=BIG)
    assert exc.value.code == "BAD_ARCHIVE"


def test_rejected_entries_on_a_corrupt_archive_is_empty_not_an_exception():
    assert rejected_entries(b"not a zip at all") == []


# ── idempotency ────────────────────────────────────────────────────────────────
def test_identical_bytes_hash_identically_regardless_of_filename():
    """The idempotency key behind F14-AC3. Portal downloads arrive as bid_1.pdf twelve times
    over, so the filename cannot be the identity."""
    assert sha256_of(b"%PDF-same") == sha256_of(b"%PDF-same")
    assert sha256_of(b"%PDF-a") != sha256_of(b"%PDF-b")


# ── format dispatch ────────────────────────────────────────────────────────────
def test_spreadsheet_bids_become_pages_with_cell_anchors():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Price Schedule"
    ws["A1"] = "Item"
    ws["B1"] = "Amount"
    ws["A2"] = "Rack Server"
    ws["B2"] = 5820000
    buf = io.BytesIO()
    wb.save(buf)

    pages = parse_pages("schedule.xlsx", buf.getvalue())
    assert len(pages) == 1
    body = pages[0][1]
    assert "SHEET: Price Schedule" in body
    assert "B2=5820000" in body      # the cell reference IS the anchor


def test_csv_bids_are_read():
    pages = parse_pages("items.csv", b"Item,Amount\nRack Server,5820000\n")
    assert "Rack Server | 5820000" in pages[0][1]


def test_an_unsupported_format_is_a_named_refusal_not_an_empty_document():
    """An empty parse looks exactly like a bid with nothing in it — which would read as a
    non-compliant bidder rather than a file we cannot open."""
    with pytest.raises(ApiError) as exc:
        parse_pages("scan.tiff", b"II*\x00")
    assert exc.value.code == "UNSUPPORTED_FORMAT"
