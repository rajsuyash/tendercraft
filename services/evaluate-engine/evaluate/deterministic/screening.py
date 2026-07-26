"""PQ / responsiveness screening (F6). No model in this path — ever.

A criterion that removes a bidder from a public tender is decided by arithmetic, and the
arithmetic is here. `Not stated` is deliberately its own verdict: treating "we could not find
it in the PDF" as "the bidder fails" disqualifies someone on an extraction miss, which is the
single most damaging thing this product could do.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from .types import CompareKind, Criterion, Response, ScreeningCell, Verdict

_TRUE = {"yes", "true", "y", "present", "1"}
_FALSE = {"no", "false", "n", "absent", "0"}


def _num(v: str) -> Decimal | None:
    try:
        return Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _date(v: str) -> date | None:
    try:
        return date.fromisoformat(str(v).strip())
    except (ValueError, AttributeError):
        return None


def _cmp(op: str, left, right) -> bool:
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == "=":
        return left == right
    raise ValueError(f"unsupported comparison operator: {op!r}")


def evaluate_criterion(criterion: Criterion, response: Response | None) -> ScreeningCell:
    """One cell of the screening matrix."""
    stated = response.stated_value if response else None
    page = response.anchor_page if response else None

    if criterion.compare_kind is CompareKind.QUALITATIVE:
        # AI locates the evidence; a human decides. The gate never guesses.
        return ScreeningCell(criterion.id, Verdict.MANUAL, criterion.compare_value, stated, page)

    if stated is None or str(stated).strip() == "":
        return ScreeningCell(criterion.id, Verdict.NOT_STATED, criterion.compare_value, None, page)

    op = criterion.compare_op or "="
    required = criterion.compare_value

    if criterion.compare_kind is CompareKind.BOOLEAN:
        s = str(stated).strip().lower()
        if s in _TRUE:
            got = True
        elif s in _FALSE:
            got = False
        else:
            return ScreeningCell(criterion.id, Verdict.NOT_STATED, required, stated, page)
        want = str(required).strip().lower() in _TRUE if required is not None else True
        ok = got == want

    elif criterion.compare_kind is CompareKind.NUMERIC:
        got_n, want_n = _num(stated), _num(required or "")
        if got_n is None or want_n is None:
            return ScreeningCell(criterion.id, Verdict.NOT_STATED, required, stated, page)
        ok = _cmp(op, got_n, want_n)

    else:  # DATE
        got_d, want_d = _date(stated), _date(required or "")
        if got_d is None or want_d is None:
            return ScreeningCell(criterion.id, Verdict.NOT_STATED, required, stated, page)
        ok = _cmp(op, got_d, want_d)

    return ScreeningCell(
        criterion.id, Verdict.MEETS if ok else Verdict.FAILS, required, stated, page
    )


def screen_bid(
    criteria: list[Criterion], responses: list[Response]
) -> tuple[ScreeningCell, ...]:
    by_crit = {r.criterion_id: r for r in responses}
    return tuple(
        evaluate_criterion(c, by_crit.get(c.id)) for c in criteria if c.kind == "pq"
    )


def auto_non_responsive(cells: tuple[ScreeningCell, ...]) -> bool:
    """True only when a mandatory comparison DEFINITIVELY failed.

    `NOT_STATED` and `MANUAL` never auto-fail a bidder — they route to a human. This function
    proposes; the officer still records the decision and a reason (F6-AC3).
    """
    return any(c.verdict is Verdict.FAILS for c in cells)
