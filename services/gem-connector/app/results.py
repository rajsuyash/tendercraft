"""GeM published bid results → the awarded price ladder. Pure functions, no network.

**Why this file exists, and why it contradicts a document in this repo.**
`docs/discovery/source-gem-contracts.md` recorded ask 5 (five-year price history) as REFUSED,
because `gem.gov.in/view_contracts` is CAPTCHA-gated on both its search forms. That finding is
correct and stands — `/view_contracts/bid_detail` was re-probed on 2026-08-16 and is still
captcha'd. What that review never checked is the surface *this service already sweeps*: its own
§5 listed "whether any other public GeM surface publishes award data" as not probed, and worth
an hour. It was worth an hour.

`bidplus.gem.gov.in/all-bids-data` — the same endpoint, the same anonymous cookie, the same
CSRF token used for the ongoing-bid listing — returns published RESULTS when asked for them:

    filter.bidStatusType = "bidrastatus"     (not "ongoing_bids")
    filter.byStatus      = "bid_awarded" | "tech_evaluated" | "fin_evaluated"

and each result links to a public page carrying the full competitive ladder:

    S.No | Seller Name | Offered Item | Total Price | Rank
    1    | J.S TRADERS (MSE)     | Wire Copper Insulated,…  | ` 9925.00  | L1
    2    | H S ELECTRICALS       | …                        | ` 11631.00 | L2

No captcha, no login, robots-clean. Measured 2026-08-16: 45,273 awarded bids for "wire rope".

**The two traps in that payload, both found by measurement.** `bidStatusType` accepts only
`ongoing_bids` and `bidrastatus`; any other value — including plausible guesses like
`bid_won` or `awarded` — is silently IGNORED rather than rejected, and the endpoint returns the
unfiltered set with `message: "Bid result"` regardless. A filter that is ignored rather than
refused is how a confident wrong answer gets built, so `build_results_payload` refuses an
unknown status here rather than sending it. And the result page's URL depends on the bid's own
shape (`b_eval_type`, `ba_is_single_packet`) — `result_path` mirrors GeM's own JS.

**What we store (§8).** GeM's copyright policy forbids reproducing site *contents*. A price, a
rank, a seller name, a quantity and a date are FACTS, and facts-plus-deep-link is the posture
`source-gem.md` §8 already settled for the listing. It applies here unchanged: we keep the
numbers and link back to the page for the prose.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import asdict, dataclass

BASE_URL = "https://bidplus.gem.gov.in"

#: The only two values `bidStatusType` recognises. Anything else is ignored by the portal and
#: silently returns unfiltered results (measured 2026-08-16).
_STATUS_TYPE = "bidrastatus"

#: The evaluation stages GeM publishes, exactly as its own checkboxes name them. The ordering
#: is the bid's lifecycle and `loadBids()` spells it out: Not Evaluated -> Technical Evaluation
#: -> Financial Evaluation -> Bid Award.
RESULT_STATUSES = ("tech_evaluated", "fin_evaluated", "bid_awarded")

#: `b_buyer_status` on the listing record encodes the same lifecycle numerically. Kept beside
#: RESULT_STATUSES because the two must agree, and nothing else in the response says so.
BUYER_STATUS_STAGE = {0: "not_evaluated", 1: "tech_evaluated", 2: "fin_evaluated",
                      3: "bid_awarded"}

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
#: The price has its own class on the page, which is a far better anchor than column position:
#: GeM's tables gain and lose columns between bid shapes, and an index would drift silently.
_PRICE = re.compile(r'<span[^>]*class="[^"]*bid_price[^"]*"[^>]*>(.*?)</span>', re.S | re.I)
_RANK = re.compile(r"\bL(\d{1,3})\b")
#: "Under PMA" is rendered inside a display:none span. It is portal chrome, not part of the
#: seller's name, and stripping tags without dropping it first welds it onto every name.
_HIDDEN = re.compile(r'<span[^>]*style="[^"]*display:\s*none[^"]*"[^>]*>.*?</span>', re.S | re.I)
_MSE_SOCIAL = re.compile(r"\(\s*MSE Social Category\s*:[^)]*\)", re.I)


@dataclass(frozen=True)
class Participant:
    """A seller who took part. Present even when they did not win — that is the point."""

    seller: str
    mse: bool
    participated_on: str | None
    status: str | None          # 'Qualified' | 'Disqualified' as the portal words it


@dataclass(frozen=True)
class PriceRow:
    """One rung of the competitive ladder: who bid what, and where they placed."""

    seller: str
    mse: bool
    total_price: float
    rank: int                   # 1 for L1. The winning price is rank 1.
    offered_item: str | None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BidResult:
    participants: tuple[Participant, ...]
    ladder: tuple[PriceRow, ...]

    @property
    def winner(self) -> PriceRow | None:
        return self.ladder[0] if self.ladder else None

    def as_dict(self) -> dict:
        return {
            "participants": [asdict(p) for p in self.participants],
            "ladder": [r.as_dict() for r in self.ladder],
            "winner": self.winner.as_dict() if self.winner else None,
            "participant_count": len(self.participants),
        }


def build_results_payload(page: int, search: str = "",
                          status: str = "bid_awarded") -> dict[str, str]:
    """The body `/all-bids-data` expects for PUBLISHED RESULTS rather than open bids.

    Raises on an unknown status instead of sending it. The portal would accept the request and
    return everything, which reads as "this category has 5.7 million awards" — a wrong answer
    that looks like a working feature.
    """
    if status not in RESULT_STATUSES:
        raise ValueError(f"unknown result status {status!r}; expected one of {RESULT_STATUSES}")
    payload = {
        "page": page,
        "param": {"searchBid": search, "searchType": "fullText"},
        "filter": {
            "bidStatusType": _STATUS_TYPE,
            "byStatus": status,
            "byType": "all",
            "highBidValue": "",
            "byEndDate": {"from": "", "to": ""},
            # Latest first: price history is most useful newest-first, and an incremental
            # sweep needs the new awards on page 1 for the same reason the listing does.
            "sort": "Bid-End-Date-Latest",
        },
    }
    return {"payload": json.dumps(payload, separators=(",", ":"))}


def result_path(doc: dict) -> str:
    """Where THIS bid's result lives, mirroring GeM's own `/all-bids` JavaScript:

        b_eval_type > 0        -> getBidResultViewSchedule   (per-schedule evaluation)
        ba_is_single_packet    -> getSinglePacketResultView
        otherwise              -> getBidResultView

    Guessing one path for all three returns an empty 200 for the other two, which parses to
    "no sellers participated" — a false fact, and the worst possible failure for a price
    feature, because nothing about it looks like an error.
    """
    bid_id = _first(doc, "b_id")
    if _first(doc, "b_eval_type", 0) > 0:
        return f"bidding/bid/getBidResultViewSchedule/{bid_id}"
    if _first(doc, "ba_is_single_packet", 0) == 1:
        return f"bidding/bid/getSinglePacketResultView/{bid_id}"
    return f"bidding/bid/getBidResultView/{bid_id}"


def result_stage(doc: dict) -> str:
    """How far this bid has got. `b_buyer_status` is the portal's own lifecycle counter."""
    return BUYER_STATUS_STAGE.get(_first(doc, "b_buyer_status", 0), "not_evaluated")


