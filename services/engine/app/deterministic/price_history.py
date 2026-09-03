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
    """One published result, flattened. `winning_price` is the L1 total for the schedule.

    **Two fields carry a source's silence rather than an answer**, because this corpus now
    holds records from more than one feed and they do not publish the same things:

    * `winner_is_mse` is `None` where the source does not publish MSE status at all. False
      would be a claim about a named real company that nobody made.
    * `award_date` is whichever date the source published — bid close on GeM, contract award
      on an aggregated feed. The two are weeks apart and the corpus keeps them in separate
      columns; this is the axis they share.
    """

    portal_ref_no: str
    source_id: str
    category: str | None
    department: str | None
    quantity: float | None
    award_date: str | None
    winner: str | None
    winner_is_mse: bool | None
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
    dates = sorted(a.award_date for a in awards if a.award_date)

    sources: dict[str, int] = {}
    for a in awards:
        sources[a.source_id] = sources.get(a.source_id, 0) + 1

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
        # The denominator for the line above, and the same argument as `single_category_awards`:
        # not every source publishes MSE status, so "2 of 20" would read as eighteen wins by
        # large firms when most of the eighteen are simply unknown.
        "mse_unknown": sum(1 for a in priced if a.winner_is_mse is None),
        "first_award": dates[0] if dates else None,
        "last_award": dates[-1] if dates else None,
        "min_awards_for_typical": MIN_AWARDS_FOR_TYPICAL,
        # Which feeds these numbers came from. A blended median across portals is only
        # defensible if the screen can say what it blended.
        "by_source": sources,
    }


def to_award(result: dict, ladder: Sequence[dict]) -> Award:
    """Flatten a stored result plus its price rows into one comparable record.

    **The winner is read, never ranked by us.** Where the source published a ladder, L1 is the
    winner and L2 is the runner-up. Where it published only who won — which is most of an
    aggregated feed's single-bidder awards — the flagged row is the winner and there is NO
    runner-up, because sorting the remaining bidders by price and calling the cheapest L2 would
    invent a ladder position the portal never stated. `undercut_pct` then stays None, which is
    the honest answer to "how much room did the winner have": unknown.
    """
    ranked = sorted((r for r in ladder if r.get("rank")), key=lambda r: r["rank"])
    if ranked:
        win, second = ranked[0], (ranked[1] if len(ranked) > 1 else None)
    else:
        win, second = next((r for r in ladder if r.get("awarded")), None), None
    return Award(
        portal_ref_no=result.get("portal_ref_no") or "",
        source_id=result.get("source_id") or "gem_bidplus",
        category=result.get("category"),
        department=result.get("department"),
        quantity=_number(result.get("quantity")),
        award_date=result.get("observed_date") or result.get("bid_end_date"),
        winner=(win or {}).get("seller"),
        # Tri-state on purpose: `bool(None)` would turn "this feed does not publish MSE status"
        # into "this company is not an MSE".
        winner_is_mse=None if win is None or win.get("mse") is None else bool(win["mse"]),
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


# ---------- which awards are actually about what was asked for ----------
#
# GeM's full-text search ORs the words, so `wire rope` returns anything containing *wire*:
# measured on the live portal, one fetch of 40 awards for "wire rope" contained ONE wire rope
# and 39 bundles with "Printer Head wire bush", "HDMI CABLWire", "Aluminium Service Wire".
# Quoting the phrase makes it worse rather than better — `"wire rope"` returned 3.3 MILLION
# matches against 45,559 unquoted, so the portal treats the quotes as noise. There is no query
# that fixes this at the source; the filter has to be ours.
#
# **Why this is deliberately stricter than the feed's keyword rule.**
# `deterministic/discovery.py::keyword_relevance` matches on shared stems, because a vendor
# writing "networking" should still see "Network switch supply" — recall matters there, and a
# wrong guess only changes the ORDER things appear in. Here a wrong match becomes a number:
# a "typical winning price" averaged across HDMI cable and steel rope is a benchmark someone
# prices a real bid against. So this rule wants precision, and the two are not the same rule
# wearing different names. Anyone tempted to unify them should read this paragraph first.
#
# The SQL and Python forms below are two expressions of ONE rule and are pinned against each
# other by tests, per the `auth.py` / `current_workspace_id()` precedent in known-pitfalls:
# where a scoping rule must exist twice, write both in one place and test them together.

_QUERY_WORD = re.compile(r"[a-z0-9]+")


#: A comma in a GeM category joins two unrelated products. It is a BARRIER, not a space:
#: turning it into one makes "Insulated copper wire,Rope ladder" read as the phrase "wire rope",
#: which is the exact false positive this rule exists to stop. The sentinel is a character no
#: query can contain and that `_QUERY_WORD` ignores, so single-word tokenisation still splits
#: on it while phrase matching cannot cross it. Found by a test, not by reasoning.
_BUNDLE_BREAK = "\x00"


def _norm(text: str | None) -> str:
    """Lowercase, whitespace collapsed, bundle commas turned into an uncrossable break."""
    collapsed = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return collapsed.replace(",", _BUNDLE_BREAK)


def _pattern(query: str) -> str:
    """ONE pattern, used by both halves. Empty query → "" meaning no condition.

    Written once because the alternative drifts, and the drift is constructible rather than
    theoretical: a hand-written `ilike '%wire rope%'` fails on `wire  rope` — a double space,
    which occurs in the live corpus — while a Python `in` on collapsed whitespace succeeds. Two
    forms of "the same" rule disagreeing about a real row is the `auth.py` /
    `current_workspace_id()` pitfall in another costume.

    - `\\y` opens every term: a wire rope is not a **hard**wire rope.
    - `\\s+` joins them: the portal's spacing is not consistent and is not meaningful.
    - Nothing closes the pattern, so "wire rope**s**" matches — GeM writes the plural and the
      bidder types the singular.
    """
    words = _QUERY_WORD.findall(_norm(query))
    if not words:
        return ""
    # A single word closes with \y too, or "rope" would match "ropeway".
    if len(words) == 1:
        return rf"\y{re.escape(words[0])}\y"
    return r"\y" + r"\s+".join(re.escape(w) for w in words)


def category_matches(query: str, category: str | None) -> bool:
    """Is this award actually about `query`? Pure; the authority for what gets STORED.

    An empty query matches everything — "show me the whole corpus" is a real request, and
    returning nothing for it would look like an empty database.
    """
    pattern = _pattern(query)
    if not pattern:
        return True
    # `\y` is Postgres's spelling of a word boundary; Python spells it `\b`. Same assertion,
    # and this one substitution is the entire difference between the two halves.
    return re.search(pattern.replace(r"\y", r"\b"), _norm(category)) is not None


def postgrest_filter(query: str) -> dict[str, str]:
    """The same pattern as a PostgREST condition, so it runs BEFORE `limit`.

    Filtering after the query would truncate newest-first and then discard, so a search whose
    matches are all older than the page size returns nothing — the failure the date window has
    already been through. `imatch` is PostgREST's `~*`.
    """
    pattern = _pattern(query)
    return {"category": f"imatch.{pattern}"} if pattern else {}
