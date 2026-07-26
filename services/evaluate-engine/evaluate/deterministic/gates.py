"""The gates. Every function here decides something that a model must never decide.

Three of them are load-bearing for the legality of an award:
  - `technical_lock_blockers`  quorum + consensus must be satisfied before scores freeze
  - `financial_readable`       the sealed-bid rule
  - `qualified`                who may have their price opened at all
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .types import CriterionAggregate


@dataclass(frozen=True)
class Blocker:
    code: str
    detail: str


def committee_mark(agg: CriterionAggregate) -> Decimal | None:
    """The committee's mark for one criterion, or None if it is not settled yet.

    A recorded consensus always wins. Otherwise the mean stands ONLY if the members agreed
    closely enough; a spread at or above the threshold means the committee has not actually
    decided, and returning the mean there would let an average stand on a criterion nobody
    discussed.
    """
    if agg.consensus is not None:
        return agg.consensus
    if not agg.marks:
        return None
    if requires_consensus(agg):
        return None
    return sum(agg.marks) / Decimal(len(agg.marks))


def requires_consensus(agg: CriterionAggregate, threshold_fraction: float = 0.20) -> bool:
    """True when members diverged enough that the committee must agree explicitly."""
    if len(agg.marks) < 2 or agg.max_marks <= 0:
        return False
    return agg.spread >= Decimal(str(threshold_fraction)) * Decimal(agg.max_marks)


def technical_score(aggregates: list[CriterionAggregate]) -> Decimal | None:
    """Total technical marks for one bid, or None while any criterion is unsettled."""
    total = Decimal(0)
    for a in aggregates:
        m = committee_mark(a)
        if m is None:
            return None
        total += m
    return total


def qualified(total: Decimal | None, qualifying_marks: int) -> bool:
    """Technically qualified — the only bidders whose financial envelope may be opened."""
    return total is not None and total >= Decimal(qualifying_marks)


def technical_lock_blockers(
    *,
    submitted_evaluators: int,
    quorum: int,
    unsettled: list[str],
) -> tuple[Blocker, ...]:
    """Everything standing between the committee and a frozen technical score."""
    out: list[Blocker] = []
    if submitted_evaluators < quorum:
        out.append(Blocker(
            "QUORUM_NOT_MET",
            f"{submitted_evaluators} of {quorum} required evaluators have submitted",
        ))
    if unsettled:
        out.append(Blocker(
            "CONSENSUS_REQUIRED",
            f"{len(unsettled)} criterion/criteria need a recorded consensus mark",
        ))
    return tuple(out)


def financial_readable(technical_locked_at) -> bool:
    """THE sealed-bid gate.

    One line, deliberately. Every read path that touches a price calls this, so there is a
    single place to audit and a single place to break. Reaching a financial figure while this
    returns False — by API, export, prefetch or error branch — invalidates the tender.
    """
    return technical_locked_at is not None
