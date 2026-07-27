"""Requirement coverage per bid (F20). No model in this path — ever.

TP17 is an officer reading hundreds of pages per bid to find out what was actually offered
against each technical requirement. The extraction that answers that already exists
(`pipeline/responder`), and it already records a stated value, an excerpt and a page anchor per
criterion. What was missing is the arithmetic on top: a denominator, a coverage state per cell,
and a count an officer can trust.

**This module produces evidence, never a verdict.** `NOT_FOUND` means "we did not locate an
answer in the submission", NOT "the bidder is non-compliant". The difference matters: an
extraction miss on page 180 of a scanned bid is our failure, not the bidder's, and F6 owns
responsiveness anyway. Nothing here writes to a decision table.

The denominator is computed once, here, and everything else reads it. Four counters describing
one object will disagree — the bidder product already shipped that bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Coverage(StrEnum):
    ADDRESSED = "addressed"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"          # never rendered or exported as non-compliance
    CONTRADICTORY = "contradictory"  # the bid says two different things


@dataclass(frozen=True)
class RequirementRef:
    id: str
    text: str
    max_marks: int = 0


@dataclass(frozen=True)
class OfferRef:
    """What the bid was found to say against one requirement."""

    criterion_id: str
    stated_value: str | None = None
    excerpt: str | None = None
    anchor_page: int | None = None


@dataclass(frozen=True)
class CoverageCell:
    requirement_id: str
    coverage: Coverage
    stated_value: str | None
    excerpt: str | None
    anchor_page: int | None


# An answer with a value but no locatable excerpt is weaker evidence: something was read, but
# an officer cannot jump to the page and check it. That is PARTIAL, not ADDRESSED — the whole
# promise of this screen is that every claim is checkable in one click.
def classify(offers: list[OfferRef]) -> Coverage:
    stated = [o for o in offers if (o.stated_value or "").strip()]
    if not stated:
        return Coverage.NOT_FOUND

    values = {(o.stated_value or "").strip().lower() for o in stated}
    if len(values) > 1:
        return Coverage.CONTRADICTORY

    if any(o.anchor_page is not None and (o.excerpt or "").strip() for o in stated):
        return Coverage.ADDRESSED
    return Coverage.PARTIAL


def cover_bid(requirements: list[RequirementRef],
              offers: list[OfferRef]) -> tuple[CoverageCell, ...]:
    by_req: dict[str, list[OfferRef]] = {}
    for o in offers:
        by_req.setdefault(o.criterion_id, []).append(o)

    cells = []
    for r in requirements:
        found = by_req.get(r.id, [])
        coverage = classify(found)
        best = next((o for o in found if o.anchor_page is not None), found[0] if found else None)
        cells.append(CoverageCell(
            requirement_id=r.id,
            coverage=coverage,
            stated_value=best.stated_value if best else None,
            excerpt=best.excerpt if best else None,
            anchor_page=best.anchor_page if best else None,
        ))
    return tuple(cells)


def denominator(requirements: list[RequirementRef]) -> int:
    """THE requirement count. One function, so the header, the per-bid summary and any export
    cannot disagree about how many there are."""
    return len(requirements)


def addressed_count(cells: tuple[CoverageCell, ...]) -> int:
    """Cells an officer does not need to read the bid for. PARTIAL deliberately does not
    count — it is the state that still needs a human to open the document."""
    return sum(1 for c in cells if c.coverage is Coverage.ADDRESSED)


def needs_attention(cells: tuple[CoverageCell, ...]) -> tuple[str, ...]:
    """Requirements worth an officer's time, worst first: contradictions, then gaps.

    This is the ranking that turns "read 300 pages" into "read these four things".
    """
    contradictory = [c.requirement_id for c in cells if c.coverage is Coverage.CONTRADICTORY]
    not_found = [c.requirement_id for c in cells if c.coverage is Coverage.NOT_FOUND]
    partial = [c.requirement_id for c in cells if c.coverage is Coverage.PARTIAL]
    return tuple(contradictory + not_found + partial)
