"""What a finished proposal is allowed to teach the system. Pure, no I/O, no model.

The product now closes its own loop: a proposal that exports becomes a past bid and is mined
into the answer library, so tender #2 is drafted with tender #1's answers available. This
module is the gate on that loop, and the gate is the entire safety story.

**Only text a human signed is knowledge.** A section is harvestable if a person approved it or
rewrote it. Unapproved AI prose is the model's guess, and mining it teaches the system its own
output — after five tenders the client's "knowledge base" is a compressed recording of the
drafter's habits. That failure arrives disguised as exactly the success the feature promises:
reuse coverage rises, edit rates fall, and the prose drifts steadily away from how the client
actually writes, with nothing on any screen saying so. The approval gate that already exists
(B-FR4, app/proposal_routes.py::approve_section) is the filter, and it costs nothing.

Three more exclusions, each for its own reason:

- **Narrative sections only.** Assembled and compliance sections are rebuilt from structured
  rows every time (app/sections.py), and they carry transcluded figures (B-FR3). Storing one
  as a reusable "answer" would freeze a number that is supposed to come from live profile data.
- **Placeholders never.** A placeholder block is the absence of evidence, rendered honestly.
  Mining it would file "we could not source this" as an answer.
- **Substance floor.** The same floor the document miner uses. A heading with two lines under
  it is not an answer, and confident-looking empty hits are what train a user to stop reading
  the suggestion panel.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

#: Matches deterministic/answer_mining.py — one notion of "enough answer to be worth storing".
_MIN_ANSWER_CHARS = 120

#: Section kinds that carry reusable prose. Mirrors app/sections.py SectionKind values; kept as
#: a literal here so app/deterministic/ stays free of app-level imports (docs/conventions.md).
_NARRATIVE = "narrative"

#: A section whose evidence was missing. Rendered honestly by the drafter, never harvested.
_PLACEHOLDER = "placeholder"


@dataclass(frozen=True)
class Harvested:
    """One (requirement, answer) pair taken from our own finished proposal."""

    requirement_text: str
    answer_text: str
    section_key: str
    #: 'edited'   — a human rewrote this text, so it is the client's own words.
    #: 'approved' — model prose a named human vouched for. Weaker, and worth telling apart:
    #:              the reuse panel can say which, and Phase 3 ranking can prefer the former.
    provenance: str


def harvestable(sections: Sequence[dict]) -> tuple[Harvested, ...]:
    """The sections of a finished proposal that may enter the answer library.

    `sections` is proposal_sections rows (db.get_sections) in order. Returns empty when nothing
    qualifies — a proposal exported with zero approved narrative sections teaches nothing, which
    is the correct outcome and not an error.

    The section's own `key` is the section key: this is our document, so there is no heading to
    match against SECTION_SPECS. That is the whole reason harvesting needs no regex pass and no
    model call — mining exists to recover structure from a blob, and our own proposal is not one.
    """
    out: list[Harvested] = []
    for s in sections:
        if (s.get("kind") or "") != _NARRATIVE:
            continue
        if (s.get("status") or "") == _PLACEHOLDER:
            continue
        edited = bool(s.get("edited_by"))
        if not edited and not s.get("approved_by"):
            continue
        body = (s.get("body_md") or "").strip()
        if len(body) < _MIN_ANSWER_CHARS:
            continue
        heading = (s.get("heading") or "").strip()
        key = (s.get("key") or "").strip()
        if not heading or not key:
            continue
        out.append(
            Harvested(
                requirement_text=heading,
                answer_text=body,
                section_key=key,
                provenance="edited" if edited else "approved",
            )
        )
    return tuple(out)


# --- what the human changed (Phase 2) -----------------------------------------------------
#
# The diff between what the drafter wrote and what the bid manager shipped is the only
# correction signal this product gets for free. It is measured, never quoted: the counts below
# feed the house-style brief, and the SOURCE TEXT NEVER DOES. A brief assembled by reading
# proposals and injected into every future draft is a permanent prompt-injection channel
# (G-6) — the argument is written out in deterministic/style.py and it applies here unchanged.
# Stripping facts from quoted text would not help, because instructions are not facts.

_WORD = re.compile(r"[A-Za-z0-9']+")

#: Below this many edited sections the aggregate is one person's mood on one afternoon, and a
#: style brief built on it would push every future proposal toward one accidental document.
MIN_EDITS = 5

#: A length change smaller than this is drafting noise, not a preference.
_LENGTH_SHIFT = 0.15
#: Above this fraction of words replaced, the human did not edit the draft — they rewrote it.
_HEAVY_REWRITE = 0.60


@dataclass(frozen=True)
class EditDelta:
    """How far one section moved between the drafter's version and the shipped one."""

    original_words: int
    final_words: int
    kept: int
    #: Fraction of the ORIGINAL's words that did not survive. 0.0 = untouched, 1.0 = replaced.
    rewrite_ratio: float
    #: Signed length change as a fraction of the original. Negative means the human cut.
    length_shift: float

    def as_dict(self) -> dict:
        return asdict(self)


