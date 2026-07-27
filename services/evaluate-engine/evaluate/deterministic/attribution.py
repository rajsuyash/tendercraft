"""Attribution resolution and the triage pile (F15). No model in this path — ever.

The model PROPOSES which bidder sent a file. This module decides whether that proposal is
allowed to stand. That is a gate, so it is arithmetic and it lives here.

One definition, used everywhere: the amber banner, the triage count, the `409 TRIAGE_PENDING`
guard on screening, and the presence matrix all call `triage_pile()`. The bidder product
shipped four counters describing one object and none of them agreeing; this is that trap, and
the fix is to have exactly one function that can answer the question.

Why a threshold at all: a confident wrong attribution binds one firm's document to another
firm's bid and **produces no error anywhere**. The screening matrix still renders as complete.
There is no natural feedback signal, so the only protection is refusing to be confident.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Attribution:
    """One file's proposal and confirmation. Mirrors the two column groups in the table."""

    file_id: str
    proposed_bid_id: str | None = None
    confidence: Decimal | None = None
    confirmed_bid_id: str | None = None
    confirmed_at: str | None = None


def effective_bid_id(a: Attribution, threshold: Decimal) -> str | None:
    """Which bid this file counts against, or None if nobody has settled it.

    A human confirmation always wins, including a human confirmation that CONTRADICTS a
    high-confidence proposal — that is the officer doing their job, not an anomaly to reconcile.
    """
    if a.confirmed_at is not None:
        # An explicit confirmation of "none of these bidders" is a real answer: the file is
        # settled and attributed to nothing. It must not fall through to the proposal.
        return a.confirmed_bid_id
    if a.proposed_bid_id is None or a.confidence is None:
        return None
    return a.proposed_bid_id if a.confidence >= threshold else None


def is_resolved(a: Attribution, threshold: Decimal) -> bool:
    """True when this file needs no human attention.

    A confirmed file is resolved even when confirmed to no bidder — the officer looked at it.
    """
    if a.confirmed_at is not None:
        return True
    return effective_bid_id(a, threshold) is not None


def triage_pile(attributions: list[Attribution], threshold: Decimal) -> tuple[str, ...]:
    """File ids awaiting a human, in input order. THE definition of the triage pile."""
    return tuple(a.file_id for a in attributions if not is_resolved(a, threshold))


def files_for_bid(attributions: list[Attribution], bid_id: str,
                  threshold: Decimal) -> tuple[str, ...]:
    """Files that count against one bid. Used by the presence gate (F18)."""
    return tuple(a.file_id for a in attributions if effective_bid_id(a, threshold) == bid_id)


def intake_blocked(attributions: list[Attribution], threshold: Decimal) -> bool:
    """Whether screening and presence must refuse to compute.

    A matrix built over a partial set of files renders as complete and is not. That is worse
    than refusing: the officer would read a finished-looking screen and make a decision on it.
    """
    return len(triage_pile(attributions, threshold)) > 0
