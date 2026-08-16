"""The house style of a bidder's past proposals, measured — never quoted. Pure, no I/O.

The point of the feature: a proposal drafted in generic vendor English does not read like the
client's other bids, and a bid manager notices in the first paragraph. So we measure how they
actually write and tell the drafter to match it.

**The brief is TEMPLATED from measurements, and contains no text taken from the documents.**
That is a deliberate divergence from a "have the model summarise their style" design, for two
reasons, and the second one is the real one:

1. A measured brief needs no model call, no prompt file, no eval gate and no per-rebuild cost.
2. Past proposals are untrusted input (G-6). A brief written by reading them, then injected
   into every future drafting prompt, is a prompt-injection channel that runs on every draft
   forever — a hostile or careless document containing "ignore previous instructions" would be
   laundered into the system prompt of an unrelated tender. Stripping digits and credentials
   (the plan's original guard) removes FACTS but does not remove INSTRUCTIONS. Emitting only
   fixed phrasing chosen by thresholds removes both, because no attacker-controlled byte ever
   reaches the prompt.

Style is shape. Content comes from evidence, and continues to go through cite-or-flag.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from .learning import edit_delta, measure_edits, render_edit_brief

_WORD = re.compile(r"[A-Za-z']+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_FIRST_PERSON = re.compile(r"\b(we|our|us|ours)\b", re.I)
_THIRD_PERSON = re.compile(r"\b(the\s+bidder|the\s+company|the\s+firm|the\s+applicant)\b", re.I)
_BULLET = re.compile(r"^\s*([-•*]|\(?[a-z0-9]{1,3}[.)])\s+", re.M)
_FORM_HEADING = re.compile(r"^\s*(form|format|annexure|appendix)\b", re.I | re.M)
_NUMBERED_HEADING = re.compile(r"^\s*\d+(\.\d+)*[.)]\s+\S", re.M)

#: Below this many sentences the measurement is noise, and a style brief built on noise is
#: worse than none: it would push every future proposal toward one accidental document.
MIN_SENTENCES = 40
#: Long-sentence threshold, in words. Indian government bid prose runs long; this separates
#: "clipped" from "flowing" rather than marking anything as wrong.
_LONG_SENTENCE = 24
_SHORT_SENTENCE = 15


@dataclass(frozen=True)
class StyleMetrics:
    sentences: int
    mean_sentence_words: float
    first_person_ratio: float
    bullet_ratio: float
    form_headings: bool
    numbered_headings: bool

    def as_dict(self) -> dict:
        return asdict(self)


def measure(texts: Sequence[str]) -> StyleMetrics:
    """Measure how this bidder writes. Counts only — nothing here retains source text."""
    joined = "\n".join(texts)
    sentences = [s for s in _SENTENCE.split(joined) if s.strip()]
    words_per = [len(_WORD.findall(s)) for s in sentences if _WORD.search(s)]
    first = len(_FIRST_PERSON.findall(joined))
    third = len(_THIRD_PERSON.findall(joined))
    lines = [line for line in joined.splitlines() if line.strip()]
    return StyleMetrics(
        sentences=len(words_per),
        mean_sentence_words=round(sum(words_per) / len(words_per), 1) if words_per else 0.0,
        first_person_ratio=round(first / (first + third), 2) if (first + third) else 0.0,
        bullet_ratio=round(len(_BULLET.findall(joined)) / len(lines), 2) if lines else 0.0,
        form_headings=bool(_FORM_HEADING.search(joined)),
        numbered_headings=bool(_NUMBERED_HEADING.search(joined)),
    )


def render_brief(m: StyleMetrics) -> str:
    """Turn measurements into instructions, using only phrasing written here.

    Returns "" when there is too little to measure — an empty brief leaves the drafter exactly
    as it behaves today, which is the correct behaviour for a workspace with no past bids.
    """
    if m.sentences < MIN_SENTENCES:
        return ""

    parts: list[str] = []
    if m.mean_sentence_words >= _LONG_SENTENCE:
        parts.append(
            "This bidder writes long, formal sentences that carry qualifying clauses; "
            "favour flowing prose over clipped statements."
        )
    elif m.mean_sentence_words <= _SHORT_SENTENCE:
        parts.append(
            "This bidder writes short, plain sentences; keep each one to a single idea and "
            "avoid stacked subordinate clauses."
        )
    else:
        parts.append("This bidder writes in a measured register — neither clipped nor ornate.")

    if m.first_person_ratio >= 0.7:
        parts.append('They write in the first person ("we", "our team"), not about themselves '
                     'in the third person.')
    elif m.first_person_ratio <= 0.3:
        parts.append('They refer to themselves in the third person ("the Bidder"), not as "we".')

    if m.bullet_ratio >= 0.25:
        parts.append("They use bulleted and enumerated lists heavily; structure accordingly.")
    elif m.bullet_ratio <= 0.05:
        parts.append("They write continuous paragraphs and use lists sparingly.")

    if m.form_headings:
        parts.append("They label sections with the tender's own form numbers; keep that habit.")
    elif m.numbered_headings:
        parts.append("They number headings hierarchically; keep that habit.")

    return (
        "## House style (measured from this bidder's previous submissions)\n\n"
        + "\n".join(f"- {p}" for p in parts)
        + "\n\nMatch this voice. It governs TONE AND SHAPE ONLY — it never licenses a claim, "
        "and every factual sentence still needs its citation."
    )


def build_profile(texts: Sequence[str], edits: Sequence[tuple[str, str]] = ()) -> dict:
    """The workspace's style profile: how they write, plus how they correct us.

    `texts` is the prose of their own submitted bids (uploaded, never generated — see
    app/learning.py). `edits` is (drafter's original, shipped text) pairs from
    proposal_sections; each is measured and discarded, so no source byte reaches the brief.
    """
    m = measure(texts)
    deltas = [d for d in (edit_delta(a, b) for a, b in edits) if d is not None]
    em = measure_edits(deltas)
    brief = render_brief(m)
    # Only append corrections to a brief that exists. A "learned from your corrections" note
    # floating alone, with no measured voice under it, reads as the system having opinions
    # about a bidder it has never read.
    if brief:
        brief += render_edit_brief(em)
    return {
        "metrics": {**m.as_dict(), "edits": em.as_dict()},
        "brief": brief,
        "built_from": len(texts),
    }
