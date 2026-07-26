"""QCBS combination and ranking (F10). Decimal throughout — float drift must never decide
which of two bidders wins."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class RankedBid:
    bid_id: str
    bidder_name: str
    technical_score: Decimal
    technically_qualified: bool
    financial_score: Decimal | None
    combined_score: Decimal | None
    rank: int | None
    tied_with: tuple[str, ...] = ()


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def financial_score(amount: Decimal, lowest: Decimal) -> Decimal:
    """Lowest evaluated price scores 100; others score proportionally below it."""
    if amount <= 0:
        raise ValueError("quoted amount must be positive")
    return _q(Decimal(100) * lowest / amount)


def rank(
    bids: list[dict],
    *,
    technical_weight: int,
    financial_weight: int,
    max_technical_marks: int,
) -> list[RankedBid]:
    """Combine and rank. Only technically qualified bids with a price can be ranked.

    Ties are RETURNED AS TIES — `tied_with` populated, and the caller must not finalise until
    a human records the published tie-break rule. Software inventing a winner on an unpublished
    rule is what gets an award set aside.
    """
    qualified = [b for b in bids if b["technically_qualified"] and b.get("amount") is not None]
    lowest = min((Decimal(str(b["amount"])) for b in qualified), default=None)

    out: list[RankedBid] = []
    for b in bids:
        tech = Decimal(str(b["technical_score"]))
        tech_pct = (
            _q(Decimal(100) * tech / Decimal(max_technical_marks))
            if max_technical_marks > 0 else Decimal(0)
        )
        fin = comb = None
        if b["technically_qualified"] and b.get("amount") is not None and lowest is not None:
            fin = financial_score(Decimal(str(b["amount"])), lowest)
            comb = _q(
                (tech_pct * Decimal(technical_weight) + fin * Decimal(financial_weight))
                / Decimal(100)
            )
        out.append(RankedBid(
            bid_id=b["bid_id"], bidder_name=b["bidder_name"],
            technical_score=_q(tech), technically_qualified=b["technically_qualified"],
            financial_score=fin, combined_score=comb, rank=None,
        ))

    rankable = sorted(
        [r for r in out if r.combined_score is not None],
        key=lambda r: r.combined_score, reverse=True,
    )
    resolved: list[RankedBid] = []
    position = 1
    i = 0
    while i < len(rankable):
        same = [r for r in rankable if r.combined_score == rankable[i].combined_score]
        for r in same:
            others = tuple(o.bidder_name for o in same if o.bid_id != r.bid_id)
            resolved.append(RankedBid(**{**r.__dict__, "rank": position, "tied_with": others}))
        position += len(same)
        i += len(same)

    unranked = [r for r in out if r.combined_score is None]
    return resolved + unranked


def has_unresolved_tie(ranked: list[RankedBid]) -> bool:
    return any(r.tied_with for r in ranked)