def _first(doc: dict, key: str, default=None):  # noqa: ANN001, ANN202
    """Solr returns every field as a single-element list. Unwrap without assuming presence."""
    value = doc.get(key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value if value is not None else default


def _text(fragment: str) -> str:
    """Cell text, with hidden portal chrome removed BEFORE the tags are stripped."""
    return _WS.sub(" ", html_lib.unescape(_TAG.sub(" ", _HIDDEN.sub(" ", fragment)))).strip()


def _seller(fragment: str) -> tuple[str, bool]:
    """(clean name, is MSE). The MSE marker is a fact the portal states; keep it, unglued."""
    raw = _text(fragment)
    mse = bool(re.search(r"\(\s*MSE\s*\)|\bMSE\b", raw, re.I))
    name = _MSE_SOCIAL.sub(" ", raw)
    name = re.sub(r"\(\s*MSE\s*\)|\(\s*MII\s*\)", " ", name, flags=re.I)
    name = re.sub(r"\bUnder PMA\b", " ", name, flags=re.I)
    return _WS.sub(" ", name).strip(" -|,"), mse


def _price(fragment: str) -> float | None:
    """The awarded amount. `class="bid_price"` first; the rupee glyph on this page is a
    BACKTICK (a GeM webfont), so a `₹`-anchored regex finds nothing and reports no prices."""
    m = _PRICE.search(fragment)
    text = _text(m.group(1)) if m else _text(fragment)
    m2 = re.search(r"[\d,]+(?:\.\d+)?", text)
    if not m2:
        return None
    try:
        return float(m2.group(0).replace(",", ""))
    except ValueError:
        return None


def _rows(table_html: str) -> list[list[str]]:
    return [cells for r in _ROW.findall(table_html)
            if (cells := _CELL.findall(r))]


def _header_index(cells: list[str]) -> dict[str, int]:
    return {_text(c).lower(): i for i, c in enumerate(cells)}


def parse_result_page(page_html: str) -> BidResult:
    """Participants and the price ladder from a published GeM result page.

    Tables are matched by their HEADER TEXT, never by position: a bid with no financial
    evaluation yet renders only the participants table, and an index-based reader would then
    parse participants as prices and report a ladder of zero-rupee bids.
    """
    participants: list[Participant] = []
    ladder: list[PriceRow] = []

    for table in re.findall(r"<table[^>]*>.*?</table>", page_html, re.S | re.I):
        rows = _rows(table)
        if not rows:
            continue
        head = _header_index(rows[0])
        if "total price" in head and "rank" in head:
            for cells in rows[1:]:
                if len(cells) <= max(head["total price"], head["rank"]):
                    continue
                price = _price(cells[head["total price"]])
                rank_m = _RANK.search(_text(cells[head["rank"]]))
                if price is None or not rank_m:
                    # A row we cannot read is DROPPED, never defaulted. A zero-priced L0 in a
                    # price history is worse than a shorter ladder.
                    continue
                name, mse = _seller(cells[head.get("seller name", 1)])
                item = (_text(cells[head["offered item"]])
                        if "offered item" in head and len(cells) > head["offered item"] else None)
                ladder.append(PriceRow(seller=name, mse=mse, total_price=price,
                                       rank=int(rank_m.group(1)),
                                       offered_item=item or None))
        elif "seller name" in head and "status" in head:
            for cells in rows[1:]:
                if len(cells) <= head["status"]:
                    continue
                name, mse = _seller(cells[head["seller name"]])
                if not name:
                    continue
                on = (_text(cells[head["participated on"]])
                      if "participated on" in head and len(cells) > head["participated on"]
                      else None)
                participants.append(Participant(seller=name, mse=mse,
                                                participated_on=on or None,
                                                status=_text(cells[head["status"]]) or None))

    ladder.sort(key=lambda r: r.rank)
    return BidResult(participants=tuple(participants), ladder=tuple(ladder))