def edit_delta(original: str, final: str) -> EditDelta | None:
    """Measure one edit. None when there is nothing to compare.

    Returns None rather than a zeroed delta for a missing original: `original_md` is NULL for
    pre-0031 rows that were already edited, and counting those as "unchanged" would report the
    most heavily rewritten sections in the workspace as the least — the exact inversion of the
    signal, in the metric built to say whether the system is improving.
    """
    a, b = _WORD.findall(original or ""), _WORD.findall(final or "")
    if not a:
        return None
    kept = sum(
        block.size for block in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    )
    return EditDelta(
        original_words=len(a),
        final_words=len(b),
        kept=kept,
        rewrite_ratio=round(1 - kept / len(a), 3),
        length_shift=round((len(b) - len(a)) / len(a), 3),
    )


@dataclass(frozen=True)
class EditMetrics:
    edits: int
    mean_rewrite_ratio: float
    mean_length_shift: float

    def as_dict(self) -> dict:
        return asdict(self)


def measure_edits(deltas: Sequence[EditDelta]) -> EditMetrics:
    n = len(deltas)
    if not n:
        return EditMetrics(0, 0.0, 0.0)
    return EditMetrics(
        edits=n,
        mean_rewrite_ratio=round(sum(d.rewrite_ratio for d in deltas) / n, 3),
        mean_length_shift=round(sum(d.length_shift for d in deltas) / n, 3),
    )


def render_edit_brief(m: EditMetrics) -> str:
    """Turn edit measurements into instructions, using only phrasing written here.

    Returns "" below the floor — an empty addition leaves the drafter exactly as it behaves
    today, which is correct for a workspace nobody has edited much yet.
    """
    if m.edits < MIN_EDITS:
        return ""
    parts: list[str] = []
    if m.mean_length_shift <= -_LENGTH_SHIFT:
        parts.append(
            "This bidder consistently tightens generated prose; prefer fewer words per "
            "sentence and cut qualifying clauses that add no commitment."
        )
    elif m.mean_length_shift >= _LENGTH_SHIFT:
        parts.append(
            "This bidder consistently expands generated prose; they expect more specific "
            "detail per requirement than a first draft usually carries."
        )
    if m.mean_rewrite_ratio >= _HEAVY_REWRITE:
        parts.append(
            "Generated prose is rewritten heavily here rather than edited; be concrete and "
            "specific rather than general, and avoid stock vendor phrasing."
        )
    if not parts:
        return ""
    return (
        "\n\n## Learned from this bidder's corrections\n\n"
        + "\n".join(f"- {p}" for p in parts)
        + "\n\nThese are shape corrections measured from their own edits. They govern TONE AND "
        "SHAPE ONLY — they never license a claim."
    )


# --- is it actually working? (Phase 4) -----------------------------------------------------
#
# "Self-sufficient after five or six tenders" is a claim, and this product's whole position is
# that it does not make unsourced claims. So the loop gets a meter, computed from data the
# system already holds, and the meter is allowed to say no.
#
# Three numbers, and the third is the honest one. Coverage and utilisation both rise simply by
# accumulating rows; only the edit trend can FALL when the system is not learning, which is
# why it is the one to watch and the one a demo would quietly leave out.


@dataclass(frozen=True)
class Coverage:
    """How much of one tender the existing answer library can already speak to."""

    tender_id: str
    criteria: int
    with_suggestion: int

    @property
    def ratio(self) -> float:
        return round(self.with_suggestion / self.criteria, 3) if self.criteria else 0.0

    def as_dict(self) -> dict:
        return {**asdict(self), "ratio": self.ratio}


def reuse_coverage(
    tender_id: str, requirements: Sequence[str], answers: Sequence[dict]
) -> Coverage:
    """Fraction of a tender's requirements that draw at least one suggestion.

    Uses the live ranker, so the number moves with the ranker rather than drifting from it —
    a coverage meter computed by its own similarity rule would eventually disagree with the
    panel the user is looking at, and the meter would be the one nobody trusted.
    """
    from .answer_reuse import rank_answers  # local: answer_reuse imports drafting, keep it lazy

    hit = sum(1 for r in requirements if rank_answers(r, answers, limit=1))
    return Coverage(tender_id=tender_id, criteria=len(requirements), with_suggestion=hit)


def utilisation(answers: Sequence[dict]) -> dict:
    """How much of the corpus has ever been accepted into a draft.

    Rising means the base is earning its place. FLAT while the corpus grows is the failure
    this metric exists to catch: answers accumulating that nobody ever takes, which is a
    suggestion panel filling with noise (the reason `collapse_duplicates` exists).
    """
    total = len(answers)
    used = sum(1 for a in answers if int(a.get("times_used") or 0) > 0)
    return {"used": used, "total": total,
            "ratio": round(used / total, 3) if total else 0.0}
