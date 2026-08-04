"""Split a past bid into requirement -> answer pairs (G-FR3). Pure, no model, no I/O.

Most Indian government bids are Form-structured, and that structure is the whole trick: the
MeitY Model RFP Appendix-I headings this product already drafts against ("Form 7(b):
Understanding of the Project") are the same headings a past bid carries, and pre-qualification
compliance is a table. So the common case needs no model call at all — headings give the
requirement, the prose beneath gives the answer, and a two-column row gives both at once.

The model (pipeline/answer_miner.py) is for the residue: prose that answers a requirement it
never names. When it fails, this module's output is what ships — degraded, never invented.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: A mined pair is worth storing only if the answer says something. Below this it is a heading
#: with a page break under it, which would pollute suggestions with empty confident-looking hits.
_MIN_ANSWER_CHARS = 120
#: Requirement text longer than this is a page of prose that was mistaken for a heading.
_MAX_REQUIREMENT_CHARS = 300
_MIN_TOKEN_LEN = 4

_TOKEN = re.compile(r"[a-z0-9]+")

# Headings, in the three shapes bids actually use: a form label, a numbered clause, or a short
# emphatic line. Deliberately NOT "any short line" — that matches addresses and page furniture.
_FORM_HEADING = re.compile(
    r"^\s*(form|format|annexure|appendix|section|schedule)\s*[-–—]?\s*[0-9IVXA-Z]+[.:)]?\s*(.*)$",
    re.I,
)
_NUMBERED_HEADING = re.compile(r"^\s*\d+(\.\d+)*[.)]\s+(\S.{2,120})$")
_MARKDOWN_HEADING = re.compile(r"^\s*#{1,6}\s+(\S.*)$")

# A spreadsheet page arrives from ingest as "cell | cell | cell" (app/ingest.py). A compliance
# sheet is exactly that: requirement in one column, the bidder's response in another.
_TABLE_ROW = re.compile(r"^(?P<left>[^|]{12,300})\|(?P<right>.+)$")

# Page furniture that looks like a heading and is not. A bid's every page carries some of this.
_FURNITURE = re.compile(
    r"^\s*(page\s+\d+|\d+\s*of\s*\d+|confidential|commercial in confidence|"
    r"technical\s+bid|financial\s+bid|table of contents|contents)\s*$",
    re.I,
)


@dataclass(frozen=True)
class MinedAnswer:
    requirement_text: str
    answer_text: str
    section_key: str | None
    mined_by: str  # 'heading' | 'table'
    document: str


def _tokens(text: str) -> set[str]:
    """Same shape as pipeline/retrieval.py's tokeniser — one notion of "word" across reuse."""
    return {t for t in _TOKEN.findall(text.lower()) if len(t) >= _MIN_TOKEN_LEN}


def match_section_key(heading: str, specs: Sequence[tuple[str, str]]) -> str | None:
    """Map a past bid's heading onto one of our section keys, or None.

    `specs` is (key, our heading) — passed in rather than imported so this layer stays free of
    app-level imports. Token overlap, not string equality: "Form 11: Understanding of the
    Project" and "Form 7(b): Understanding of the Project" are the same section under different
    issuing authorities, which is precisely why SECTION_SPECS keys are semantic.
    """
    want = _tokens(heading)
    if not want:
        return None
    best, best_score = None, 0.0
    for key, spec_heading in specs:
        have = _tokens(spec_heading) | _tokens(key.replace("_", " "))
        if not have:
            continue
        score = len(want & have) / len(have)
        if score > best_score:
            best, best_score = key, score
    # Half the section's own words must appear. Lower than that and "Form 5: Letter of
    # Proposal" starts matching every heading containing "proposal".
    return best if best_score >= 0.5 else None


def _heading_of(line: str) -> str | None:
    line = line.strip()
    if not line or len(line) > _MAX_REQUIREMENT_CHARS or _FURNITURE.match(line):
        return None
    if m := _MARKDOWN_HEADING.match(line):
        return m.group(1).strip()
    if m := _FORM_HEADING.match(line):
        return line.strip()
    if m := _NUMBERED_HEADING.match(line):
        return m.group(2).strip()
    return None


def _table_pair(line: str) -> tuple[str, str] | None:
    """A compliance row: requirement on the left, the bidder's response on the right."""
    m = _TABLE_ROW.match(line.strip())
    if not m:
        return None
    left = m.group("left").strip()
    right = " ".join(c.strip() for c in m.group("right").split("|") if c.strip())
    # "Complied" / "Yes" answers a requirement but is not an ANSWER — nothing to reuse.
    if len(right) < 40 or len(left) < 12:
        return None
    return left, right


def mine_answers(
    pages: Sequence[tuple[str, str]],
    section_specs: Sequence[tuple[str, str]] = (),
) -> tuple[MinedAnswer, ...]:
    """Mine (requirement, answer) pairs from a past bid.

    `pages` is (document label, page text) in reading order — the shape app/ingest.py already
    produces. Pairs are emitted in document order so a reviewer reads them as the bid reads.
    """
    out: list[MinedAnswer] = []
    heading: str | None = None
    buf: list[str] = []
    doc = pages[0][0] if pages else ""

    def flush() -> None:
        nonlocal heading, buf
        body = "\n".join(buf).strip()
        if heading and len(body) >= _MIN_ANSWER_CHARS:
            out.append(
                MinedAnswer(
                    requirement_text=heading,
                    answer_text=body,
                    section_key=match_section_key(heading, section_specs),
                    mined_by="heading",
                    document=doc,
                )
            )
        buf = []

    for document, text in pages:
        for line in text.splitlines():
            if pair := _table_pair(line):
                # A table row is self-contained: it carries its own requirement, so it never
                # joins the surrounding narrative buffer.
                out.append(
                    MinedAnswer(
                        requirement_text=pair[0],
                        answer_text=pair[1],
                        section_key=match_section_key(pair[0], section_specs),
                        mined_by="table",
                        document=document,
                    )
                )
                continue
            if h := _heading_of(line):
                flush()
                heading, doc = h, document
                continue
            if line.strip():
                buf.append(line.strip())
    flush()
    return tuple(out)
