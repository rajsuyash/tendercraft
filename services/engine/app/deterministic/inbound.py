"""Reading a forwarded GeM email. Pure — no I/O, no model, no network.

UML ask 4, and the half of ask 1 the crawler cannot reach. GeM emails a registered seller both
the category-matched new-bid alert and the post-technical-evaluation request for additional
documents. The second is the only legal route to that request: it is addressed to one bidder
about their own submission, it is not on any public page, and the alternative — logging in to
the customer's GeM account — is refused by G-1 and G-8 and always will be.

**The design constraint that shaped everything here: we have never seen one of these emails.**
`docs/feedback/usha-martin.md` has been blocked on "ask UML to forward three" since 2026-08-07,
and the parse was called unspecifiable. It is not, as long as the parser is built to be wrong.

Three rules follow from that, and they are the whole module:

1. **Classification decides ROUTING, never RETENTION.** Every message is stored and surfaced.
   An unrecognised email becomes "something arrived about GEM/2026/B/7876746 that we could not
   classify", with the text one click away — which is strictly better than the status quo of a
   human reading it in Outlook, and cannot silently drop the one email that mattered.
2. **Only the bid reference is trusted.** It is a rigid format (`GEM/<year>/<B|R>/<digits>`),
   it is certainly present in any mail GeM sends about a bid, and it is the dedup key the rest
   of the product already uses. Everything else — dates, document lists, the class itself — is
   a guess that a human confirms.
3. **A guess never sets a deadline.** `due_at` is populated only from an explicit date in the
   text. Inventing "probably 7 days" would put a wrong date on a compliance action, and a
   bidder who missed a real deadline because our estimate looked authoritative is the exact
   harm this feature exists to prevent.

**The email body is untrusted input (G-6),** the same as a tender document — more so, because
anyone who learns a workspace's inbound address can send to it. Nothing here interprets an
instruction, follows a URL, or reaches a model. It matches patterns and counts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

#: GeM's bid reference. Anchored on the literal prefix rather than a loose slash pattern: a
#: forwarded email carries quoted headers, signatures and disclaimers full of slashes and
#: dates, and a permissive pattern turns any of them into a tender we then act on.
_BID_REF = re.compile(r"\bGEM\s*/\s*(\d{4})\s*/\s*([BR])\s*/\s*(\d{4,12})\b", re.I)

#: Message classes, most specific first — the order IS the precedence, because a clarification
#: request about a bid also contains everything that looks like a bid alert.
CLARIFICATION = "clarification_request"
STAGE_NOTICE = "stage_notice"
BID_ALERT = "bid_alert"
UNCLASSIFIED = "unclassified"

#: Phrases that mark a seller-specific request for more. Deliberately narrow: a false
#: CLARIFICATION shows a bidder a document deadline that does not exist, which is worse than
#: showing them UNCLASSIFIED and letting them read it.
_CLARIFICATION_MARKERS = (
    "additional document", "additional documents", "clarification sought",
    "seek clarification", "seeking clarification", "clarification required",
    "document required", "documents required", "submit the following",
    "upload the following", "furnish the following", "shortfall document",
)
_STAGE_MARKERS = (
    "technical evaluation", "financial evaluation", "technically qualified",
    "technically disqualified", "bid has been evaluated", "evaluation completed",
)
_ALERT_MARKERS = (
    "new bid", "new bids", "bid published", "matching your category",
    "bids matching", "opportunity", "participate in the bid",
)

#: Dates GeM writes in prose. Numeric-first because the portal is consistent about DD-MM-YYYY,
#: and a bare "05/06/2026" is read the Indian way — an American reading would move a June
#: deadline to May and lose the bid.
_DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
           "jul", "aug", "sep", "oct", "nov", "dec")
_TEXT_DATE = re.compile(
    r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")[a-z]*\.?\s+(\d{4})\b",
    re.I,
)

#: A date only counts as a deadline if the text says it is one. GeM emails carry sent-dates,
#: publication dates and bid-open dates; taking the first date in the message would routinely
#: put yesterday on a compliance action.
_DEADLINE_CUES = (
    "by", "before", "on or before", "due", "last date", "deadline",
    "within", "not later than", "closing", "expires", "valid till", "valid up to",
)


@dataclass(frozen=True)
class ParsedMessage:
    """What a forwarded email is about, with every uncertainty visible.

    `needs_human` is not a quality score. It is the instruction to the UI: show this to
    somebody, because we are not confident enough for it to sit quietly in a list.
    """

    kind: str
    bid_refs: tuple[str, ...]
    due_at: date | None
    #: Phrases that drove the classification, so a user can see WHY — and so a wrong call is
    #: diagnosable from the stored row rather than by re-running the parser on a lost email.
    matched: tuple[str, ...] = ()
    needs_human: bool = True
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def primary_ref(self) -> str | None:
        """The bid this message is about, when exactly one bid is named.

        Two references means a digest or a quoted thread, and picking one would attach a
        document request to the wrong tender — a failure that looks like a working feature
        right up until the wrong deadline is missed.
        """
        return self.bid_refs[0] if len(self.bid_refs) == 1 else None


def extract_bid_refs(text: str) -> tuple[str, ...]:
    """Every distinct GeM bid reference in the message, in the order they appear.

    Normalised to match `gem-connector`'s `normalize_ref` — upper case, separators collapsed —
    because this is the key an email-sourced record dedups against the crawled corpus on. Two
    spellings of one bid would produce two rows and the customer would see the tender twice.
    """
    seen: dict[str, None] = {}
    for match in _BID_REF.finditer(text or ""):
        year, kind, number = match.groups()
        seen.setdefault(f"GEM/{year}/{kind.upper()}/{number}", None)
    return tuple(seen)


def _parse_date(day: str, month: str, year: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def find_deadline(text: str, *, today: date) -> date | None:
    """A date the message explicitly presents as a deadline, or None.

    None is a first-class answer here, not a failure: the action still gets created, it simply
    carries no date, and the UI asks the human for one. A guessed deadline is the one output
    of this module that could cost a bid outright.
    """
    lowered = (text or "").lower()
    candidates: list[date] = []

    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(lowered):
            groups = match.groups()
            parsed = (_parse_date(groups[2], groups[1], groups[0])
                      if len(groups[0]) == 4 else _parse_date(*groups))
            if parsed and _is_cued(lowered, match.start()) and parsed >= today:
                candidates.append(parsed)

    for match in _TEXT_DATE.finditer(lowered):
        day, month_name, year = match.groups()
        month = _MONTHS.index(month_name[:3].lower()) + 1
        parsed = _parse_date(day, str(month), year)
        if parsed and _is_cued(lowered, match.start()) and parsed >= today:
            candidates.append(parsed)

    # Earliest wins: a message naming several dates is naming a window, and the near end of a
    # compliance window is the one that can be missed.
    return min(candidates) if candidates else None


def _is_cued(lowered: str, position: int) -> bool:
    """Is there deadline language immediately before this date?

    A 60-character window rather than the sentence: GeM's mails run dates into tables and
    line breaks where sentence splitting is unreliable, and widening this to the paragraph
    reintroduces the sent-date as a deadline.
    """
    window = lowered[max(0, position - 60):position]
    return any(cue in window for cue in _DEADLINE_CUES)


def classify(subject: str, body: str, *, today: date) -> ParsedMessage:
    """What is this email, and what does it name?

    Returns UNCLASSIFIED rather than guessing when nothing matches — see the module docstring.
    An unclassified message with a bid reference is still useful and is still shown; it simply
    makes no claim about what the sender wanted.
    """
    text = f"{subject or ''}\n{body or ''}"
    lowered = text.lower()
    refs = extract_bid_refs(text)

    for kind, markers in ((CLARIFICATION, _CLARIFICATION_MARKERS),
                          (STAGE_NOTICE, _STAGE_MARKERS),
                          (BID_ALERT, _ALERT_MARKERS)):
        hits = tuple(m for m in markers if m in lowered)
        if hits:
            due = find_deadline(text, today=today) if kind == CLARIFICATION else None
            return ParsedMessage(
                kind=kind,
                bid_refs=refs,
                due_at=due,
                matched=hits,
                # A bid alert is a feed item and the feed already ranks; the two classes that
                # imply someone must DO something are the ones that interrupt a person.
                needs_human=kind in (CLARIFICATION, STAGE_NOTICE),
                notes=_notes(refs, due, kind),
            )

    return ParsedMessage(kind=UNCLASSIFIED, bid_refs=refs, due_at=None,
                         needs_human=True, notes=_notes(refs, None, UNCLASSIFIED))


def _notes(refs: tuple[str, ...], due: date | None, kind: str) -> tuple[str, ...]:
    """Plain sentences a person reads, not codes. These end up on screen verbatim."""
    out = []
    if not refs:
        out.append("No GeM bid reference found in this message — it could not be linked to a "
                   "tender.")
    elif len(refs) > 1:
        out.append(f"{len(refs)} bid references found; not linked automatically because a "
                   "request attached to the wrong tender is worse than one left unlinked.")
    if kind == CLARIFICATION and due is None:
        out.append("No response deadline was stated in a form we could read. Check the "
                   "original email — GeM clarification windows are short.")
    if kind == UNCLASSIFIED:
        out.append("We could not tell what this email is. It is kept in full so nothing is "
                   "lost; open it to decide.")
    return tuple(out)
