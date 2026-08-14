"""Read a BOQ table into schedule line items — deterministically, or not at all.

Module H. A tender's schedule of items is a table, and until now it reached the product as one
page of joined text (`ingest.parse_spreadsheet_pages`), which is right for criteria extraction
and useless for "can we supply line 14". This module recovers the rows.

It is pure: it takes cell values and returns line items. The openpyxl read stays in
`app/ingest.py`, so `app/deterministic/` keeps its no-I/O, no-model contract and every branch
here is reachable from a plain list of tuples in a test.

THE RULE THAT MATTERS: no recognisable header, no line items. Not a best guess at which column
held the description — nothing, and a UI that asks the human to enter the schedule by hand. A
BOQ misread by one column produces line items that look perfectly plausible and describe the
wrong goods, and every downstream verdict inherits that quietly. An empty result is visible in a
way a wrong one is not.

Ceiling, named: a BOQ with no header row at all, or one split across merged cells, yields
nothing. That is the intended failure. # ponytail: if real GeM BOQs turn out to bury the header
under a merged title block, widen the scan window before loosening the match.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: How far down the sheet to look for a header. Tender BOQs carry a title block, an authority
#: name and sometimes a logo row; twelve rows clears every real one seen so far without letting
#: a stray word deep in the data masquerade as a header.
_HEADER_SCAN_ROWS = 12

#: A header needs a description column plus one more signal. One lone matching word is a
#: coincidence — "Description" appears in prose sheets that are not tables at all.
_MIN_HEADER_ROLES = 2

Cell = object
Row = Sequence[Cell]


@dataclass(frozen=True)
class BoqRow:
    """One schedule line, anchored to the cell it came from."""

    document: str          # "BOQ.xlsx · Schedule-A" — same label ingest gives a SourcePage
    sheet_index: int
    row_number: int        # 1-indexed worksheet row: what a human scrolls to
    description: str
    schedule_ref: str = ""
    item_ref: str = ""
    quantity: float | None = None
    uom: str | None = None


# Longest token wins, so "item description" resolves to description rather than to item_ref.
_ROLE_TOKENS: dict[str, tuple[str, ...]] = {
    "description": (
        "item description", "material description", "description of item", "description",
        "particulars", "specification", "specifications", "nomenclature", "material",
        "product", "item name",
    ),
    "item_ref": (
        "item no", "item code", "itemno", "itemcode", "sl no", "slno", "sr no", "srno",
        "s no", "sno", "item", "sl", "sr",
    ),
    "quantity": ("quantity", "qty", "nos"),
    "uom": ("unit of measurement", "uom", "unit", "units"),
    "schedule_ref": ("schedule", "lot", "group", "package"),
}

# Commercial columns are never read. Pricing is not this module's business — and without this,
# "Unit Rate" matches the `unit` token and a rupee figure lands in `uom`.
_COMMERCIAL = ("price", "rate", "amount", "value", "cost", "gst", "tax", "total")

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACE = re.compile(r"\s+")

# Separator is [\s\-_]* and not \s*: "Sub-total" is at least as common as "Sub Total" in a real
# BOQ, and a totals row that survives becomes a line item nobody can supply.
_TOTAL_ROW = re.compile(r"^(sub[\s\-_]*)?(grand[\s\-_]*)?total\b|^carried[\s\-_]+forward\b", re.I)


def _text(cell: Cell) -> str:
    if cell is None:
        return ""
    return str(cell).strip()


def _normalise(cell: Cell) -> str:
    folded = _PUNCT.sub(" ", _text(cell).lower())
    return _SPACE.sub(" ", folded).strip()


#: (token, role) longest-first — computed once so header detection is a single ordered scan.
_TOKENS_BY_LENGTH: tuple[tuple[str, str], ...] = tuple(
    sorted(
        ((token, role) for role, tokens in _ROLE_TOKENS.items() for token in tokens),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)


def _role_of(cell: Cell) -> str | None:
    """Which column is this, if any? None for a header we do not understand."""
    normalised = _normalise(cell)
    if not normalised:
        return None
    if any(word in normalised for word in _COMMERCIAL):
        return None
    for token, role in _TOKENS_BY_LENGTH:
        if normalised == token or normalised.startswith(token + " "):
            return role
    return None


def find_header(rows: Sequence[Row]) -> tuple[int, dict[str, int]] | None:
    """The header row index and its column map, or None when there is no table here."""
    for index, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        columns: dict[str, int] = {}
        for position, cell in enumerate(row):
            role = _role_of(cell)
            # First column wins a role: a sheet repeating "Qty" for a second consignee must
            # not silently rebind the quantity to the later one.
            if role is not None and role not in columns:
                columns[role] = position
        if "description" in columns and len(columns) >= _MIN_HEADER_ROLES:
            return index, columns
    return None


def _cell_at(row: Row, position: int | None) -> Cell:
    if position is None or position >= len(row):
        return None
    return row[position]


def _quantity(cell: Cell) -> float | None:
    """A quantity we cannot read is absent, not zero. Zero is a real order size."""
    raw = _text(cell).replace(",", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def rows_to_line_items(document: str, sheet_index: int, rows: Sequence[Row]) -> list[BoqRow]:
    """Every readable schedule line below the header. Empty when there is no header."""
    found = find_header(rows)
    if found is None:
        return []
    header_index, columns = found

    items: list[BoqRow] = []
    carried_schedule = ""
    for offset, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        description = _text(_cell_at(row, columns.get("description")))
        # A schedule name is often written once, on the first row of its block.
        schedule = _text(_cell_at(row, columns.get("schedule_ref")))
        if schedule:
            carried_schedule = schedule
        if not description or _TOTAL_ROW.match(description):
            continue
        items.append(
            BoqRow(
                document=document,
                sheet_index=sheet_index,
                row_number=offset,
                description=description,
                schedule_ref=carried_schedule,
                item_ref=_text(_cell_at(row, columns.get("item_ref"))),
                quantity=_quantity(_cell_at(row, columns.get("quantity"))),
                uom=_text(_cell_at(row, columns.get("uom"))) or None,
            )
        )
    return items
