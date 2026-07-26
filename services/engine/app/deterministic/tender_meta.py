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

# Issuing authority — usually the first government-sounding line on page one.
_AUTHORITY = re.compile(
    r"^\s*((?:office\s+of\s+the\s+|directorate\s+of\s+|department\s+of\s+|government\s+of\s+|"
    r"municipal\s+|ministry\s+of\s+)[^\n]{3,90})$",
    re.I | re.M,
)

_NOISE = re.compile(r"\s+")


@dataclass(frozen=True)
class TenderMeta:
    tender_number: str | None = None
    title: str | None = None
    authority: str | None = None


def _clean(v: str | None) -> str | None:
    if not v:
        return None
    v = _NOISE.sub(" ", v).strip(" .,:;-–—")
    return v or None


def extract_tender_meta(pages: list[str], max_pages: int = 3) -> TenderMeta:
    """Read identity from the first few pages. Absent labels yield None, never a guess."""
    head = "\n".join(pages[:max_pages])
    if not head.strip():
        return TenderMeta()

    number = _clean(m.group(1)) if (m := _NUMBER.search(head)) else None
    title = _clean(m.group(1)) if (m := _TITLE.search(head)) else None
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
    return TenderMeta(tender_number=number, title=title, authority=authority)


def display_title(meta: TenderMeta, fallback: str) -> str:
    """What a human should see. Falls back to the filename only when nothing was found."""
    return meta.title or fallback
