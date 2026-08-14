"""BOQ table recovery — and the cases where it must decline to guess.

A BOQ misread by one column produces line items that look entirely plausible and describe the
wrong goods. Every verdict downstream inherits that silently, so roughly half of this file is
about the parser refusing rather than the parser working.
"""

from __future__ import annotations

import pytest

from app.deterministic.boq import BoqRow, find_header, rows_to_line_items

HEADER = ("Sl. No.", "Item Description", "Qty", "UOM", "Unit Rate")
ROWS = [
    ("Tender for supply of steel wire ropes",),
    ("Ministry of Testing", None, None),
    (),
    HEADER,
    ("1", "Steel wire rope 20mm 6x36 IWRC 1960 N/mm2 as per IS 2266", "5,000", "m", "450.00"),
    ("2", "Steel wire rope 24mm 6x19 FC galvanised", "1200", "m", "610.50"),
    (None, None, None, None, None),
    ("", "Total", "6200", "m", ""),
]


def parse(rows=None, document="BOQ.xlsx · Schedule-A", sheet=1):
    return rows_to_line_items(document, sheet, rows if rows is not None else ROWS)


# ── the happy path ───────────────────────────────────────────────────────────────────

def test_a_real_boq_yields_one_line_item_per_schedule_row():
    items = parse()
    assert len(items) == 2
    assert items[0].description.startswith("Steel wire rope 20mm")
    assert items[1].item_ref == "2"


def test_every_line_item_anchors_to_the_worksheet_row_a_human_would_scroll_to():
    """Cite-or-flag for a table. 'BOQ.xlsx · Schedule-A · row 5' has to actually be row 5."""
    items = parse()
    assert items[0].row_number == 5
    assert items[1].row_number == 6
    assert items[0].document == "BOQ.xlsx · Schedule-A"


def test_quantity_and_unit_are_read_including_thousands_separators():
    items = parse()
    assert items[0].quantity == 5000.0
    assert items[0].uom == "m"


def test_blank_and_total_rows_are_not_line_items():
    """A totals row has a description and a quantity and is not a thing anyone supplies."""
    assert all("Total" not in item.description for item in parse())


@pytest.mark.parametrize("label", [
    "Total", "TOTAL", "Sub Total", "Sub-total", "Grand Total", "Carried forward",
])
def test_every_spelling_of_a_totals_row_is_skipped(label):
    rows = [HEADER, ("1", "Wire rope 20mm", "10", "m", "1"), ("", label, "10", "m", "")]
    assert [i.description for i in parse(rows)] == ["Wire rope 20mm"]


# ── refusing to guess ────────────────────────────────────────────────────────────────

def test_no_header_means_no_line_items_rather_than_a_guess():
    """The decisive one. Inventing a description column produces confident nonsense."""
    rows = [("1", "some value", "3"), ("2", "another", "4")]
    assert parse(rows) == []
    assert find_header(rows) is None


def test_a_table_without_a_description_column_yields_nothing():
    """description is NOT NULL downstream, and a line item without one describes no goods."""
    rows = [("Sl. No.", "Qty", "UOM"), ("1", "10", "m")]
    assert parse(rows) == []


def test_one_lone_matching_word_is_a_coincidence_not_a_header():
    rows = [("Description",), ("Some prose about the tender",)]
    assert parse(rows) == []


def test_a_header_buried_below_a_long_title_block_is_still_found():
    rows = [("title",)] * 8 + [HEADER, ("1", "Wire rope 20mm", "10", "m", "1")]
    assert [i.description for i in parse(rows)] == ["Wire rope 20mm"]


def test_a_header_beyond_the_scan_window_is_not_found():
    """Named ceiling, pinned so a future widening is a deliberate act."""
    rows = [("title",)] * 13 + [HEADER, ("1", "Wire rope 20mm", "10", "m", "1")]
    assert parse(rows) == []


def test_an_empty_sheet_yields_nothing():
    assert parse([]) == []


# ── the column-mapping traps ─────────────────────────────────────────────────────────

def test_unit_rate_is_never_read_as_a_unit_of_measurement():
    """'Unit Rate' contains 'unit'. Without the commercial-word guard a rupee figure lands in
    `uom` and the line item claims to be measured in money."""
    rows = [("Sl", "Description", "Unit Rate"), ("1", "Wire rope 20mm", "450.00")]
    items = parse(rows)
    assert items[0].uom is None


@pytest.mark.parametrize("header", ["Unit Price", "Amount", "Total Value", "GST Rate", "Cost"])
def test_commercial_columns_are_ignored_entirely(header):
    rows = [("Description", "Qty", header), ("Wire rope", "10", "999")]
    assert find_header(rows)[1].keys() == {"description", "quantity"}


def test_item_description_binds_to_description_not_to_item():
    """Longest token wins. Otherwise 'Item Description' matches 'item' and the description
    column is read as a reference number."""
    _, columns = find_header([("Item Description", "Qty")])
    assert columns["description"] == 0
    assert "item_ref" not in columns


def test_the_first_column_wins_a_repeated_role():
    """A sheet with a Qty per consignee must not silently rebind to the later one."""
    rows = [("Description", "Qty", "Qty"), ("Wire rope", "10", "999")]
    assert parse(rows)[0].quantity == 10.0


def test_a_row_shorter_than_the_header_does_not_raise():
    """Real sheets have ragged rows. An IndexError here would fail the whole upload."""
    rows = [HEADER, ("1", "Wire rope 20mm")]
    items = parse(rows)
    assert items[0].quantity is None and items[0].uom is None


def test_an_unreadable_quantity_is_absent_not_zero():
    """Zero is a real order size. Coercing 'As required' to 0 invents a fact."""
    rows = [HEADER, ("1", "Wire rope 20mm", "As required", "m", "1")]
    assert parse(rows)[0].quantity is None


def test_an_unrecognised_header_word_is_simply_not_mapped():
    rows = [("Description", "Qty", "Consignee"), ("Wire rope", "10", "Depot 4")]
    assert find_header(rows)[1].keys() == {"description", "quantity"}


# ── schedules ────────────────────────────────────────────────────────────────────────

def test_a_schedule_name_written_once_carries_down_its_block():
    """BOQs name a schedule on its first row and leave the rest blank. Without the carry,
    every line but the first loses which schedule it belongs to."""
    rows = [
        ("Schedule", "Description", "Qty"),
        ("Schedule-A", "Wire rope 20mm", "10"),
        ("", "Wire rope 24mm", "20"),
        ("Schedule-B", "Welding wire 1.2mm", "30"),
    ]
    assert [i.schedule_ref for i in parse(rows)] == ["Schedule-A", "Schedule-A", "Schedule-B"]


def test_a_sheet_with_no_schedule_column_leaves_the_reference_empty():
    assert all(item.schedule_ref == "" for item in parse())


def test_the_result_is_immutable():
    """A line item is evidence about a document. Nothing downstream may edit it in place."""
    with pytest.raises(AttributeError):
        parse()[0].description = "something else"  # type: ignore[misc]


def test_boq_row_carries_its_sheet_so_a_multi_sheet_package_stays_distinguishable():
    assert parse(sheet=3)[0].sheet_index == 3
    assert isinstance(parse()[0], BoqRow)
