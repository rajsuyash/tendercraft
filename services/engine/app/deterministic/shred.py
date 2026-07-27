"""Requirement shredding — the denominator behind "we covered everything" (G-FR2).

A hand-shredded compliance matrix has no denominator. Nobody can state how many requirement
sentences the RFP contained, so "we answered everything" is an assertion rather than a
measurement, and a dropped clause produces no error anywhere. This module supplies the
denominator: every obligation-bearing sentence in the tender, and which of them did NOT
become a criterion.

**Deliberately deterministic, and a deviation from the PRD worth stating.** The discovery PRD
assigns requirement-sentence identification to the model. It is done here in Python instead,
because:

  - Obligation is a *grammatical* signal, not a semantic one. "shall / must / is required to"
    is exactly how a bid desk shreds an RFP by hand, and how a procurement lawyer reads one.
  - A denominator computed by a model is a denominator that changes when the prompt changes.
    An auditor can check "every sentence containing 'shall'"; they cannot check a vibe.
  - It costs nothing. Ingest already makes one model call per page; this would have doubled it
    on documents that run to hundreds of pages.

The ceiling is real and named: obligations phrased without a marker ("Bidders are to submit…"
is caught; "Submission of Form 3 is a precondition" is not) are missed. The mitigation is that
detection errs toward OVER-collecting — an over-collected sentence costs one human dismissal,
an under-collected one is the silent omission this module exists to prevent.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

# Obligation markers. Word-boundary matched, case-insensitive.
#
# "may" is deliberately ABSENT: it grants permission, not obligation, and including it turned
# a sample NIT's boilerplate ("the Authority may seek clarification") into dozens of phantom
# requirements — noise that trains users to dismiss the whole list without reading it.
_OBLIGATION = re.compile(
    r"\b("
    r"shall|must|will be required|is required|are required|required to|"
    r"mandatory|obligatory|shall be submitted|to be submitted|"
    r"bidder(?:s)? (?:is|are|should|shall|must)|"
    r"should (?:be |have |submit|provide|furnish|possess)|"
    r"has to|have to|need(?:s)? to"
    r")\b",
    re.IGNORECASE,
)

# Lines that are structure, not prose: page furniture, headings, table rules, ToC dot-leaders.
_FURNITURE = re.compile(
    r"^(page\s+\d+|\d+\s*$|[-=_.•\s|]+$|table of contents|annexure\s+[ivxlc]+\s*$)",
    re.IGNORECASE,
)

# A run of dots is a table-of-contents leader ("Pro forma of Integrity Pact ......... 42").
# The ToC quotes requirement headings verbatim, so without this every mandatory item is
# counted twice — once where it is stated and once where it is listed.
_TOC_LEADER = re.compile(r"\.{4,}")

_SENTENCE_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\d])|\n{2,}")

# Abbreviations whose trailing period is not a sentence end. Indian tender prose is dense with
# them — "Rs. 2,40,000", "Cl. 4.1(a)", "No. 7" — and splitting there cuts a requirement in half,
# which silently drops the half carrying the obligation's actual terms. Python's re has only
# fixed-width lookbehind, so this is applied as a merge-back pass rather than inside the split.
_ABBREV_TAIL = re.compile(
    r"(?:^|\s)(?:rs|no|nos|cl|sr|vol|fig|para|pvt|ltd|inc|mr|ms|mrs|dr|sec|art|annex|"
    r"approx|min|max|yrs?|[a-z])\.$",
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9 ]+")

#: A sentence shorter than this is a fragment (a table cell, a heading) and cannot carry a
#: complete obligation on its own.
MIN_SENTENCE_CHARS = 30
#: Token overlap above which a shredded sentence counts as represented by a criterion.
#: Substring containment is checked first; this catches the case where the extractor lightly
#: normalised the clause it quoted.
MAP_OVERLAP_THRESHOLD = 0.6
#: Tokens carrying no discriminating power when comparing two requirement sentences.
_STOPWORDS = frozenset(
    "the a an of to in for and or be is are as at by on with shall must from that this "
    "any all such".split()
)


@dataclass(frozen=True)
class RequirementSentence:
    page: int
    text: str


def _normalise(text: str) -> str:
    return _NON_WORD.sub(" ", _WS.sub(" ", text).strip().lower()).strip()


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _normalise(text).split() if t and t not in _STOPWORDS)


def split_sentences(page_text: str) -> list[str]:
    """Split page text into candidate sentences, dropping page furniture."""
    out: list[str] = []
    pending = ""
    for raw in _SENTENCE_SPLIT.split(page_text or ""):
        cleaned = _WS.sub(" ", raw).strip()
        if not cleaned or _FURNITURE.match(cleaned) or _TOC_LEADER.search(cleaned):
            continue
        cleaned = f"{pending} {cleaned}".strip() if pending else cleaned
        if _ABBREV_TAIL.search(cleaned):
            pending = cleaned  # the period was an abbreviation — the sentence continues
            continue
        pending = ""
        out.append(cleaned)
    if pending:
        out.append(pending)
    return out


def find_requirement_sentences(pages: Sequence[tuple[int, str]]) -> list[RequirementSentence]:
    """Every obligation-bearing sentence in the document, in page order.

    Deduplicated on normalised text within a page: a clause repeated in a header and a body
    table is one requirement, not two.
    """
    found: list[RequirementSentence] = []
    for page, text in pages:
        seen: set[str] = set()
        for sentence in split_sentences(text):
            if len(sentence) < MIN_SENTENCE_CHARS or not _OBLIGATION.search(sentence):
                continue
            key = _normalise(sentence)
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(RequirementSentence(page=page, text=sentence))
    return found


def is_represented(sentence: str, criterion_text: str) -> bool:
    """Does an extracted criterion already cover this sentence?

    Containment either way, else token overlap. The extractor quotes verbatim, so containment
    carries most cases; overlap catches light normalisation (collapsed whitespace, a dropped
    lead-in).
    """
    s_norm, c_norm = _normalise(sentence), _normalise(criterion_text)
    if not s_norm or not c_norm:
        return False
    if s_norm in c_norm or c_norm in s_norm:
        return True

    s_tokens, c_tokens = _tokens(sentence), _tokens(criterion_text)
    if not s_tokens:
        return False
    return len(s_tokens & c_tokens) / len(s_tokens) >= MAP_OVERLAP_THRESHOLD


def unmapped_sentences(
    pages: Sequence[tuple[int, str]],
    criteria: Sequence[tuple[int | None, str]],
) -> list[RequirementSentence]:
    """Requirement sentences that no extracted criterion represents.

    `criteria` is (anchor_page, verbatim_text). A criterion with no page is compared against
    every page rather than skipped: a missing anchor is an extraction weakness, and letting it
    silently inflate the unmapped backlog would blame the user for the extractor's gap.
    """
    by_page: dict[int, list[str]] = {}
    pageless: list[str] = []
    for page, text in criteria:
        if page is None:
            pageless.append(text)
        else:
            by_page.setdefault(page, []).append(text)

    out: list[RequirementSentence] = []
    for sentence in find_requirement_sentences(pages):
        candidates = by_page.get(sentence.page, []) + pageless
        if not any(is_represented(sentence.text, c) for c in candidates):
            out.append(sentence)
    return out
