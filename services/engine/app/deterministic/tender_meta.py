"""Pull a tender's identity out of its own first pages — deterministically.

Every screen used to call a bid "rfp.pdf", because ingest stored the FILENAME as the
title. A bid manager running twelve pursuits cannot tell them apart, cannot hand one over,
and cannot find one later. The document already states its number, name and authority on
page one; nothing was reading them.

Deterministic on purpose (PRD §2.4): a tender number is a fact copied verbatim from the
document, not something a model should be free to paraphrase. Regexes over the labels
Indian government RFPs actually use — and when a label is absent we return None and keep
the filename, rather than guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_IST = timezone(timedelta(hours=5, minutes=30))

# "Tender No. MAHA/DMA/2026/0917", "NIT No: 42/2026-27", "RFP Reference: ABC-123"
_NUMBER = re.compile(
    r"\b(?:tender|nit|rfp|bid|e-?tender)\s*(?:no\.?|number|ref(?:erence)?)\s*[:.\-]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9/_\-]{3,40})",
    re.I,
)

# "Name of Work: ...", "Subject: ...", "Name of the Project: ..."
_TITLE = re.compile(
    r"\b(?:name\s+of\s+(?:the\s+)?(?:work|project|assignment)|subject|title\s+of\s+work)\s*[:.\-]\s*"
    # Terminates at a blank line, at the next "Some Label:" line, or at end of text.
    # The label pattern must allow MULTI-WORD labels: real PDFs run the title straight into
    # "Estimated Contract Value:" with no blank line, and a single-word rule misses it.
    r"(.{6,200}?)(?:\n\s*\n|\n(?=[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,4}\s*:)|$)",
    re.I | re.S,
)

# Headline form, with no label at all:
#   "Notice Inviting Tender (NIT) (Only through GeM) For Selection of Agency for Conducting
#    NABARD All-India Rural Financial Inclusion Survey (NAFIS Third Round)"
# Real NITs often state their subject this way and never write "Name of Work:", so the
# label-based pattern above finds nothing and every screen falls back to the FILENAME — the
# exact failure tender_meta exists to prevent (found on a live 81-page NABARD RFP).
#
# Terminates on a run of 3+ spaces as well as a newline: PDF text extraction frequently
# collapses a cover page into one long line, with column gaps surviving as wide runs of
# spaces. Three, not two — a title containing "(NAFIS  Third Round)" has a double space
# INSIDE it, and cutting there leaves an unclosed bracket on every screen.
_TITLE_HEADLINE = re.compile(
    r"\b(?:notice\s+inviting\s+tender|nit|request\s+for\s+proposal|rfp|tender\s+document)\b"
    r"[^\n]{0,120}?\bfor\s+"
    r"((?:selection|engagement|appointment|empanelment|providing|provision|supply|"
    r"procurement|hiring|design|development|implementation)\b.{6,200}?)"
    r"(?:\s{3,}|\n|$)",
    re.I | re.S,
)

# Issuing authority — usually the first government-sounding line on page one.
_AUTHORITY = re.compile(
    r"^\s*((?:office\s+of\s+the\s+|directorate\s+of\s+|department\s+of\s+|government\s+of\s+|"
    r"municipal\s+|ministry\s+of\s+)[^\n]{3,90})$",
    re.I | re.M,
)

_NOISE = re.compile(r"\s+")

# Submission deadline. GeM bid documents print "/Bid End Date/Time" and the value on the next
# line as "28-04-2026 19:00:00"; NITs write "Last date for submission of bid: 28.04.2026 up to
# 15:00 hrs". Only a fully-formed date is accepted, and the time is optional — a deadline the
# document does not state stays NULL rather than being guessed, because the dashboard's SLA
# chip and every "closes in N days" label read this field (found: six live tenders, all
# "Deadline not recorded", every one a GeM bid whose page one stated the end date).
_DEADLINE = re.compile(
    r"(?:/Bid End Date/Time"
    r"|\blast\s+date\s+(?:and\s+time\s+)?(?:for|of)\s+(?:bid\s+|tender\s+)?submission"
    r"|\bbid\s+submission\s+(?:end|closing|last)\s+date"
    r"|\bdue\s+date\s+(?:for|of)\s+(?:bid\s+)?submission)"
    r"[^0-9\n]{0,40}\n?\s*"
    r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})"
    r"(?:[ ,T]+(?:up\s*to\s+|at\s+|by\s+)?(\d{1,2})[:.](\d{2})(?::(\d{2}))?)?",
    re.I,
)

#: A filename that is machine-generated noise rather than something a person chose: a long
#: hex run, or an embedded export timestamp. Deliberately narrow — "Oil India wire rope
#: NIT.pdf" is a real answer from a real person and must survive.
_NOISY_FILENAME = re.compile(r"[0-9a-f]{16,}|_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}_")


@dataclass(frozen=True)
class TenderMeta:
    tender_number: str | None = None
    title: str | None = None
    authority: str | None = None
    #: ISO 8601 with the +05:30 offset — Indian portals state deadlines in IST and a naive
    #: timestamp would be read as UTC downstream (known-pitfalls: "15:00 IST ≠ 15:00 UTC").
    deadline: str | None = None


def _clean(v: str | None) -> str | None:
    if not v:
        return None
    v = _NOISE.sub(" ", v).strip(" .,:;-–—")
    return v or None


def _deadline(head: str) -> str | None:
    m = _DEADLINE.search(head)
    if not m:
        return None
    day, month, year, hour, minute, second = m.groups()
    try:
        dt = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                      int(second or 0), tzinfo=_IST)
    except ValueError:
        return None
    return dt.isoformat()


def extract_tender_meta(pages: list[str], max_pages: int = 3) -> TenderMeta:
    """Read identity from the first few pages. Absent labels yield None, never a guess."""
    head = "\n".join(pages[:max_pages])
    if not head.strip():
        return TenderMeta()

    number = _clean(m.group(1)) if (m := _NUMBER.search(head)) else None
    # Labelled form first — it is explicit and unambiguous. The headline form is the fallback
    # for documents that never write "Name of Work:", which is most NITs.
    title = _clean(m.group(1)) if (m := _TITLE.search(head)) else None
    if not title and (m := _TITLE_HEADLINE.search(head)):
        title = _clean(m.group(1))
    # Prefer the ISSUING BODY over the parent government. "Directorate of Municipal
    # Administration" tells a bid manager who to deal with; "Government of Maharashtra"
    # does not, and is what a first-match wins rule returns on almost every Indian RFP.
    candidates = [_clean(x) for x in _AUTHORITY.findall(head)]
    candidates = [c for c in candidates if c]
    specific = [c for c in candidates if not c.lower().startswith("government of")]
    authority = (specific or candidates or [None])[0]

    # A "title" that merely repeats the number is not a title.
    if title and number and title.lower().strip() == number.lower().strip():
        title = None
    return TenderMeta(tender_number=number, title=title, authority=authority,
                      deadline=_deadline(head))


def display_title(meta: TenderMeta, fallback: str) -> str:
    """What a human should see.

    The filename is the LAST resort, not the second. A bid team running twelve pursuits gets
    twelve identical "all_bid_docs_….pdf" headings, while the tender number they actually use
    to talk about the bid sits unused in the same object.

    When even that is missing — which is what happens when page one is a scan nobody could
    read — say so. A hex hash tells the reader nothing and hides the real problem, which is
    that the package was never readable.

    Mirror: `ReadinessHub.tsx`'s subtitle-dedup block rebuilds this same "number · authority"
    join in TypeScript to compare against the string this function produced. Change the
    separator or the field order on either side and update both — `app/tenders.py::
    _apply_pursuit_context` also calls back into this function to re-stamp a placeholder
    title once a pursuit backfill learns the number/authority this function didn't have yet.
    """
    if meta.title:
        return meta.title
    named = " · ".join(x for x in (meta.tender_number, meta.authority) if x)
    if named:
        return named
    stem = fallback.rsplit(".", 1)[0]
    return "Untitled tender" if _NOISY_FILENAME.search(stem) else stem
