"""What a category has actually been winning at (UML ask 5). Pure — no I/O, no model.

UML's words: *"identifying and analysing the historical prices of the respective scheduled
items"* and *"understanding previous price trends"*. This turns a pile of award records into
the four numbers a bid manager actually uses, and refuses to produce the one that would be a
lie.

**The refusal is the important part.** `total_price` is what a seller bid for the WHOLE
schedule, and GeM routinely bundles unrelated items into one bid — a real record from the live
feed reads "Wire Copper Insulated, Fevi Quick, Throttle Spray, Wire Connector Thimble". A
per-unit rate derived from that bundle is confidently wrong, and a wrong benchmark price is
worse than no benchmark: it is the number someone prices a real bid against. So an implied
unit rate is emitted ONLY where the record is a single-category bid with a known quantity, and
every summary says how many of its records qualified.

**Median, not mean.** Government award values are wildly skewed — a ₹9,925 bundle and a ₹40 Cr
framework sit in the same category — and one outlier moves a mean past every real observation.
The same argument as `LearningMeter.readTrend`, for the same reason: this number's only job is
to be believable.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass

#: Below this, a "typical winning price" is one or two bids wearing a statistic's clothing.
MIN_AWARDS_FOR_TYPICAL = 3

#: GeM writes a bundle as a comma-separated category string. One item, one comma-free string.
_BUNDLE = re.compile(r",|\band\b|\+", re.I)


@dataclass(frozen=True)
class Award:
    """One published result, flattened. `winning_price` is the L1 total for the schedule."""

    portal_ref_no: str
    category: str | None
    department: str | None
    quantity: float | None
    bid_end_date: str | None
    winner: str | None
    winner_is_mse: bool
    winning_price: float | None
    runner_up_price: float | None
    participants: int
    source_url: str | None

    @property
    def is_single_category(self) -> bool:
        """Can a per-unit rate mean anything for this record?"""
        return bool(self.category) and not _BUNDLE.search(self.category or "")

    @property
    def implied_unit_price(self) -> float | None:
        """Winning total ÷ quantity — only where that division is defensible."""
        if not (self.is_single_category and self.winning_price and self.quantity):
            return None
        if self.quantity <= 0:
            return None
        return round(self.winning_price / self.quantity, 2)

    @property
    def undercut_pct(self) -> float | None:
        """How far below the runner-up the winner came in. The 'how much room did I have' number.

        Reported per award rather than averaged into the summary: a bidder is deciding on ONE
        tender, and the spread on comparable individual awards tells them more than a mean of
        spreads across bundles of different shapes.
        """
        if not (self.winning_price and self.runner_up_price) or self.runner_up_price <= 0:
            return None
        return round((self.runner_up_price - self.winning_price) / self.runner_up_price * 100, 1)

    def as_dict(self) -> dict:
        return {**asdict(self), "implied_unit_price": self.implied_unit_price,
                "undercut_pct": self.undercut_pct,
                "is_single_category": self.is_single_category}


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return round(s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2, 2)


def summarise(awards: Sequence[Award]) -> dict:
    """The four numbers, plus an honest account of what could not be computed.

    Every count here exists so a zero can be read correctly. "No typical unit price" means one
    of two very different things — nobody bid, or every bid was a bundle — and a summary that
    cannot tell them apart invites the user to conclude the wrong one.
    """
    priced = [a for a in awards if a.winning_price]
    wins = [a.winning_price for a in priced if a.winning_price]
    unit_rated = [a for a in priced if a.implied_unit_price is not None]
    units = [a.implied_unit_price for a in unit_rated if a.implied_unit_price is not None]
    dates = sorted(a.bid_end_date for a in awards if a.bid_end_date)

    return {
        "awards": len(awards),
        "with_published_price": len(priced),
        # Suppressed below the floor rather than shown small: three awards is not a market rate,
        # and a number labelled "typical" carries more authority than the evidence behind it.
        "typical_winning_price": _median(wins) if len(wins) >= MIN_AWARDS_FOR_TYPICAL else None,
        "lowest_winning_price": min(wins) if wins else None,
        "highest_winning_price": max(wins) if wins else None,
        "typical_unit_price": (
            _median(units) if len(units) >= MIN_AWARDS_FOR_TYPICAL else None
        ),
        # The denominator for the number above. Without it, a null unit price reads as "no
        # data" when it usually means "these were bundled bids" — a different fact entirely.
        "single_category_awards": len(unit_rated),
        "mse_wins": sum(1 for a in priced if a.winner_is_mse),
        "first_award": dates[0] if dates else None,
        "last_award": dates[-1] if dates else None,
        "min_awards_for_typical": MIN_AWARDS_FOR_TYPICAL,
    }


def to_award(result: dict, ladder: Sequence[dict]) -> Award:
    """Flatten a stored result plus its price rows into one comparable record."""
    ranked = sorted((r for r in ladder if r.get("rank")), key=lambda r: r["rank"])
    win = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    return Award(
        portal_ref_no=result.get("portal_ref_no") or "",
        category=result.get("category"),
        department=result.get("department"),
        quantity=_number(result.get("quantity")),
        bid_end_date=result.get("bid_end_date"),
        winner=(win or {}).get("seller"),
        winner_is_mse=bool((win or {}).get("mse")),
        winning_price=_number((win or {}).get("total_price")),
        runner_up_price=_number((second or {}).get("total_price")),
        participants=int(result.get("participants") or 0),
        source_url=result.get("source_url"),
    )


def _number(value) -> float | None:  # noqa: ANN001
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
