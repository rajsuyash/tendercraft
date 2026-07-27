"""Reading a bid total off a price schedule. No model in this path — ever.

A quoted price decides who wins. It is not a field a model may author or guess at, so this is
arithmetic over text: find figures that are explicitly LABELLED as the total, and return one
only when the document is unambiguous about it.

Returning None is the designed outcome whenever there is doubt. The officer then enters the
figure at financial opening, which is a keystroke. A wrong figure silently reorders the
ranking, and the audit trail will say a machine read it correctly.

Indian conventions matter here and are the reason this is not a one-line regex:
  ₹1,20,00,000  is 1.2 crore, not 120 million — the grouping is 2-2-3, not 3-3-3
  "Rs. 5.40 Crore" and "54000000" are the same number written two ways
  a trailing "/-" is decoration
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Labels that mean "this is the bid total", not a line item or a subtotal of one section.
_TOTAL_LABELS = re.compile(
    r"(grand\s+total|total\s+bid\s+(value|amount|price)|total\s+quoted\s+(value|amount|price)"
    r"|bid\s+price|total\s+cost|total\s+amount)",
    re.IGNORECASE,
)

_CRORE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(crore|cr\b)", re.IGNORECASE)
_LAKH = re.compile(r"([\d,]+(?:\.\d+)?)\s*(lakh|lac|lakhs)", re.IGNORECASE)
_PLAIN = re.compile(r"(?:₹|rs\.?|inr)?\s*([\d][\d,]{2,})(?:\.\d{1,2})?\s*(?:/-)?", re.IGNORECASE)


def _num(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def parse_amount(text: str) -> Decimal | None:
    """One figure from one fragment, in whole rupees. None when it cannot be read."""
    m = _CRORE.search(text)
    if m:
        v = _num(m.group(1))
        return v * Decimal("10000000") if v is not None else None
    m = _LAKH.search(text)
    if m:
        v = _num(m.group(1))
        return v * Decimal("100000") if v is not None else None
    m = _PLAIN.search(text)
    if m:
        return _num(m.group(1))
    return None


def extract_total(pages: list[tuple[int, str]]) -> tuple[Decimal | None, int | None]:
    """(amount, anchor page) for the bid total, or (None, None) if it is not unambiguous.

    Ambiguity means: no labelled total, or two labelled totals that disagree. Both route to a
    human. Two agreeing labels (a summary page repeating the schedule) are not a conflict.
    """
    found: list[tuple[Decimal, int]] = []
    for page_no, text in pages:
        for line in text.splitlines():
            if not _TOTAL_LABELS.search(line):
                continue
            amount = parse_amount(line)
            if amount is not None and amount > 0:
                found.append((amount, page_no))

    if not found:
        return None, None
    distinct = {a for a, _ in found}
    if len(distinct) > 1:
        # The document states more than one total. Picking the largest would be a guess, and
        # picking the last would be a guess about layout.
        return None, None
    return found[0][0], found[0][1]
